from datetime import datetime, timedelta, timezone
from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.knowledge.models import Task


def test_bootstrap_model_initializes_and_predicts() -> None:
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    # После бутстрапа модель готова, можно предсказывать
    task = Task(title="Test", estimated_minutes=60, priority=2,
                deadline=datetime.now(timezone.utc) + timedelta(days=1),
                workspace_id="study")
    score = scoring.score_single_task(task, [], datetime.now(timezone.utc))
    assert isinstance(score, float)
    assert 0.0 <= score <= 200.0


def test_initial_target_bounds() -> None:
    # Экстремальные значения
    target = MLScoringService._initial_target(free_minutes=0, priority=1, estimated_minutes=0)
    assert target == 200.0  # max clamped
    target = MLScoringService._initial_target(free_minutes=1e6, priority=4, estimated_minutes=9999)
    assert target == 0.0    # min clamped


def test_build_score_map_empty() -> None:
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    score_map = scoring.build_score_map([], [], datetime.now(timezone.utc))
    assert score_map == {}


def test_record_completed_feedback_overdue_bonus_increases_target() -> None:
    now = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    deadline = now - timedelta(hours=1)  # просрочена
    task = Task(title="Late", deadline=deadline, workspace_id="study")
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7, overdue_bonus=10.0)
    # base_score = 50
    retrained = scoring.record_completed_feedback(task, [], now, base_score=50.0)
    # только один сэмпл в пакете, retrain_batch_size=20 → retrained=False
    assert not retrained
    assert scoring.pending_samples_count == 1
    sample = scoring._pending_samples[0]
    assert sample.target == 60.0  # 50 + 10


def test_pending_samples_count_increments() -> None:
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7, retrain_batch_size=5)
    task = Task(title="Some", workspace_id="study")
    for _ in range(3):
        scoring.record_reorder_feedback(task, [], datetime.now(timezone.utc), target_score=100.0)
    assert scoring.pending_samples_count == 3
