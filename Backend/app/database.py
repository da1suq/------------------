from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Используем pg8000, который не выдает ошибку кодировки C-драйверов
# Подключаемся к Докеру на порт 5433 (метод trust, без пароля)
SQLALCHEMY_DATABASE_URL = "postgresql+pg8000://postgres@127.0.0.1:5433/codedojo_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Фабрика сессий. Именно её мы вызываем в фоновых задачах!
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Генератор сессий для обычных HTTP-запросов (FastAPI Depends)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 