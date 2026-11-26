from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.modules.knowledge.models import Task


class ScheduledSlot(BaseModel):
    """Один запланированный интервал выполнения задачи."""
    task_id: str
    title: str
    start_at: datetime
    end_at: datetime
    score: float


class SchedulePlan(BaseModel):
    """Результат работы планировщика."""
    generated_at: datetime
    slots: list[ScheduledSlot]
    unscheduled_task_ids: list[str]
    prime_task_id: str | None


class TodayView(BaseModel):
    """Представление задач на текущий день."""
    date: str
    prime_task_id: str | None
    tasks: list[Task]
    schedule_dirty: bool


class ReorderFeedbackRequest(BaseModel):
    """Запрос на запись обратной связи о ручном переупорядочивании задач."""
    moved_task_id: str
    left_task_id: Optional[str] = None
    right_task_id: Optional[str] = None
    moved_at: Optional[datetime] = None


class ReorderFeedbackResult(BaseModel):
    """Ответ на запрос обратной связи."""
    moved_task_id: str
    target_score: float
    samples_in_batch: int
    retrained: bool
