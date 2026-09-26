from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class User(BaseModel):
    """Аккаунт пользователя (внутреннее представление, хранится в репозитории)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    username: str
    password_hash: str
    salt: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserPublic(BaseModel):
    """Публичное представление аккаунта (без секретов)."""

    id: str
    username: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=4, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user: UserPublic
