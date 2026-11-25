from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.container import container
from app.modules.auth.models import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest) -> TokenResponse:
    try:
        return container.auth_service.register(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    try:
        return container.auth_service.login(payload)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/me", response_model=UserPublic)
def me(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    return user
