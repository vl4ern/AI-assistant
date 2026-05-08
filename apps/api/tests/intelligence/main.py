from datetime import datetime, timedelta, timezone
from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.intelligence.models import ReorderFeedbackRequest
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.intelligence.service import SchedulerService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.models import Event, EventCreate, Task, TaskCreate


scoring = MLScoringService(
    wake_start_hour=8, wake_end_hour=22, horizon_days=7, retrain_batch_size=7
)
now = datetime.now(timezone.utc)
events = []

# Создаём две задачи с одинаковыми параметрами, но разным приоритетом
low_prio = Task(
    title="Low", priority=4, estimated_minutes=60,
    deadline=now + timedelta(hours=5), workspace_id="study"
)
high_prio = Task(
    title="High", priority=1, estimated_minutes=60,
    deadline=now + timedelta(hours=5), workspace_id="study"
)

# Исходные скоры (до дообучения)
original_low = scoring.score_single_task(low_prio, events, now)
original_high = scoring.score_single_task(high_prio, events, now)
original_diff = original_high - original_low

# Готовим обучающие примеры, которые учат модель, что приоритет 1 -> очень высокий скор,
# приоритет 4 -> низкий скор

prio_1 = Task(
    title="prio_1", priority=3, estimated_minutes=60,
    deadline=now + timedelta(hours=5), workspace_id="study"
)
prio_2 = Task(
    title="prio_2", priority=3, estimated_minutes=60,
    deadline=now + timedelta(hours=15), workspace_id="study"
)
prio_3 = Task(
    title="prio_3", priority=3, estimated_minutes=60,
    deadline=now + timedelta(hours=25), workspace_id="study"
)
prio_4 = Task(
    title="prio_4", priority=3, estimated_minutes=60,
    deadline=now + timedelta(hours=45), workspace_id="study"
)
prio_5 = Task(
    title="prio_5", priority=2, estimated_minutes=60,
    deadline=now + timedelta(hours=105), workspace_id="study"
)
prio_6 = Task(
    title="prio_6", priority=2, estimated_minutes=60,
    deadline=now + timedelta(hours=150), workspace_id="study"
)
prio_7 = Task(
    title="prio_7", priority=2, estimated_minutes=60,
    deadline=now + timedelta(hours=255), workspace_id="study"
)
prio_8 = Task(
    title="prio_8", priority=1, estimated_minutes=60,
    deadline=now + timedelta(hours=505), workspace_id="study"
)


tasks = [prio_1, prio_2, prio_3, prio_4, prio_5, prio_6, prio_7, prio_8]
retrained = False
for _ in range(7):
    smap = scoring.build_score_map(tasks, events, now)

    ranked = sorted(
        [(float(smap.get(task.id, 0.0)), task.id) for task],
        key=lambda item: item[0],
        reverse=True,
    )

    task = tasks.pop()
    max_score = max(smap.values())
    if not max_score:
        max_score = smap[task.id]
        
    print(f'name: ', task.title)
    print(f'score', smap[task.id])
    print(f'max_score', max_score, '\n')
    
    retrained = scoring.record_completed_feedback(
        task=task, events=events, now=now, base_score=smap[task.id], max_active_score=max_score
    )

new_low = scoring.score_single_task(low_prio, events, now)
new_high = scoring.score_single_task(high_prio, events, now)
new_diff = new_high - new_low

print(f"После дообучения разница должна вырасти: было {original_diff:.1f}, стало {new_diff:.1f}")
