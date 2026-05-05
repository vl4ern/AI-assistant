from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.knowledge.models import EventCreate, Task
from app.modules.knowledge.rules import (
    KnowledgeRuleViolation,
    is_active_task,
    is_schedulable_task,
    validate_event_knowledge,
    validate_task_knowledge,
)


def test_valid_event_passes_validation() -> None:
    event = EventCreate(
        title="Лекция",
        start_at=datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 5, 11, 35, tzinfo=timezone.utc),
        source="bsuir-lms",
    )

    validate_event_knowledge(event)


def test_event_with_invalid_time_interval_raises_error() -> None:
    event = EventCreate(
        title="Некорректное событие",
        start_at=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
        source="manual",
    )

    with pytest.raises(KnowledgeRuleViolation):
        validate_event_knowledge(event)


def test_task_dependencies_must_not_have_duplicates() -> None:
    task = Task(
        title="Подготовить отчёт",
        estimated_minutes=60,
        priority=2,
        depends_on=["task-1", "task-1"],
    )

    with pytest.raises(KnowledgeRuleViolation):
        validate_task_knowledge(task)


def test_task_cannot_depend_on_itself() -> None:
    task = Task(
        id="task-1",
        title="Подготовить отчёт",
        estimated_minutes=60,
        priority=2,
        depends_on=["task-1"],
    )

    with pytest.raises(KnowledgeRuleViolation):
        validate_task_knowledge(task)


def test_split_task_requires_min_chunk_minutes() -> None:
    task = Task(
        title="Большая задача",
        estimated_minutes=120,
        priority=2,
        allow_split=True,
        min_chunk_minutes=None,
    )

    with pytest.raises(KnowledgeRuleViolation):
        validate_task_knowledge(task)


def test_min_chunk_minutes_must_not_be_greater_than_estimated_minutes() -> None:
    task = Task(
        title="Большая задача",
        estimated_minutes=60,
        priority=2,
        allow_split=True,
        min_chunk_minutes=90,
    )

    with pytest.raises(KnowledgeRuleViolation):
        validate_task_knowledge(task)


def test_completed_task_is_not_active() -> None:
    task = Task(
        title="Завершённая задача",
        estimated_minutes=60,
        priority=2,
        status="completed",
    )

    assert is_active_task(task) is False


def test_blocked_task_is_active_but_not_schedulable() -> None:
    task = Task(
        title="Заблокированная задача",
        estimated_minutes=60,
        priority=2,
        status="blocked",
    )

    assert is_active_task(task) is True
    assert is_schedulable_task(task) is False


def test_todo_task_is_active_and_schedulable() -> None:
    task = Task(
        title="Обычная задача",
        estimated_minutes=60,
        priority=2,
        status="todo",
    )

    assert is_active_task(task) is True
    assert is_schedulable_task(task) is True
