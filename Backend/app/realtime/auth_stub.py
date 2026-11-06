"""ЗАГЛУШКА авторизации, чтобы модуль запускался отдельно.
TODO(B1): заменить на реальные `get_current_user` и разбор токена из app.auth.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException


@dataclass
class User:
    id: int
    name: str
    role: str  # participant | organizer


DEMO_TOKENS = {
    "anna-token": User(1, "Анна", "participant"),
    "boris-token": User(2, "Борис", "participant"),
    "org-token": User(100, "Организатор", "organizer"),
}


def user_from_token(token: Optional[str]) -> Optional[User]:
    return DEMO_TOKENS.get(token or "")


def get_current_user(authorization: str = Header(default="")) -> User:
    user = user_from_token(authorization.removeprefix("Bearer ").strip())
    if user is None:
        raise HTTPException(401, "invalid token")
    return user
