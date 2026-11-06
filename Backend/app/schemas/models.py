from pydantic import BaseModel

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