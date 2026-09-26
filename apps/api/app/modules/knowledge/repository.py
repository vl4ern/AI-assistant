from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.modules.auth.models import User

from .models import Event, EventCreate, Task, TaskCreate, TaskStatus


class KnowledgeRepository(ABC):
    """
    Хранилище фактов базы знаний и аккаунтов.

    Параметр user_id в методах-выборках:
    - None — вернуть всё (внутреннее использование);
    - конкретный id — личные записи пользователя плюс общие
      (user_id = SHARED_USER_ID), например импортированное расписание.
    """

    @abstractmethod
    def list_tasks(self, user_id: str | None = None) -> list[Task]:
        raise NotImplementedError

    @abstractmethod
    def get_task(self, task_id: str) -> Task | None:
        raise NotImplementedError

    @abstractmethod
    def create_task(self, payload: TaskCreate) -> Task:
        raise NotImplementedError

    @abstractmethod
    def update_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
        raise NotImplementedError

    @abstractmethod
    def update_task_schedule(
        self,
        task_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> Task | None:
        raise NotImplementedError

    @abstractmethod
    def list_events(self, user_id: str | None = None) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def create_event(self, payload: EventCreate) -> Event:
        raise NotImplementedError

    @abstractmethod
    def create_user(
        self,
        username: str,
        password_hash: str,
        salt: str,
        user_id: str | None = None,
    ) -> User:
        raise NotImplementedError

    @abstractmethod
    def get_user_by_username(self, username: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    def is_schedule_dirty(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_schedule_dirty(self, value: bool) -> None:
        raise NotImplementedError
