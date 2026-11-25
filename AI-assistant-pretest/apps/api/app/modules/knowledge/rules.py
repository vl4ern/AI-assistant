from __future__ import annotations

from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate


class KnowledgeRuleViolation(ValueError):
    """Raised when a knowledge base rule is violated."""


ACTIVE_TASK_STATUSES = {"todo", "in_progress", "blocked"}
SCHEDULABLE_TASK_STATUSES = {"todo", "in_progress"}


def is_active_task(task: Task) -> bool:
    """
    Return True if the task is still relevant for the knowledge base.

    Completed and cancelled tasks remain stored as facts,
    but they are not considered active work items.
    """
    return task.status in ACTIVE_TASK_STATUSES


def is_schedulable_task(task: Task) -> bool:
    """
    Return True if the task may be considered for scheduling.

    Blocked tasks are active knowledge facts, but they should not be
    placed into a schedule until their blocking condition is removed.
    """
    return task.status in SCHEDULABLE_TASK_STATUSES


def validate_task_dependencies(task: Task | TaskCreate) -> None:
    """
    Validate dependency facts for a task.

    Rules:
    - a task cannot depend on itself;
    - dependency identifiers should not be duplicated.
    """
    dependencies = task.depends_on

    if len(dependencies) != len(set(dependencies)):
        raise KnowledgeRuleViolation("Task dependencies must not contain duplicates.")

    task_id = getattr(task, "id", None)
    if task_id is not None and task_id in dependencies:
        raise KnowledgeRuleViolation("A task cannot depend on itself.")


def validate_split_settings(task: Task | TaskCreate) -> None:
    """
    Validate task splitting settings.

    Rules:
    - if splitting is disabled, min_chunk_minutes is not required;
    - if splitting is enabled, min_chunk_minutes must be defined;
    - min_chunk_minutes must not be greater than estimated_minutes.
    """
    if not task.allow_split:
        return

    if task.min_chunk_minutes is None:
        raise KnowledgeRuleViolation(
            "min_chunk_minutes must be specified when allow_split is enabled."
        )

    if task.min_chunk_minutes > task.estimated_minutes:
        raise KnowledgeRuleViolation(
            "min_chunk_minutes must not be greater than estimated_minutes."
        )


def validate_event_interval(event: Event | EventCreate) -> None:
    """
    Validate an event as a busy time interval.

    Rule:
    - event end time must be later than event start time.
    """
    if event.end_at <= event.start_at:
        raise KnowledgeRuleViolation("Event end_at must be later than start_at.")


def validate_task_knowledge(task: Task | TaskCreate) -> None:
    """
    Validate a task as a knowledge base fact.

    This function combines task-related rules that are not only technical
    constraints, but also part of the domain model.
    """
    validate_task_dependencies(task)
    validate_split_settings(task)


def validate_event_knowledge(event: Event | EventCreate) -> None:
    """
    Validate an event as a knowledge base fact.
    """
    validate_event_interval(event)
