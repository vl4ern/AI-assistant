from __future__ import annotations

from datetime import datetime

from app.modules.knowledge.models import (
    Event,
    EventCreate,
    Task,
    TaskCreate,
    TaskStatus,
    TaskUpdate,
)
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.rules import (
    is_active_task,
    is_schedulable_task,
    validate_event_knowledge,
    validate_task_knowledge,
)


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self._repository = repository

    def list_tasks(self) -> list[Task]:
        return self._repository.list_tasks()

    def list_active_tasks(self) -> list[Task]:
        return [task for task in self._repository.list_tasks() if is_active_task(task)]

    def list_schedulable_tasks(self) -> list[Task]:
        return [
            task
            for task in self._repository.list_tasks()
            if is_schedulable_task(task)
        ]

    def get_task(self, task_id: str) -> Task | None:
        return self._repository.get_task(task_id)

    def create_task(self, payload: TaskCreate) -> Task:
        validate_task_knowledge(payload)
        return self._repository.create_task(payload)

    def update_task(self, task_id: str, payload: TaskUpdate) -> Task | None:
        current = self._repository.get_task(task_id)

        if current is None:
            return None

        data = current.model_dump()
        data.update(payload.model_dump(exclude_unset=True))

        merged_task = Task(**data)
        validate_task_knowledge(merged_task)

        return self._repository.update_task(task_id, payload)

    def delete_task(self, task_id: str) -> bool:
        return self._repository.delete_task(task_id)

    def update_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
        return self._repository.update_task_status(task_id, status)

    def update_task_schedule(
        self,
        task_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> Task | None:
        return self._repository.update_task_schedule(task_id, start_at, end_at)

    def list_events(self) -> list[Event]:
        return self._repository.list_events()

    def create_event(self, payload: EventCreate) -> Event:
        validate_event_knowledge(payload)
        return self._repository.create_event(payload)

    def is_schedule_dirty(self) -> bool:
        return self._repository.is_schedule_dirty()

    def set_schedule_dirty(self, value: bool) -> None:
        self._repository.set_schedule_dirty(value)
