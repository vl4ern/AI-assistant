from datetime import datetime, timedelta, timezone

from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.knowledge.models import Event, Task


def test_scheduler_places_high_priority_before_low_priority() -> None:
    now = datetime(2026, 4, 4, 8, 0, tzinfo=timezone.utc)

    tasks = [
        Task(
            title="Low",
            estimated_minutes=60,
            priority=4,
            deadline=now + timedelta(days=2),
            workspace_id="study",
        ),
        Task(
            title="High",
            estimated_minutes=60,
            priority=1,
            deadline=now + timedelta(days=1),
            workspace_id="study",
        ),
    ]

    events = [
        Event(
            title="Lecture",
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=4),
        )
    ]

    scheduler = GreedyScheduler(
        slot_minutes=30,
        horizon_days=2,
        wake_start_hour=8,
        wake_end_hour=22,
    )
    plan = scheduler.build_plan(tasks=tasks, events=events, now=now)

    assert len(plan.slots) == 2
    assert plan.slots[0].title == "High"
    assert plan.prime_task_id == plan.slots[0].task_id
