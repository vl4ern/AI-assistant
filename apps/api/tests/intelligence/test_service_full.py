from datetime import datetime, timedelta, timezone
import pytest
from app.modules.intelligence.service import SchedulerService
from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.intelligence.models import ReorderFeedbackRequest
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.models import TaskCreate, EventCreate


def test_rebuild_clears_dirty_flag() -> None:
    repo = InMemoryKnowledgeRepository()
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    service = SchedulerService(repo, scheduler, scoring)
    # repo по умолчанию помечает расписание как dirty после создания задачи
    repo.create_task(TaskCreate(title="Task", workspace_id="study", estimated_minutes=60))
    assert repo.is_schedule_dirty()
    service.rebuild()
    assert not repo.is_schedule_dirty()


def test_today_when_no_tasks() -> None:
    repo = InMemoryKnowledgeRepository()
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    service = SchedulerService(repo, scheduler, scoring)
    today = service.today()
    assert today.tasks == []
    assert today.prime_task_id is None


def test_today_sorts_by_start() -> None:
    now = datetime.now(timezone.utc)
    repo = InMemoryKnowledgeRepository()
    
    t1 = repo.create_task(
        TaskCreate(title="Later", workspace_id="study")
    )
    t2 = repo.create_task(
        TaskCreate(title="Earlier", workspace_id="study")
    )
    repo.update_task_schedule(t1.id, now + timedelta(hours=2), now + timedelta(hours=3))
    repo.update_task_schedule(t2.id, now + timedelta(hours=1), now + timedelta(hours=2))
    
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    service = SchedulerService(repo, scheduler, scoring)
    today = service.today()
    titles = [task.title for task in today.tasks]
    assert titles == ["Earlier", "Later"]

def test_on_task_status_updated_ignores_non_completed() -> None:
    repo = InMemoryKnowledgeRepository()
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    service = SchedulerService(repo, scheduler, scoring)
    task = repo.create_task(TaskCreate(title="InProgress", workspace_id="study"))
    task.status = "in_progress"
    service.on_task_status_updated(task)
    assert scoring.pending_samples_count == 0


def test_on_task_status_updated_duplicate_completion_not_re_recorded() -> None:
    repo = InMemoryKnowledgeRepository()
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7, retrain_batch_size=20)
    service = SchedulerService(repo, scheduler, scoring)
    task = repo.create_task(TaskCreate(title="Done", workspace_id="study"))
    task.status = "completed"
    task.updated_at = datetime.now(timezone.utc)
    # первый вызов
    service.on_task_status_updated(task)
    assert scoring.pending_samples_count == 1
    # повторный вызов с тем же updated_at не должен добавить сэмпл
    service.on_task_status_updated(task)
    assert scoring.pending_samples_count == 1


def test_record_reorder_feedback_moved_task_not_found() -> None:
    repo = InMemoryKnowledgeRepository()
    scheduler = GreedyScheduler(slot_minutes=30, horizon_days=1, wake_start_hour=8, wake_end_hour=22)
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    service = SchedulerService(repo, scheduler, scoring)
    with pytest.raises(ValueError, match="Moved task not found"):
        service.record_reorder_feedback(ReorderFeedbackRequest(moved_task_id="nonexistent"))
