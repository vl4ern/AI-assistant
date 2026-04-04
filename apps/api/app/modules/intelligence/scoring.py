from __future__ import annotations

from datetime import datetime, timezone

from app.modules.knowledge.models import Task


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def score_task(task: Task, now: datetime) -> float:
    current = _to_utc(now)

    priority_score = (5 - task.priority) * 20

    if task.deadline is None:
        urgency_score = 25
    else:
        hours_left = (_to_utc(task.deadline) - current).total_seconds() / 3600
        if hours_left <= 0:
            urgency_score = 120
        elif hours_left <= 24:
            urgency_score = 95
        elif hours_left <= 72:
            urgency_score = 70
        else:
            urgency_score = 40

    dependency_penalty = len(task.depends_on) * 5
    return float(priority_score + urgency_score - dependency_penalty)
