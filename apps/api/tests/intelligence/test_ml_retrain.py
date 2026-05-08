from datetime import datetime, timedelta, timezone
from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.intelligence.models import ReorderFeedbackRequest
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.intelligence.service import SchedulerService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate

def test_retrain_amplifies_priority_effect_naturally() -> None:
    """
    Модель учится, что задачи с высоким приоритетом должны иметь значительно больший скор.

    Стратегия:
    - Создаётся задача-лидер с экстремально высоким скором (дедлайн сейчас) и
      задача-аутсайдер с низким скором (без дедлайна, низкий приоритет, большая длительность).
    - "Высокоприоритетная" задача завершается на фоне лидера — получает целевой скор,
      близкий к лидеру.
    - "Низкоприоритетная" задача завершается на фоне аутсайдера — целевой скор остаётся низким.
    - После нескольких таких циклов модель переобучается и начинает сильнее разделять приоритеты.
    """
    scoring = MLScoringService(
        wake_start_hour=8, wake_end_hour=22, horizon_days=7, retrain_batch_size=10
    )
    now = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    events = []

    # Умеренно высокий лидер (deadline через 1 час)
    leader = Task(
        title="Leader", priority=1, estimated_minutes=15,
        deadline=now + timedelta(hours=1), workspace_id="study"
    )
    # Умеренно низкий аутсайдер
    outsider = Task(
        title="Outsider", priority=4, estimated_minutes=120,
        deadline=now + timedelta(days=30), workspace_id="study"
    )
    high_prio = Task(
        title="High", priority=1, estimated_minutes=60,
        deadline=now + timedelta(days=7), workspace_id="study"
    )
    low_prio = Task(
        title="Low", priority=4, estimated_minutes=60,
        deadline=now + timedelta(days=7), workspace_id="study"
    )

    initial_high = scoring.score_single_task(high_prio, events, now)
    initial_low = scoring.score_single_task(low_prio, events, now)
    initial_diff = initial_high - initial_low

    # Функция завершения с контекстом (чистые single scores)
    def complete(task, max_task, tasks_ctx):
        score_map = scoring.build_score_map(tasks_ctx, events, now)
        max_score = score_map.get(max_task.id, None)
        # Используем прямой предсказанный скор, а не из score_map
        base = scoring.score_single_task(task, events, now)
        scoring.record_completed_feedback(task, events, now, base, max_score)

    tasks = [leader, outsider, high_prio, low_prio]
    for _ in range(5):
        complete(high_prio, leader, tasks)
        # Контекст без лидера
        tasks_no_leader = [outsider, high_prio, low_prio]
        complete(low_prio, outsider, tasks_no_leader)

    assert scoring.pending_samples_count == 0, "Модель не переобучилась"

    final_high = scoring.score_single_task(high_prio, events, now)
    final_low = scoring.score_single_task(low_prio, events, now)
    final_diff = final_high - final_low

    assert final_diff > initial_diff, (
        f"Приоритет должен усилиться: было {initial_diff:.1f}, стало {final_diff:.1f}"
    )


def test_retrain_adapts_to_workspace_preference_naturally() -> None:
    """
    Демонстрирует, что после обучения на предпочтительном рабочем пространстве
    задачи из него получают более высокий скор.
    """
    scoring = MLScoringService(
        wake_start_hour=8, wake_end_hour=22, horizon_days=7, retrain_batch_size=10
    )
    now = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    events = []

    study_task = Task(
        title="Study", workspace_id="study", estimated_minutes=60,
        deadline=now + timedelta(days=2), priority=2
    )
    hobby_task = Task(
        title="Hobby", workspace_id="hobby", estimated_minutes=60,
        deadline=now + timedelta(days=2), priority=2
    )
    leader = Task(
        title="Leader", priority=1, estimated_minutes=15,
        deadline=now + timedelta(hours=1), workspace_id="study"
    )
    outsider = Task(
        title="Outsider", priority=4, estimated_minutes=120,
        deadline=now + timedelta(days=30), workspace_id="hobby"
    )

    initial_study = scoring.score_single_task(study_task, events, now)
    initial_hobby = scoring.score_single_task(hobby_task, events, now)
    initial_diff = initial_study - initial_hobby

    def complete(task, max_task, tasks_ctx):
        score_map = scoring.build_score_map(tasks_ctx, events, now)
        max_score = score_map.get(max_task.id, None)
        base = scoring.score_single_task(task, events, now)
        scoring.record_completed_feedback(task, events, now, base, max_score)

    tasks = [leader, outsider, study_task, hobby_task]
    for _ in range(5):
        complete(study_task, leader, tasks)
        tasks_no_leader = [outsider, study_task, hobby_task]
        complete(hobby_task, outsider, tasks_no_leader)

    assert scoring.pending_samples_count == 0

    final_study = scoring.score_single_task(study_task, events, now)
    final_hobby = scoring.score_single_task(hobby_task, events, now)
    final_diff = final_study - final_hobby

    assert final_diff > initial_diff, (
        f"study должно опережать hobby сильнее: было {initial_diff:.1f}, стало {final_diff:.1f}"
    )


def test_retrain_description_length_effect_naturally() -> None:
    """
    Показывает, что модель может научиться сильнее учитывать длину описания,
    когда подробные задачи завершаются с более высоким скором.
    """
    scoring = MLScoringService(
        wake_start_hour=8, wake_end_hour=22, horizon_days=7, retrain_batch_size=10
    )
    now = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
    events = []

    long_desc = Task(
        title="Long", description="Подробное описание " * 20,
        estimated_minutes=60, deadline=now + timedelta(days=2), workspace_id="study", priority=2
    )
    short_desc = Task(
        title="Short", description=".",
        estimated_minutes=60, deadline=now + timedelta(days=2), workspace_id="study", priority=2
    )
    leader = Task(
        title="Leader", description="Длинное важное" * 5, priority=1, estimated_minutes=15,
        deadline=now + timedelta(hours=1), workspace_id="study"
    )
    outsider = Task(
        title="Outsider", description="", priority=4, estimated_minutes=120,
        deadline=now + timedelta(days=30), workspace_id="study"
    )

    initial_long = scoring.score_single_task(long_desc, events, now)
    initial_short = scoring.score_single_task(short_desc, events, now)
    initial_diff = initial_long - initial_short

    def complete(task, max_task, tasks_ctx):
        score_map = scoring.build_score_map(tasks_ctx, events, now)
        max_score = score_map.get(max_task.id, None)
        base = scoring.score_single_task(task, events, now)
        scoring.record_completed_feedback(task, events, now, base, max_score)

    tasks = [leader, outsider, long_desc, short_desc]
    for _ in range(5):
        complete(long_desc, leader, tasks)
        tasks_no_leader = [outsider, long_desc, short_desc]
        complete(short_desc, outsider, tasks_no_leader)

    assert scoring.pending_samples_count == 0

    final_long = scoring.score_single_task(long_desc, events, now)
    final_short = scoring.score_single_task(short_desc, events, now)
    final_diff = final_long - final_short

    assert final_diff > initial_diff, (
        f"Описание должно влиять сильнее: было {initial_diff:.1f}, стало {final_diff:.1f}"
    )
