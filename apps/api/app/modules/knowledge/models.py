from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

TaskStatus = Literal["todo", "in_progress", "completed", "cancelled", "blocked"]


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    estimated_minutes: int = Field(default=60, ge=15, le=24 * 60)
    priority: int = Field(default=3, ge=1, le=4)
    deadline: datetime | None = None
    workspace_id: str = Field(default="study")
    project_id: str | None = None
    auto_reschedule: bool = True
    depends_on: list[str] = Field(default_factory=list)


class TaskCreate(TaskBase):
    pass


class Task(TaskBase):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = "todo"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class EventBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    source: str = "manual"


class EventCreate(EventBase):
    pass


class Event(EventBase):
    id: str = Field(default_factory=lambda: str(uuid4()))
