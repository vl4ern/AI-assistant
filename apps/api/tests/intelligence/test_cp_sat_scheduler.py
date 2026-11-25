from datetime import datetime, timedelta, timezone

from app.modules.intelligence.cp_sat_scheduler import CpSatScheduler
from app.modules.knowledge.models import Event, Task


def _scheduler(**overrides) -> CpSatScheduler:
    params = {
        "slot_minutes": 30,
        "horizon_days": 1,
        "wake_start_hour": 8,
        "wake_end_hour": 22,
        "max_time_in_seconds": 5,
    }
    params.update(overrides)
    return CpSatScheduler(**params)


def test_cp_sat_places_high_priority_before_low_priority() -> None:
    now = datetime(2026, 4, 4, 8, 0, tzinfo=timezone.utc)
    low = Task(
        title="Low",
        estimated_minutes=60,
        priority=4,
        deadline=now + timedelta(days=2),
        workspace_id="study",
    )
    high = Task(
        title="High",
        estimated_minutes=60,
        priority=1,
        deadline=now + timedelta(days=1),
        workspace_id="study",
    )
    event = Event(
        title="Lecture",
        start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=4),
    )

    plan = _scheduler(horizon_days=2).build_plan(
        tasks=[low, high],
        events=[event],
        now=now,
        task_scores={low.id: 10.0, high.id: 100.0},
    )

    assert len(plan.slots) == 2
    assert plan.slots[0].title == "High"
    assert plan.prime_task_id == plan.slots[0].task_id


def test_cp_sat_prefers_two_medium_tasks_over_one_long_high_score() -> None:
    """Жадный алгоритм взял бы Long, CP-SAT должен максимизировать сумму."""
    now = datetime(2026, 4, 4, 8, 0, tzinfo=timezone.utc)
    long_task = Task(title="Long", estimated_minutes=120, workspace_id="study")
    medium_a = Task(title="Medium-A", estimated_minutes=60, workspace_id="study")
    medium_b = Task(title="Medium-B", estimated_minutes=60, workspace_id="study")

    plan = _scheduler(wake_end_hour=10).build_plan(
        tasks=[long_task, medium_a, medium_b],
        events=[],
        now=now,
        task_scores={long_task.id: 100.0, medium_a.id: 70.0, medium_b.id: 70.0},
    )

    scheduled_titles = {slot.title for slot in plan.slots}
    assert scheduled_titles == {"Medium-A", "Medium-B"}
    assert long_task.id in plan.unscheduled_task_ids


def test_cp_sat_splits_when_whole_task_cannot_fit() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(
        title="Big",
        estimated_minutes=180,
        deadline=now + timedelta(hours=4),
        allow_split=True,
        min_chunk_minutes=60,
        workspace_id="study",
    )
    events = [
        Event(
            title="Busy-1",
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
        ),
        Event(
            title="Busy-2",
            start_at=now + timedelta(hours=3),
            end_at=now + timedelta(hours=4),
        ),
    ]

    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[task],
        events=events,
        now=now,
        task_scores={task.id: 100.0},
    )

    assert len(plan.slots) == 2
    assert plan.unscheduled_task_ids == [task.id]


def test_cp_sat_prefers_whole_block_when_it_fits() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(
        title="Splittable",
        estimated_minutes=120,
        allow_split=True,
        min_chunk_minutes=30,
        workspace_id="study",
    )

    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[task],
        events=[],
        now=now,
        task_scores={task.id: 100.0},
    )

    assert len(plan.slots) == 1
    assert plan.slots[0].start_at == now
    assert plan.slots[0].end_at == now + timedelta(minutes=120)
    assert plan.unscheduled_task_ids == []


def test_cp_sat_does_not_schedule_only_short_remainder() -> None:
    """Короткий остаток нельзя ставить без всех полноразмерных кусков."""
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(
        title="Ninety",
        estimated_minutes=90,
        allow_split=True,
        min_chunk_minutes=60,
        workspace_id="study",
    )
    # Оставляем только 30 свободных минут: целый кусок на 60 не влезает.
    event = Event(
        title="Busy",
        start_at=now + timedelta(minutes=30),
        end_at=now + timedelta(hours=4),
    )

    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[task],
        events=[event],
        now=now,
        task_scores={task.id: 100.0},
    )

    assert plan.slots == []
    assert plan.unscheduled_task_ids == [task.id]


