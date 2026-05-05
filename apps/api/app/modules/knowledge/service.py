from __future__ import annotations

from datetime import datetime

from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate, TaskStatus
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.rules import (
    is_active_task,
    is_schedulable_task,
    validate_event_knowledge,
    validate_task_knowledge,
)


class KnowledgeService:
    """
    Service layer for working with the knowledge base.

    The repository is responsible for storing facts.
    This service is responsible for applying domain rules before
    facts are stored or interpreted by other modules.
    """

    def __init__(self, repository: KnowledgeRepository) -> None:
        self._repository = repository

    def list_tasks(self) -> list[Task]:
        """
        Return all task facts stored in the knowledge base.
        """
        return self._repository.list_tasks()

    def list_active_tasks(self) -> list[Task]:
        """
        Return tasks that are still relevant for the user.

        Completed and cancelled tasks remain stored in the knowledge base,
        but they are not considered active work items.
        """
        return [task for task in self._repository.list_tasks() if is_active_task(task)]

    def list_schedulable_tasks(self) -> list[Task]:
        """
        Return tasks that may be considered by a planner.

        Blocked, completed and cancelled tasks are excluded.
        """
        return [
            task
            for task in self._repository.list_tasks()
            if is_schedulable_task(task)
        ]

    def get_task(self, task_id: str) -> Task | None:
        """
        Return a task by its identifier.
        """
        return self._repository.get_task(task_id)

    def create_task(self, payload: TaskCreate) -> Task:
        """
        Validate and store a new task fact.

        The validation is part of the knowledge base logic:
        it prevents contradictory or inconsistent task facts.
        """
        validate_task_knowledge(payload)
        return self._repository.create_task(payload)

    def update_task_status(self, task_id: str, status: TaskStatus) -> Task | None:
        """
        Update task status.

        Status itself is validated by Pydantic and database constraints.
        This method keeps status changes inside the knowledge service layer.
        """
        return self._repository.update_task_status(task_id, status)

    def update_task_schedule(
        self,
        task_id: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> Task | None:
        """
        Update scheduled time for a task.

        This method is kept in the knowledge service because schedule
        information is also part of the task fact stored in the knowledge base.
        """
        return self._repository.update_task_schedule(task_id, start_at, end_at)

    def list_events(self) -> list[Event]:
        """
        Return all event facts stored in the knowledge base.
        """
        return self._repository.list_events()

    def create_event(self, payload: EventCreate) -> Event:
        """
        Validate and store a new event fact.

        Events represent busy time intervals, therefore their start and end
        timestamps must be logically consistent.
        """
        validate_event_knowledge(payload)
        return self._repository.create_event(payload)

    def is_schedule_dirty(self) -> bool:
        """
        Return whether the schedule should be recalculated.
        """
        return self._repository.is_schedule_dirty()

    def set_schedule_dirty(self, value: bool) -> None:
        """
        Mark schedule state as actual or requiring recalculation.
        """
        self._repository.set_schedule_dirty(value)
