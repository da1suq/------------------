from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.models import Contest, Task, User
from app.schemas.models import ContestCreate, TaskCreate
from app.api.auth import get_current_user

router = APIRouter(prefix="/contests", tags=["Контесты и Задачи"])

@router.get("/")
def get_contests(db: Session = Depends(get_db)):
    # Отдаем реальный список из базы
    return db.query(Contest).all()

@router.post("/")
def create_contest(
    contest: ContestCreate, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user) # Защищаем: только авторизованные
):
    # Если фронт не прислал даты, ставим дефолтные (на 2 часа)
    now = datetime.now(timezone.utc)
    new_contest = Contest(
        author_id=current_user.id,
        title=contest.title,
        description=getattr(contest, 'description', ''),
        start_at=getattr(contest, 'start_at', now),
        end_at=getattr(contest, 'end_at', now + timedelta(hours=2)),
        difficulty=getattr(contest, 'difficulty', 'easy'),
        mode="duel"
    )
    db.add(new_contest)
    db.commit()
    db.refresh(new_contest)
    return new_contest

@router.get("/{contest_id}/tasks")
def get_tasks(contest_id: int, db: Session = Depends(get_db)):
    tasks = db.query(Task).filter(Task.contest_id == contest_id).all()
    return tasks

@router.post("/{contest_id}/tasks")
def create_task(
    contest_id: int, 
    task: TaskCreate, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    new_task = Task(
        contest_id=contest_id,
        title=task.title,
        description=getattr(task, 'description', ''),
        example_input=getattr(task, 'example_input', ''),
        example_output=getattr(task, 'example_output', '')
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

# Тот самый скрипт для быстрой генерации данных для фронтов
@router.post("/seed")
def seed_test_data(db: Session = Depends(get_db)):
    if db.query(Contest).first():
        return {"message": "Данные уже были сгенерированы ранее!"}
    
    # 1. Создаем системного юзера, если его нет
    user = db.query(User).first()
    if not user:
        user = User(
            email="admin@dojo.com",
            password_hash="dummy_hash",
            role="admin"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # 2. Создаем контест
    now = datetime.now(timezone.utc)
    new_contest = Contest(
        author_id=user.id, # Берем ID реально существующего юзера
        title="Hackathon Demo Contest",
        description="Тестовый контест для проверки дуэлей 1х1",
        start_at=now,
        end_at=now + timedelta(hours=2),
        difficulty="easy",
        mode="duel"
    )
    db.add(new_contest)
    db.flush() 

    # 3. Создаем задачи
    task1 = Task(
        contest_id=new_contest.id,
        title="A + B",
        description="Считайте два числа через пробел и выведите их сумму.",
        example_input="2 2",
        example_output="4"
    )
    
    task2 = Task(
        contest_id=new_contest.id,
        title="Умножение",
        description="Считайте два числа через пробел и выведите их произведение.",
        example_input="10 5",
        example_output="50"
    )
    
    db.add_all([task1, task2])
    db.commit()

    return {
        "message": "Успешно! Тестовый юзер, контест и задачи созданы.", 
        "contest_id": new_contest.id
    }