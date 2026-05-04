from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from .models import Event, EventCreate, Task, TaskCreate, TaskStatus
from .repository import KnowledgeRepository


class InMemoryKnowledgeRepository(KnowledgeRepository):
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._events: dict[str, Event] = {}
        self._schedule_dirty: bool = True
        self._lock = Lock()

    def list_tasks(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def create_task(self, payload: TaskCreate) -> Task:
        with self._lock:
            item = Task(**payload.model_dump())
            self._tasks[item.id] = item
            self._schedule_dirty = True
            return item

    def update_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
        with self._lock:
            item = self._tasks.get(task_id)
            if item is None:
                return None
            item.status = status
            item.updated_at = datetime.now(timezone.utc)
            self._schedule_dirty = True
            return item

    def update_task_schedule(
        self,
        task_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> Task | None:
        with self._lock:
            item = self._tasks.get(task_id)
            if item is None:
                return None
            item.scheduled_start = start_at
            item.scheduled_end = end_at
            item.updated_at = datetime.now(timezone.utc)
            return item

    def list_events(self) -> list[Event]:
        with self._lock:
            return list(self._events.values())

    def create_event(self, payload: EventCreate) -> Event:
        with self._lock:
            item = Event(**payload.model_dump())
            self._events[item.id] = item
            self._schedule_dirty = True
            return item

    def is_schedule_dirty(self) -> bool:
        with self._lock:
            return self._schedule_dirty

    def set_schedule_dirty(self, value: bool) -> None:
        with self._lock:
            self._schedule_dirty = value
