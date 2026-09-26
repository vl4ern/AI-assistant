from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.modules.auth.models import User

from .models import Event, EventCreate, Task, TaskCreate, TaskStatus
from .models import SHARED_USER_ID
from .repository import KnowledgeRepository


def _visible_to(item_user_id: str, user_id: str) -> bool:
    return item_user_id in (user_id, SHARED_USER_ID)


class InMemoryKnowledgeRepository(KnowledgeRepository):
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._events: dict[str, Event] = {}
        self._users: dict[str, User] = {}
        self._schedule_dirty: bool = True
        self._lock = Lock()

    def list_tasks(self, user_id: str | None = None) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        if user_id is None:
            return tasks
        return [task for task in tasks if _visible_to(task.user_id, user_id)]

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

    def list_events(self, user_id: str | None = None) -> list[Event]:
        with self._lock:
            events = list(self._events.values())
        if user_id is None:
            return events
        return [event for event in events if _visible_to(event.user_id, user_id)]

    def create_event(self, payload: EventCreate) -> Event:
        with self._lock:
            item = Event(**payload.model_dump())
            self._events[item.id] = item
            self._schedule_dirty = True
            return item

    def create_user(
        self,
        username: str,
        password_hash: str,
        salt: str,
        user_id: str | None = None,
    ) -> User:
        with self._lock:
            user_data: dict[str, str] = {
                "username": username,
                "password_hash": password_hash,
                "salt": salt,
            }
            if user_id:
                user_data["id"] = user_id
            user = User(**user_data)
            self._users[user.id] = user
            return user

    def get_user_by_username(self, username: str) -> User | None:
        with self._lock:
            for user in self._users.values():
                if user.username == username:
                    return user
            return None

    def is_schedule_dirty(self) -> bool:
        with self._lock:
            return self._schedule_dirty

    def set_schedule_dirty(self, value: bool) -> None:
        with self._lock:
            self._schedule_dirty = value
