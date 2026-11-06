from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone
import asyncio
from app.api.ws import manager

# ВАЖНО: Для фоновых задач нужна независимая сессия (SessionLocal)
from app.database import get_db, SessionLocal 
from app.models import User, Match, Task, Submission, MatchResult
from app.api.auth import get_current_user
from app.sandbox import execute_code 

# from app.realtime.scoring import send_ws_notification 

router = APIRouter(tags=["Проверка решений"])

# Схема четко по контракту с фронтом (заменили problem_id на match_id и task_id)
class SubmitRequest(BaseModel):
    match_id: int
    task_id: int
    code: str

def process_submission_in_background(submission_id: int, match_id: int, task_id: int, user_id: int, code: str):
    # Фоновые задачи запускаются вне HTTP-запроса, поэтому открываем свою сессию БД
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        
        # Берем тесты прямо из задачи, а не хардкодим
        mock_tests = [
            {"input": task.example_input, "output": task.example_output}
        ] if task.example_input else []
        
        result = execute_code(
            code=code, 
            language="python", 
            time_limit=2.0, 
            memory_limit=128, 
            test_cases=mock_tests
        )
        
        # Подстрой ключи словаря под то, что реально возвращает execute_code
        is_success = result.get("success", False) 
        verdict = "OK" if is_success else "WA"
        
        # Обновляем статус отправки
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if submission:
            submission.verdict = verdict
        
        # Начисляем баллы за правильное решение
        if is_success:
            match_result = db.query(MatchResult).filter(
                MatchResult.match_id == match_id, 
                MatchResult.participant_id == user_id
            ).first()
            
            if not match_result:
                match_result = MatchResult(match_id=match_id, participant_id=user_id, solved_count=1, points=1)
                db.add(match_result)
            else:
                match_result.solved_count += 1
                match_result.points += 1
        
        db.commit()
        
        # Отправляем уведомление на фронт
        print(f"[{user_id}] Вердикт песочницы: {verdict}")
        # Собираем данные для фронтенда
        event_data = {
            "event": "submission_checked",
            "submission_id": submission_id,
            "user_id": user_id,
            "verdict": verdict,
            "points_earned": 1 if is_success else 0
        }
        
        # Прокидываем асинхронный вызов из синхронного потока
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            manager.broadcast_to_match(match_id, event_data), 
            loop
        )
    finally:
        db.close() # Обязательно закрываем сессию фоновой задачи

@router.post("/submissions/submit")
def submit_code(
    payload: SubmitRequest, 
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Проверяем валидность матча
    match = db.query(Match).filter(Match.id == payload.match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Матч не найден")
        
    if match.status != "active":
        raise HTTPException(status_code=400, detail="Матч еще не начался или уже завершен")

    # 2. Жесткая привязка ко времени (по требованиям фронтов)
    now = datetime.now(timezone.utc)
    # Раскомментируй это, когда в БД появятся контесты с реальным end_at
    # if match.end_at and now > match.end_at.replace(tzinfo=timezone.utc):
    #     raise HTTPException(status_code=400, detail="Время вышло, решения больше не принимаются")

    # 3. Проверяем наличие задачи в текущем контесте
    task = db.query(Task).filter(Task.id == payload.task_id, Task.contest_id == match.contest_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # 4. Создаем черновик отправки в базе со статусом running
    new_sub = Submission(
        match_id=match.id,
        task_id=task.id,
        user_id=user.id,
        code=payload.code,
        language="python",
        verdict="running"
    )
    db.add(new_sub)
    db.commit()
    db.refresh(new_sub)
        
    # 5. Прокидываем в фон только ID-шники и код
    background_tasks.add_task(
        process_submission_in_background, 
        submission_id=new_sub.id,
        match_id=match.id,
        task_id=task.id,
        user_id=user.id,
        code=payload.code
    )
    
    return {
        "submission_id": new_sub.id, 
        "status": "processing", 
        "message": "Решение отправлено в песочницу"
    }