from datetime import datetime, timedelta, timezone
from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.knowledge.models import Task


def test_bootstrap_model_initializes_and_predicts_with_five_features() -> None:
    """После бутстрепа модель готова и учитывает все 5 признаков."""
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    # Явно вызывать _bootstrap_model не нужно, он уже в __init__
    task = Task(
        title="Test",
        description="Сделать лабораторную по ООП",
        estimated_minutes=180,
        priority=2,
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        workspace_id="study",
    )
    score = scoring.score_single_task(task, [], datetime.now(timezone.utc))
    assert isinstance(score, float)
    assert 0.0 <= score <= 1000.0


def test_workspace_weight_starts_at_zero_and_accumulates() -> None:
    """Вес неизвестного workspace = 0, после фидбека вес вычисляется как среднее целевых скоров."""
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    assert scoring._get_workspace_weight("study") == 0.0

    task = Task(title="Task", workspace_id="study")
    # Записываем два completed-фидбека с разными target
    scoring.record_completed_feedback(
        task, [], datetime.now(timezone.utc), base_score=50.0,
    )
    scoring.record_completed_feedback(
        task, [], datetime.now(timezone.utc), base_score=80.0,
    )
    # Средний целевой скор = (50 + 80) / 2 = 65
    assert scoring._get_workspace_weight("study") == 65.0

    # Новый workspace всё ещё 0
    assert scoring._get_workspace_weight("work") == 0.0


def test_initial_target_includes_description_length() -> None:
    """Начальная формула учитывает длину описания."""
    target_long = MLScoringService._initial_target(
        free_minutes=1000.0, priority=2, estimated_minutes=90.0, description_length=500.0
    )
    target_short = MLScoringService._initial_target(
        free_minutes=1000.0, priority=2, estimated_minutes=90.0, description_length=0.0
    )
    assert target_long > target_short  # Подробная задача должна получить больше скора


def test_record_completed_feedback_with_max_active_score() -> None:
    """Завершение задачи с более приоритетным лидером увеличивает скор."""
    now = datetime(2026, 5, 3, 10, 0, tzinfo=timezone.utc)
    task = Task(title="Later", workspace_id="study", deadline=now + timedelta(hours=5))
    scoring = MLScoringService(
        wake_start_hour=8, wake_end_hour=22, horizon_days=7, overdue_bonus=10.0
    )
    # Задача имела base_score=30, но есть лидер с max_active_score=100
    scoring.record_completed_feedback(task, [], now, base_score=30.0, max_active_score=100.0)
    sample = scoring._pending_samples[0]
    # target = max_score + 0.5*(max_score - base_score) = 100 + 35 = 135
    assert sample.target == 135.0


def test_record_completed_feedback_overdue_superbonus_with_leader() -> None:
    """Просроченная задача получает бонус с учётом дней опоздания и лидера."""
    now = datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc)
    deadline = now - timedelta(days=2)  # просрочена на 2 дня
    task = Task(title="Overdue", deadline=deadline, workspace_id="study")
    scoring = MLScoringService(
        wake_start_hour=8, wake_end_hour=22, horizon_days=7, overdue_bonus=10.0
    )
    scoring.record_completed_feedback(
        task, [], now, base_score=40.0, max_active_score=40.0
    )
    sample = scoring._pending_samples[0]
    # dynamic_bonus = 10 * (1 + 2) = 30, max=40 -> target = 40 + 30 = 70
    assert sample.target == 70.0


def test_pending_samples_count_and_batch_retrain() -> None:
    """При накоплении batch_size происходит дообучение."""
    scoring = MLScoringService(
        wake_start_hour=8, wake_end_hour=22, horizon_days=7, retrain_batch_size=2
    )
    task = Task(title="Batch", workspace_id="study")
    # Добавляем 2 фидбека – должно хватить для переобучения
    retrained1 = scoring.record_completed_feedback(task, [], datetime.now(timezone.utc), base_score=100.0)
    retrained2 = scoring.record_completed_feedback(task, [], datetime.now(timezone.utc), base_score=200.0)
    # После второго вызова partial_fit должен выполниться
    assert not retrained1
    assert retrained2
    assert scoring.pending_samples_count == 0


def test_task_features_vector_length() -> None:
    """Убедиться, что вектор признаков имеет 5 элементов."""
    scoring = MLScoringService(wake_start_hour=8, wake_end_hour=22, horizon_days=7)
    task = Task(title="Feat", workspace_id="study")
    features = scoring._task_features(task, [], datetime.now(timezone.utc))
    assert len(features) == 5
