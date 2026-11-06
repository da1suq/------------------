from fastapi import FastAPI, Body
from pydantic import BaseModel

app = FastAPI(
    title="CodeDojo API", 
    description="Mock API для фронтенда (на основе спецификации 0.1)"
)

# ==========================================
# СХЕМЫ ДАННЫХ ДЛЯ ЗАПРОСОВ (REQUEST BODIES)
# ==========================================
class RegisterParticipant(BaseModel):
    email: str
    password: str

class RegisterAdmin(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ContestCreate(BaseModel):
    title: str
    description: str
    mode: str
    start_at: str
    duration_minutes: int

class TaskCreate(BaseModel):
    title: str
    statement: str
    time_limit: int
    memory_limit: int
    order: int

class SubmissionRequest(BaseModel):
    task_id: str
    language: str
    code: str

# ==========================================
# 6. АВТОРИЗАЦИЯ И ПОЛЬЗОВАТЕЛИ
# ==========================================
@app.post("/auth/register/participant", tags=["6. Авторизация"])
def register_participant(user: RegisterParticipant):
    return {"id": "user_123", "email": user.email, "roles": ["participant"]}

@app.post("/auth/register/admin", tags=["6. Авторизация"])
def register_admin(admin: RegisterAdmin):
    return {"id": "admin_1", "email": admin.email, "roles": ["admin"]}

@app.post("/auth/login", tags=["6. Авторизация"])
def login(creds: LoginRequest):
    return {"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "token_type": "bearer"}

@app.post("/auth/logout", tags=["6. Авторизация"])
def logout():
    return {"message": "Сессия завершена"}

@app.get("/users/me", tags=["6. Авторизация"])
def get_me():
    return {"id": "user_123", "email": "hacker@test.com", "roles": ["participant"]}

@app.get("/users/{user_id}", tags=["6. Авторизация"])
def get_user(user_id: str):
    return {"id": user_id, "email": f"{user_id}@test.com"}


# ==========================================
# 7. КОНТЕСТЫ И ЗАДАЧИ
# ==========================================
@app.get("/contests", tags=["7. Контесты и Задачи"])
def get_contests():
    return [{"id": "c_1", "title": "Хакатон: Отборочный тур", "status": "waiting"}]

@app.get("/contests/{contest_id}", tags=["7. Контесты и Задачи"])
def get_contest(contest_id: str):
    return {"id": contest_id, "title": "Хакатон: Отборочный тур", "mode": "duel", "status": "waiting"}

@app.post("/contests", tags=["7. Контесты и Задачи"])
def create_contest(contest: ContestCreate):
    return {"id": "c_2", **contest.dict(), "status": "draft"}

@app.patch("/contests/{contest_id}", tags=["7. Контесты и Задачи"])
def update_contest(contest_id: str, data: dict = Body(...)):
    return {"id": contest_id, "status": "waiting", "message": "Обновлено"}

@app.get("/contests/{contest_id}/tasks", tags=["7. Контесты и Задачи"])
def get_tasks(contest_id: str):
    return [{"id": "t_1", "contest_id": contest_id, "title": "A+B", "time_limit": 1000}]

@app.post("/contests/{contest_id}/tasks", tags=["7. Контесты и Задачи"])
def create_task(contest_id: str, task: TaskCreate):
    return {"id": "t_2", "contest_id": contest_id, **task.dict()}

@app.patch("/tasks/{task_id}", tags=["7. Контесты и Задачи"])
def update_task(task_id: str, data: dict = Body(...)):
    return {"id": task_id, "message": "Задача обновлена"}

@app.delete("/tasks/{task_id}", tags=["7. Контесты и Задачи"])
def delete_task(task_id: str):
    return {"message": "Задача удалена"}


# ==========================================
# 8. ДУЭЛИ И ПРИГЛАШЕНИЯ
# ==========================================
@app.post("/contests/{contest_id}/duels", tags=["8. Дуэли"])
def create_duel(contest_id: str):
    return {"duel_id": "d_1", "invitation_token": "token-xyz-123", "status": "waiting"}

@app.post("/invitations/{token}/accept", tags=["8. Дуэли"])
def accept_invitation(token: str):
    return {"message": "Приглашение принято", "match_id": "d_1"}

@app.get("/duels/{duel_id}", tags=["8. Дуэли"])
def get_duel(duel_id: str):
    return {"id": duel_id, "participant_1_id": "user_1", "participant_2_id": "user_2"}

@app.get("/duels/{duel_id}/status", tags=["8. Дуэли"])
def get_duel_status(duel_id: str):
    return {"id": duel_id, "status": "active"}


# ==========================================
# 9. КОМАНДЫ
# ==========================================
@app.post("/contests/{contest_id}/teams", tags=["9. Команды"])
def create_team(contest_id: str):
    return {"team_id": "team_1", "invitation_token": "token-team-456"}

@app.get("/teams/{team_id}", tags=["9. Команды"])
def get_team(team_id: str):
    return {"id": team_id, "member_1_id": "user_1", "member_2_id": "user_3"}

@app.get("/teams/me", tags=["9. Команды"])
def get_my_team():
    return {"id": "team_1", "contest_id": "c_1"}


# ==========================================
# 10. ОТПРАВКА РЕШЕНИЙ
# ==========================================
@app.post("/submissions", tags=["10. Решения"])
def submit_code(sub: SubmissionRequest):
    return {"id": "sub_1", "verdict": "waiting", "task_id": sub.task_id}

@app.get("/submissions/{submission_id}", tags=["10. Решения"])
def get_submission(submission_id: str):
    return {"id": submission_id, "verdict": "OK", "passed_tests": 15, "total_tests": 15}

@app.get("/contests/{contest_id}/submissions/me", tags=["10. Решения"])
def get_my_contest_submissions(contest_id: str):
    return [{"id": "sub_1", "task_id": "t_1", "verdict": "OK"}]

@app.get("/tasks/{task_id}/submissions/me", tags=["10. Решения"])
def get_my_task_submissions(task_id: str):
    return [{"id": "sub_1", "task_id": task_id, "verdict": "WA"}]


# ==========================================
# 11. РЕЗУЛЬТАТЫ И АДМИНКА
# ==========================================
@app.get("/contests/{contest_id}/results", tags=["11. Результаты"])
def get_results(contest_id: str):
    return [{"participant_id": "user_1", "score": 100, "place": 1}]

@app.get("/contests/{contest_id}/results/me", tags=["11. Результаты"])
def get_my_result(contest_id: str):
    return {"score": 100, "place": 1, "penalty": 0}

@app.get("/admin/contests", tags=["11. Админка"])
def admin_get_contests():
    return [{"id": "c_1", "status": "active"}]

@app.get("/admin/contests/{contest_id}/participants", tags=["11. Админка"])
def admin_get_participants(contest_id: str):
    return [{"id": "user_1", "email": "user1@test.com"}]

@app.get("/admin/contests/{contest_id}/submissions", tags=["11. Админка"])
def admin_get_submissions(contest_id: str):
    return [{"id": "sub_1", "code": "print(input())", "verdict": "OK"}]

@app.get("/admin/submissions/{submission_id}", tags=["11. Админка"])
def admin_get_submission_detail(submission_id: str):
    return {"id": submission_id, "code": "print(input())", "execution_time": 0.12}
