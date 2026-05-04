from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean

from app.modules.knowledge.models import Event, Task
from app.modules.intelligence.utils.time_utils import build_working_windows

from sklearn.linear_model import SGDRegressor


@dataclass
class TrainingSample:
    features: list[float]
    target: float
    source: str
    task_id: str


class MLScoringService:
    """
    Сервис скоринга задач на базе ML-регрессии.

    Важно:
    - Модель используется всегда (даже "с нуля"), потому что мы делаем
      стартовую калибровку на синтетических данных.
    - Далее модель дообучается на реальных действиях пользователя.
    """

    def __init__(
        self,
        wake_start_hour: int,
        wake_end_hour: int,
        horizon_days: int,
        retrain_batch_size: int = 20,
        overdue_bonus: float = 10.0,
    ) -> None:
        self.wake_start_hour = wake_start_hour
        self.wake_end_hour = wake_end_hour
        self.horizon_days = horizon_days
        self.retrain_batch_size = retrain_batch_size
        self.overdue_bonus = overdue_bonus

        self._model = SGDRegressor(
            loss="squared_error",
            penalty="l2",
            random_state=42,
            max_iter=2000,
            tol=1e-3,
            learning_rate="optimal",
        )

        self._pending_samples: list[TrainingSample] = []
        self.last_scores: dict[str, float] = {}
        self._bootstrap_model()

    @property
    def pending_samples_count(self) -> int:
        return len(self._pending_samples)

    def build_score_map(
        self,
        tasks: list[Task],
        events: list[Event],
        now: datetime,
    ) -> dict[str, float]:
        current = self._to_utc(now)
        score_map = {
            task.id: self.score_single_task(task=task, events=events, now=current)
            for task in tasks
        }
        self._apply_dependency_rules(tasks=tasks, score_map=score_map)
        self.last_scores = score_map.copy()
        return score_map

    def score_single_task(self, task: Task, events: list[Event], now: datetime) -> float:
        # Всегда считаем через ML-модель.
        features = self._task_features(task=task, events=events, now=now)
        
        return float(self._model.predict([features])[0])

    def record_reorder_feedback(
        self,
        task: Task,
        events: list[Event],
        now: datetime,
        target_score: float,
    ) -> bool:
        return self._record_sample(
            task=task,
            events=events,
            now=now,
            target_score=target_score,
            source="reorder",
        )

    def record_completed_feedback(
        self,
        task: Task,
        events: list[Event],
        now: datetime,
        base_score: float,
    ) -> bool:
        target = base_score
        deadline = task.deadline
        if deadline and self._to_utc(now) > self._to_utc(deadline):
            target += self.overdue_bonus

        return self._record_sample(
            task=task,
            events=events,
            now=now,
            target_score=target,
            source="completed",
        )

    def _record_sample(
        self,
        task: Task,
        events: list[Event],
        now: datetime,
        target_score: float,
        source: str,
    ) -> bool:
        features = self._task_features(task=task, events=events, now=now)
        self._pending_samples.append(
            TrainingSample(
                features=features,
                target=float(target_score),
                source=source,
                task_id=task.id,
            )
        )

        if len(self._pending_samples) < self.retrain_batch_size:
            return False

        features_batch = [sample.features for sample in self._pending_samples]
        targets_batch = [sample.target for sample in self._pending_samples]

        # Дообучаем модель пачкой накопленных пользовательских примеров.
        self._model.partial_fit(features_batch, targets_batch)

        self._pending_samples.clear()
        return True

    def _task_features(self, task: Task, events: list[Event], now: datetime) -> list[float]:
        # Набор признаков по ТЗ:
        # 1) свободные минуты до дедлайна,
        # 2) пользовательский приоритет,
        # 3) оценка времени задачи.
        free_minutes = self._time_to_deadline_free_minutes(task=task, events=events, now=now)
        user_priority = float(task.priority)
        estimate_minutes = float(task.estimated_minutes)
        return [free_minutes, user_priority, estimate_minutes]

    def _time_to_deadline_free_minutes(self, task: Task, events: list[Event], now: datetime) -> float:
        current = self._to_utc(now)
        deadline = (
            self._to_utc(task.deadline)
            if task.deadline is not None
            else current + timedelta(days=self.horizon_days)
        )

        if deadline <= current:
            return 0.0

        awake_windows = build_working_windows(current, deadline, self.wake_start_hour, self.wake_end_hour)
        awake_minutes = sum((end - start).total_seconds() / 60 for start, end in awake_windows)
        busy_minutes = self._events_overlap_minutes(windows=awake_windows, events=events)

        return max(0.0, awake_minutes - busy_minutes)


    def _events_overlap_minutes(
        self,
        windows: list[tuple[datetime, datetime]],
        events: list[Event],
    ) -> float:
        busy = 0.0
        normalized_events = [
            (self._to_utc(event.start_at), self._to_utc(event.end_at))
            for event in events
            if event.end_at > event.start_at
        ]

        for window_start, window_end in windows:
            for event_start, event_end in normalized_events:
                overlap_start = max(window_start, event_start)
                overlap_end = min(window_end, event_end)
                if overlap_end > overlap_start:
                    busy += (overlap_end - overlap_start).total_seconds() / 60

        return busy

    def _apply_dependency_rules(self, tasks: list[Task], score_map: dict[str, float]) -> None:
        task_by_id = {task.id: task for task in tasks}
        base_scores = score_map.copy()

        for task in tasks:
            blockers = [
                task_by_id[dep_id]
                for dep_id in task.depends_on
                if dep_id in base_scores
            ]
            if not blockers or task.id not in base_scores:
                continue

            # Правило зависимостей:
            # score(T) = mean(score(T), score(B1), score(B2), ...)
            dependent_score = mean(
                [base_scores[task.id], *[base_scores[item.id] for item in blockers]]
            )
            score_map[task.id] = dependent_score

            # Для блокирующих задач повышаем приоритет: score(Bi) = score(T) + 1.
            blocker_target = dependent_score + 1.0
            for blocker in blockers:
                score_map[blocker.id] = max(score_map[blocker.id], blocker_target)

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _bootstrap_model(self) -> None:
        """
        Стартовая калибровка:
        обучаем модель на синтетике, чтобы ML работал сразу после запуска.
        """
        bootstrap_features: list[list[float]] = []
        bootstrap_targets: list[float] = []

        free_minutes_values = [60, 240, 720, 1440, 2880, 7200, 14400, 28800, 43200]
        priorities = [1, 2, 3, 4]
        estimates = [30, 60, 90, 120, 180, 240]

        for free_minutes in free_minutes_values:
            for priority in priorities:
                for estimate in estimates:
                    bootstrap_features.append([float(free_minutes), float(priority), float(estimate)])
                    bootstrap_targets.append(
                        self._initial_target(
                            free_minutes=float(free_minutes),
                            priority=float(priority),
                            estimated_minutes=float(estimate),
                        )
                    )

        self._model.fit(bootstrap_features, bootstrap_targets)

    @staticmethod
    def _initial_target(
        free_minutes: float,
        priority: float,
        estimated_minutes: float,
    ) -> float:
        """
        Начальная формула "здравого смысла":
        - чем меньше свободного времени до дедлайна, тем выше score;
        - чем "важнее" задача для пользователя (priority=1), тем выше score;
        - более длинные задачи немного повышаем, чтобы не откладывались бесконечно.
        """
        raw = 220.0 - (0.006 * free_minutes) - (18.0 * priority) + (0.05 * estimated_minutes)
        return max(0.0, min(200.0, raw))
