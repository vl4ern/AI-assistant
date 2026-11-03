from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TaskDraft(BaseModel):
    """
    Черновик задачи, распознанный локальной моделью.

    Это не факт базы знаний: черновик возвращается пользователю для
    проверки и сохраняется только явным вызовом POST /v1/tasks.
    """

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    estimated_minutes: int = Field(default=60, ge=15, le=24 * 60)
    priority: int = Field(default=3, ge=1, le=4)
    deadline: datetime | None = None
    workspace_id: str = "study"
    project_id: str | None = None
    input_kind: Literal["text", "image"] = "text"
    warnings: list[str] = Field(default_factory=list)
