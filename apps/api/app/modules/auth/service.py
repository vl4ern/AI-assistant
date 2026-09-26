from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.modules.auth.models import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    User,
    UserPublic,
)
from app.modules.knowledge.repository import KnowledgeRepository

PASSWORD_HASH_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


class AuthService:
    """
    Регистрация, вход и проверка токенов.

    Пароли хранятся как PBKDF2-HMAC-SHA256 с индивидуальной солью,
    токены подписываются HMAC-SHA256 и живут 7 дней.
    """

    def __init__(self, repository: KnowledgeRepository, secret: str) -> None:
        self._repository = repository
        self._secret = secret

    def register(self, payload: RegisterRequest) -> TokenResponse:
        username = payload.username.strip()
        if self._repository.get_user_by_username(username) is not None:
            raise ValueError(f"Имя пользователя «{username}» уже занято")

        salt = secrets.token_hex(16)
        password_hash = self._hash_password(payload.password, salt)
        user = self._repository.create_user(
            username=username,
            password_hash=password_hash,
            salt=salt,
        )
        return self._issue_token_response(user)

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self._repository.get_user_by_username(payload.username.strip())
        if user is None:
            raise ValueError("Неверное имя пользователя или пароль")

        expected = self._hash_password(payload.password, user.salt)
        if not hmac.compare_digest(expected, user.password_hash):
            raise ValueError("Неверное имя пользователя или пароль")

        return self._issue_token_response(user)

    def verify_token(self, token: str) -> UserPublic | None:
        try:
            encoded_payload, signature = token.split(".", 1)
            expected_signature = self._sign(encoded_payload)
            if not hmac.compare_digest(signature, expected_signature):
                return None

            padded_payload = encoded_payload + "=" * (-len(encoded_payload) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded_payload))
            if payload.get("exp", 0) < time.time():
                return None

            return UserPublic(id=payload["user_id"], username=payload["username"])
        except (ValueError, KeyError, TypeError):
            return None

    def _issue_token_response(self, user: User) -> TokenResponse:
        return TokenResponse(
            token=self._issue_token(user.id, user.username),
            user=UserPublic(id=user.id, username=user.username),
        )

    def _issue_token(self, user_id: str, username: str) -> str:
        payload = json.dumps(
            {
                "user_id": user_id,
                "username": username,
                "exp": int(time.time()) + TOKEN_TTL_SECONDS,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        return f"{encoded_payload}.{self._sign(encoded_payload)}"

    def _sign(self, encoded_payload: str) -> str:
        return hmac.new(
            self._secret.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PASSWORD_HASH_ITERATIONS,
        ).hex()
