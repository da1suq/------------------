import jwt 
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError

# Секретный ключ для подписи токенов (на хакатоне храним тут, в реальной жизни - в .env файле)
SECRET_KEY = "super-secret-hackathon-key"
ALGORITHM = "HS256"

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext

# Импортируем наши схемы, подключение к БД и таблицу User
from app.schemas.models import RegisterParticipant, LoginRequest
from app.database import get_db
from app.models import User

router = APIRouter(tags=["Авторизация и Пользователи"])

# Настраиваем инструмент для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password[:72])

@router.post("/auth/register/participant")
def register_participant(user_data: RegisterParticipant, db: Session = Depends(get_db)):
    
    # 1. Проверяем, нет ли уже такого email в базе (чтобы не было дублей)
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email уже занят")

    # 2. Хешируем пароль из JSON, который прислал фронтенд
    hashed_password = get_password_hash(user_data.password)

    # 3. Создаем запись для базы данных на основе нашей модели User
    new_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        role="participant"
    )

    # 4. Сохраняем в PostgreSQL
    db.add(new_user)       
    db.commit()            
    db.refresh(new_user)   

    # 5. Возвращаем успешный ответ
    return {"id": new_user.id, "email": new_user.email, "role": new_user.role}


@router.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # 1. Ищем пользователя в базе по email
    # ВАЖНО: Swagger кладет email в поле form_data.username, это стандарт OAuth2
    user = db.query(User).filter(User.email == form_data.username).first()
    
    # Мы не говорим "такого email нет", мы даем общую ошибку, чтобы хакеры не перебирали базу
    if not user:
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    # 2. Проверяем пароль: сравниваем то, что ввел юзер, с хешем из базы
    if not pwd_context.verify(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный email или пароль")

    # 3. Собираем данные для "пропуска" (токена)
    expiration = datetime.now(timezone.utc) + timedelta(hours=24)
    token_payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expiration
    }

    # 4. Генерируем сам токен и подписываем нашим секретным ключом
    token = jwt.encode(token_payload, SECRET_KEY, algorithm=ALGORITHM)

    return {"access_token": token, "token_type": "bearer"}

# Эта штука автоматически будет искать токен в заголовках запроса
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Не удалось проверить токен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Пытаемся расшифровать токен нашим секретным ключом
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
        
    # Ищем юзера в базе по ID из токена
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user