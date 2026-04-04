from __future__ import annotations

from datetime import datetime, timezone

from app.modules.intelligence.models import SchedulePlan, TodayView
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.knowledge.repository import KnowledgeRepository


class SchedulerService:
    def __init__(self, repository: KnowledgeRepository, scheduler: GreedyScheduler) -> None:
        self.repository = repository
        self.scheduler = scheduler

    def rebuild(self) -> SchedulePlan:
        tasks = self.repository.list_tasks()
        events = self.repository.list_events()

        for task in tasks:
            if task.auto_reschedule and task.status in {"todo", "in_progress"}:
                self.repository.update_task_schedule(task.id, None, None)

        plan = self.scheduler.build_plan(tasks=tasks, events=events, now=datetime.now(timezone.utc))

        for slot in plan.slots:
            self.repository.update_task_schedule(slot.task_id, slot.start_at, slot.end_at)

        self.repository.set_schedule_dirty(False)
        return plan

    def today(self) -> TodayView:
        current = datetime.now(timezone.utc)
        date_value = current.date().isoformat()

        tasks = [
            task
            for task in self.repository.list_tasks()
            if task.scheduled_start and task.scheduled_start.date().isoformat() == date_value
        ]
        tasks.sort(key=lambda item: item.scheduled_start)

        prime_task_id = tasks[0].id if tasks else None

        return TodayView(
            date=date_value,
            prime_task_id=prime_task_id,
            tasks=tasks,
            schedule_dirty=self.repository.is_schedule_dirty(),
        )
