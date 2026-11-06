from fastapi import FastAPI
# Импортируем роутеры из наших новых файлов
from app.api import auth, contests, submissions
from app.realtime.router import router as realtime_router
from app.api.submissions import router as submissions_router
from app.database import engine
from app.models import Base
from app.api import ws

# SQLAlchemy проверит базу и автоматически создаст пустые таблицы, если их нет
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Contest system API", 
    description="Модульная архитектура"
)

# Подключаем роутеры к основному приложению
app.include_router(auth.router)
app.include_router(contests.router)
app.include_router(submissions.router)
app.include_router(realtime_router)
app.include_router(submissions_router)
app.include_router(ws.router)