def test_cp_sat_respects_deadline() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    too_late = Task(
        title="TooLate",
        estimated_minutes=120,
        deadline=now + timedelta(hours=1),
        workspace_id="study",
    )
    in_time = Task(
        title="InTime",
        estimated_minutes=60,
        deadline=now + timedelta(hours=1),
        workspace_id="study",
    )

    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[too_late, in_time],
        events=[],
        now=now,
        task_scores={too_late.id: 100.0, in_time.id: 50.0},
    )

    assert [slot.title for slot in plan.slots] == ["InTime"]
    assert plan.slots[0].end_at <= in_time.deadline
    assert too_late.id in plan.unscheduled_task_ids


def test_cp_sat_blocks_dependent_until_blocker_completed() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    blocker = Task(title="Blocker", estimated_minutes=60, workspace_id="study")
    dependent = Task(
        title="Dependent",
        estimated_minutes=60,
        workspace_id="study",
        depends_on=[blocker.id],
    )

    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[dependent, blocker],
        events=[],
        now=now,
        task_scores={dependent.id: 100.0, blocker.id: 50.0},
    )

    scheduled_ids = {slot.task_id for slot in plan.slots}
    assert dependent.id not in scheduled_ids
    assert blocker.id in scheduled_ids

    blocker.status = "completed"
    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[dependent, blocker],
        events=[],
        now=now,
        task_scores={dependent.id: 100.0, blocker.id: 50.0},
    )

    scheduled_ids = {slot.task_id for slot in plan.slots}
    assert dependent.id in scheduled_ids
    assert blocker.id not in scheduled_ids


def test_cp_sat_respects_events_and_fixed_tasks() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    fixed = Task(
        title="Fixed",
        estimated_minutes=30,
        scheduled_start=now,
        scheduled_end=now + timedelta(minutes=30),
        auto_reschedule=False,
        workspace_id="study",
    )
    event = Event(
        title="Meeting",
        start_at=now + timedelta(hours=1),
        end_at=now + timedelta(hours=2),
    )
    movable = Task(
        title="Movable",
        estimated_minutes=60,
        workspace_id="study",
    )

    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[fixed, movable],
        events=[event],
        now=now,
        task_scores={fixed.id: 10.0, movable.id: 100.0},
    )

    movable_slot = next(slot for slot in plan.slots if slot.task_id == movable.id)
    assert (
        movable_slot.start_at >= fixed.scheduled_end
        or movable_slot.end_at <= fixed.scheduled_start
    )
    assert (
        movable_slot.start_at >= event.end_at
        or movable_slot.end_at <= event.start_at
    )


def test_cp_sat_empty_tasks() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    plan = _scheduler().build_plan([], [], now)
    assert plan.slots == []
    assert plan.unscheduled_task_ids == []
    assert plan.prime_task_id is None


def test_cp_sat_all_unscheduled_when_no_free_time() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(title="Task", estimated_minutes=60, workspace_id="study")
    event = Event(
        title="AllDay",
        start_at=now,
        end_at=now + timedelta(hours=14),
    )

    plan = _scheduler(wake_end_hour=22).build_plan(
        tasks=[task],
        events=[event],
        now=now,
        task_scores={task.id: 100.0},
    )

    assert plan.slots == []
    assert plan.unscheduled_task_ids == [task.id]


def test_cp_sat_falls_back_to_greedy_without_ortools(monkeypatch) -> None:
    import app.modules.intelligence.cp_sat_scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "cp_model", None)

    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(title="Fallback", estimated_minutes=60, workspace_id="study")

    plan = _scheduler(wake_end_hour=12).build_plan(
        tasks=[task],
        events=[],
        now=now,
        task_scores={task.id: 100.0},
    )

    assert len(plan.slots) == 1
    assert plan.slots[0].start_at == now
    assert plan.unscheduled_task_ids == []
