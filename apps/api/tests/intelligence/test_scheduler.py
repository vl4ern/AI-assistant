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
    plan = scheduler.build_plan(
        tasks=tasks,
        events=events,
        now=now,
        task_scores={
            tasks[0].id: 10.0,   # Low
            tasks[1].id: 100.0,  # High
        },
    )

    assert len(plan.slots) == 2
    assert plan.slots[0].title == "High"
    assert plan.prime_task_id == plan.slots[0].task_id


def test_build_plan_empty_tasks() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    plan = scheduler.build_plan([], [], now)
    assert plan.slots == []
    assert plan.unscheduled_task_ids == []
    assert plan.prime_task_id is None


def test_task_without_deadline_uses_horizon_end() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(title="NoDeadline", estimated_minutes=60, workspace_id="study")
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    plan = scheduler.build_plan([task], [], now, {task.id: 100.0})
    assert len(plan.slots) == 1
    # Должно разместиться в первом окне этого дня
    assert plan.slots[0].start_at == now
    assert plan.slots[0].end_at == now + timedelta(minutes=60)


def test_task_blocked_by_dependency_not_scheduled() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    blocker = Task(title="Blocker", workspace_id="study")
    dependent = Task(title="Dependent", workspace_id="study", depends_on=[blocker.id])
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    plan = scheduler.build_plan(
        [dependent, blocker], [], now,
        {dependent.id: 100.0, blocker.id: 50.0}
    )
    # Блокирующая ещё не завершена → зависимая не должна планироваться
    scheduled_ids = {slot.task_id for slot in plan.slots}
    assert dependent.id not in scheduled_ids
    assert blocker.id in scheduled_ids


def test_unschedulable_task_goes_to_unscheduled() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(title="Huge", estimated_minutes=900, workspace_id="study")
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    plan = scheduler.build_plan([task], [], now, {task.id: 100.0})
    assert len(plan.slots) == 0
    assert task.id in plan.unscheduled_task_ids


def test_fixed_busy_intervals_from_events_and_non_movable_tasks() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    non_movable = Task(
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
    movable_task = Task(
        title="Movable",
        estimated_minutes=60,
        workspace_id="study",
        auto_reschedule=True,
    )
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    plan = scheduler.build_plan(
        [non_movable, movable_task], [event], now,
        {non_movable.id: 10.0, movable_task.id: 100.0}
    )
    # movable должна встать до или после этих занятых интервалов, но не встык с ними
    movable_slot = next(s for s in plan.slots if s.task_id == movable_task.id)
    # Проверим отсутствие пересечения с non_movable
    assert movable_slot.start_at >= non_movable.scheduled_end or movable_slot.end_at <= non_movable.scheduled_start
    # Проверим отсутствие пересечения с event
    assert movable_slot.start_at >= event.end_at or movable_slot.end_at <= event.start_at


def test_allocate_window_respects_latest_end() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    free_windows = [(now, now + timedelta(hours=10))]
    # Задача с дедлайном через 1 час, а нужно 90 минут – должна не влезть
    result = scheduler._allocate_window(free_windows, 90, now + timedelta(hours=1))
    assert result is None
    # А 30 минут должна влезть
    result = scheduler._allocate_window(free_windows, 30, now + timedelta(hours=1))
    assert result == (now, now + timedelta(minutes=30))


def test_allocate_window_consumes_whole_window() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    free_windows = [(now, now + timedelta(minutes=30))]
    result = scheduler._allocate_window(free_windows, 30, now + timedelta(hours=10))
    assert result == (now, now + timedelta(minutes=30))
    assert len(free_windows) == 0


def test_allocate_split_windows_returns_remaining_when_not_enough() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    free_windows = [(now, now + timedelta(minutes=60))]
    slots, remaining = scheduler._allocate_split_windows(
        free_windows, total_minutes=120, latest_end=now+timedelta(hours=10), min_chunk_minutes=60
    )
    assert len(slots) == 1
    assert remaining == 60


def test_normalize_intervals_discards_none_and_invalid() -> None:
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    intervals = [
        (None, datetime(2026,1,1)),
        (datetime(2026,1,1), None),
        (datetime(2026,1,2), datetime(2026,1,1)),  # end <= start
    ]
    result = scheduler._normalize_intervals(intervals)
    assert result == []


def test_subtract_interval_middle() -> None:
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    window = [(datetime(2026,1,1,8,0), datetime(2026,1,1,22,0))]
    busy_start = datetime(2026,1,1,10,0)
    busy_end   = datetime(2026,1,1,12,0)
    result = scheduler._subtract_interval(window, busy_start, busy_end)
    assert len(result) == 2
    assert result[1] == (datetime(2026,1,1,12,0), datetime(2026,1,1,22,0))


def test_round_up_to_slot() -> None:
    scheduler = GreedyScheduler(slot_minutes=15, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    assert scheduler._round_up_to_slot(0) == 0
    assert scheduler._round_up_to_slot(13) == 15
    assert scheduler._round_up_to_slot(15) == 15
    assert scheduler._round_up_to_slot(16) == 30
