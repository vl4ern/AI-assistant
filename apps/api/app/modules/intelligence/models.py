from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.modules.knowledge.models import Task


class ScheduledSlot(BaseModel):
    task_id: str
    title: str
    start_at: datetime
    end_at: datetime
    score: float


class SchedulePlan(BaseModel):
    generated_at: datetime
    slots: list[ScheduledSlot]
    unscheduled_task_ids: list[str]
    prime_task_id: str | None


class TodayView(BaseModel):
    date: str
    prime_task_id: str | None
    tasks: list[Task]
    schedule_dirty: bool
