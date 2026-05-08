from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.intelligence.models import (
    ReorderFeedbackRequest,
    ReorderFeedbackResult,
    SchedulePlan,
    TodayView,
)
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.knowledge.models import Task
from app.modules.knowledge.repository import KnowledgeRepository


class SchedulerService:
    """
    Оркестратор интеллектуального модуля.

    Связывает репозиторий, планировщик и сервис скоринга.
    Предоставляет методы для:
    - перестроения расписания (rebuild)
    - получения представления "Сегодня" (today)
    - обработки обратной связи от пользователя (record_reorder_feedback)
    - реакции на изменение статуса задачи (on_task_status_updated)
    """
    def __init__(
        self,
        repository: KnowledgeRepository,
        scheduler: GreedyScheduler,
        scoring_service: MLScoringService,
    ) -> None:
        """Сохраняет ссылки на репозиторий, планировщик и сервис скоринга."""
        self.repository = repository
        self.scheduler = scheduler
        self.scoring_service = scoring_service
        self._completed_markers: dict[str, datetime] = {}

    def rebuild(self) -> SchedulePlan:
        """
        Полностью перестраивает расписание.

        1. Сбрасывает scheduled_start/end у всех подвижных задач.
        2. Вычисляет скоринговую карту (MLScoringService).
        3. Вызывает планировщик.
        4. Сохраняет назначенные интервалы в репозитории.
        5. Снимает флаг "расписание изменено" (schedule_dirty).
        6. Возвращает объект SchedulePlan.
        """
        now = datetime.now(timezone.utc)
        tasks = self.repository.list_tasks()
        events = self.repository.list_events()

        for task in tasks:
            if task.auto_reschedule and task.status in {"todo", "in_progress"}:
                self.repository.update_task_schedule(task.id, None, None)

        score_map = self.scoring_service.build_score_map(tasks=tasks, events=events, now=now)
        plan = self.scheduler.build_plan(
            tasks=tasks,
            events=events,
            now=now,
            task_scores=score_map,
        )

        for slot in plan.slots:
            self.repository.update_task_schedule(slot.task_id, slot.start_at, slot.end_at)

        self.repository.set_schedule_dirty(False)
        return plan

    def today(self) -> TodayView:
        """
        Формирует представление "Сегодня".

        Выбирает задачи, запланированные на текущий день, сортирует по времени начала,
        определяет prime-задачу (самый ранний слот) и проверяет флаг schedule_dirty.

        Возвращает объект TodayView.
        """
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

    def record_reorder_feedback(self, payload: ReorderFeedbackRequest) -> ReorderFeedbackResult:
        """
        Обрабатывает ручное перемещение задачи пользователем.

        Вычисляет целевой скор как среднее скоринг-баллов соседних задач,
        или сохраняет текущий, если соседей нет.

        Затем передаёт пример в MLScoringService для дообучения.
        Возвращает ReorderFeedbackResult с информацией о состоянии обучения.
        """
        now = payload.moved_at or datetime.now(timezone.utc)

        tasks = self.repository.list_tasks()
        events = self.repository.list_events()
        task_by_id = {task.id: task for task in tasks}

        moved_task = task_by_id.get(payload.moved_task_id)
        if moved_task is None:
            raise ValueError("Moved task not found")

        if self.scoring_service.last_scores:
            score_map = self.scoring_service.last_scores
        else:
            score_map = self.scoring_service.build_score_map(tasks=tasks, events=events, now=now)

        neighbor_scores: list[float] = []
        for neighbor_id in (payload.left_task_id, payload.right_task_id):
            if neighbor_id and neighbor_id in score_map:
                neighbor_scores.append(float(score_map[neighbor_id]))

        if neighbor_scores:
            target_score = float(mean(neighbor_scores))
        else:
            target_score = float(
                score_map.get(
                    moved_task.id,
                    self.scoring_service.score_single_task(moved_task, events=events, now=now),
                )
            )

        retrained = self.scoring_service.record_reorder_feedback(
            task=moved_task,
            events=events,
            now=now,
            target_score=target_score,
        )

        return ReorderFeedbackResult(
            moved_task_id=moved_task.id,
            target_score=target_score,
            samples_in_batch=self.scoring_service.pending_samples_count,
            retrained=retrained,
        )

    def on_task_status_updated(self, task: Task) -> None:
        """
        Реагирует на изменение статуса задачи.

        Если задача стала completed, записывает completed-фидбек в MLScoringService.
        Использует маркер updated_at, чтобы избежать повторной обработки одного и того же события.
        """
        if task.status != "completed":
            return

        marker = task.updated_at
        known = self._completed_markers.get(task.id)
        if known is not None and known >= marker:
            return

        now = datetime.now(timezone.utc)
        events = self.repository.list_events()

        base_score = self.scoring_service.last_scores.get(task.id)
        if base_score is None:
            base_score = self.scoring_service.score_single_task(task, events=events, now=now)
        
        max_score = base_score
        if self.scoring_service.last_scores:
            tasks = self.repository.list_tasks()
            task_by_id = {task.id: task for task in tasks}
            
            active_scores = [s for tid, s in self.scoring_service.last_scores.items()
                             if task_by_id[tid].status not in ("cancelled", "completed")]

            if active_scores:
                max_score = max(active_scores)

        self.scoring_service.record_completed_feedback(
            task=task,
            events=events,
            now=now,
            base_score=float(base_score),
            max_active_score=max_score
        )
        self._completed_markers[task.id] = marker
