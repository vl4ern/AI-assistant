from __future__ import annotations

from fastapi import Header, HTTPException

from app.container import container
from app.modules.auth.models import UserPublic


def get_current_user(authorization: str = Header(default="")) -> UserPublic:
    """Достаёт пользователя из заголовка Authorization: Bearer <token>."""
    parts = authorization.split()
    token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else parts[0] if parts else ""
    token = token.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход в аккаунт")

    user = container.auth_service.verify_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите снова")
    return user
