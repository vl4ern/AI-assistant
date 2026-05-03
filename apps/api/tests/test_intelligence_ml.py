from datetime import datetime, timedelta, timezone

from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.intelligence.models import ReorderFeedbackRequest
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.intelligence.service import SchedulerService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate


def test_time_to_deadline_free_minutes_excludes_sleep_and_events() -> None:
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    task = Task(title="Task", deadline=now + timedelta(hours=12), workspace_id="study")
    events = [
        Event(
            title="Lecture",
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=4),
        )
    ]

    scoring = MLScoringService(
        wake_start_hour=8,
        wake_end_hour=22,
        horizon_days=7,
        retrain_batch_size=20,
        overdue_bonus=10,
    )

    free_minutes = scoring._time_to_deadline_free_minutes(task=task, events=events, now=now)
    assert free_minutes == 600.0


def test_dependency_rule_updates_dependent_and_blocker_scores() -> None:
    blocker = Task(title="Blocker", workspace_id="study")
    dependent = Task(title="Dependent", workspace_id="study", depends_on=[blocker.id])

    scoring = MLScoringService(
        wake_start_hour=8,
        wake_end_hour=22,
        horizon_days=7,
    )
    score_map = {
        dependent.id: 40.0,
        blocker.id: 10.0,
    }

    scoring._apply_dependency_rules(tasks=[dependent, blocker], score_map=score_map)

    assert score_map[dependent.id] == 25.0
    assert score_map[blocker.id] == 26.0


def test_scheduler_splits_when_whole_task_cannot_fit() -> None:
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

    scheduler = GreedyScheduler(
        slot_minutes=30,
        horizon_days=1,
        wake_start_hour=8,
        wake_end_hour=12,
    )

    plan = scheduler.build_plan(
        tasks=[task],
        events=events,
        now=now,
        task_scores={task.id: 100.0},
    )

    assert len(plan.slots) == 2
    assert plan.unscheduled_task_ids == [task.id]


def test_reorder_feedback_uses_neighbor_average_target() -> None:
    now = datetime.now(timezone.utc)
    repository = InMemoryKnowledgeRepository()
    a = repository.create_task(TaskCreate(title="A", workspace_id="study"))
    b = repository.create_task(TaskCreate(title="B", workspace_id="study"))
    c = repository.create_task(TaskCreate(title="C", workspace_id="study"))

    scheduler = GreedyScheduler(
        slot_minutes=30,
        horizon_days=1,
        wake_start_hour=8,
        wake_end_hour=22,
    )
    scoring = MLScoringService(
        wake_start_hour=8,
        wake_end_hour=22,
        horizon_days=7,
        retrain_batch_size=20,
    )
    scoring.last_scores = {a.id: 10.0, b.id: 20.0, c.id: 50.0}

    service = SchedulerService(
        repository=repository,
        scheduler=scheduler,
        scoring_service=scoring,
    )

    result = service.record_reorder_feedback(
        ReorderFeedbackRequest(
            moved_task_id=b.id,
            left_task_id=a.id,
            right_task_id=c.id,
            moved_at=now,
        )
    )

    assert result.target_score == 30.0
    assert result.samples_in_batch == 1
    assert result.retrained is False


def test_integration_rebuild_today_reorder_completion_retrains_batch() -> None:
    now = datetime.now(timezone.utc)

    repository = InMemoryKnowledgeRepository()
    repository.create_event(
        EventCreate(
            title="Class",
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            source="manual",
        )
    )

    t1 = repository.create_task(
        TaskCreate(
            title="Task-1",
            workspace_id="study",
            priority=1,
            estimated_minutes=60,
            deadline=now + timedelta(hours=5),
        )
    )
    t2 = repository.create_task(
        TaskCreate(
            title="Task-2",
            workspace_id="study",
            priority=2,
            estimated_minutes=60,
            deadline=now + timedelta(hours=7),
        )
    )

    scheduler = GreedyScheduler(
        slot_minutes=30,
        horizon_days=2,
        wake_start_hour=8,
        wake_end_hour=23,
    )
    scoring = MLScoringService(
        wake_start_hour=8,
        wake_end_hour=23,
        horizon_days=7,
        retrain_batch_size=2,
        overdue_bonus=10,
    )

    service = SchedulerService(
        repository=repository,
        scheduler=scheduler,
        scoring_service=scoring,
    )

    plan = service.rebuild()
    assert plan.slots

    today = service.today()
    assert today.schedule_dirty is False

    service.record_reorder_feedback(
        ReorderFeedbackRequest(
            moved_task_id=t1.id,
            left_task_id=t2.id,
            moved_at=now,
        )
    )

    completed = repository.update_task_status(t1.id, "completed")
    assert completed is not None
    service.on_task_status_updated(completed)

    assert scoring.pending_samples_count == 0
    assert scoring._is_fitted or scoring._model is None
