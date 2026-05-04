from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .models import Event, EventCreate, Task, TaskCreate, TaskStatus


class KnowledgeRepository(ABC):
    @abstractmethod
    def list_tasks(self) -> list[Task]:
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
    def list_events(self) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def create_event(self, payload: EventCreate) -> Event:
        raise NotImplementedError

    @abstractmethod
    def is_schedule_dirty(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_schedule_dirty(self, value: bool) -> None:
        raise NotImplementedError
