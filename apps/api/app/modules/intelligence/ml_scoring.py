from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean

from app.modules.knowledge.models import Event, Task

try:
    from sklearn.linear_model import SGDRegressor
except Exception:  # pragma: no cover - fallback for environments without sklearn
    SGDRegressor = None


@dataclass
class TrainingSample:
    features: list[float]
    target: float
    source: str
    task_id: str


class MLScoringService:
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

        self._model = (
            SGDRegressor(
                loss="squared_error",
                penalty="l2",
                random_state=42,
                max_iter=1000,
                tol=1e-3,
                learning_rate="optimal",
            )
            if SGDRegressor is not None
            else None
        )
        self._is_fitted = False

        self._pending_samples: list[TrainingSample] = []
        self.last_scores: dict[str, float] = {}

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
        features = self._task_features(task=task, events=events, now=now)
        if self._model is not None and self._is_fitted:
            return float(self._model.predict([features])[0])
        return self._fallback_score(task=task, now=now)

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

        if self._model is not None:
            self._model.partial_fit(features_batch, targets_batch)
            self._is_fitted = True

        self._pending_samples.clear()
        return True

    def _task_features(self, task: Task, events: list[Event], now: datetime) -> list[float]:
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

        awake_windows = self._build_awake_windows(start_at=current, end_at=deadline)
        awake_minutes = sum((end - start).total_seconds() / 60 for start, end in awake_windows)
        busy_minutes = self._events_overlap_minutes(windows=awake_windows, events=events)

        return max(0.0, awake_minutes - busy_minutes)

    def _build_awake_windows(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[tuple[datetime, datetime]]:
        windows: list[tuple[datetime, datetime]] = []
        day_cursor = start_at.replace(hour=0, minute=0, second=0, microsecond=0)

        while day_cursor < end_at:
            day_start = day_cursor.replace(
                hour=self.wake_start_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if self.wake_end_hour == 24:
                day_end = day_cursor + timedelta(days=1)
            else:
                day_end = day_cursor.replace(
                    hour=self.wake_end_hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

            window_start = max(day_start, start_at)
            window_end = min(day_end, end_at)
            if window_end > window_start:
                windows.append((window_start, window_end))

            day_cursor += timedelta(days=1)

        return windows

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
                if dep_id in task_by_id and dep_id in base_scores
            ]
            if not blockers or task.id not in base_scores:
                continue

            dependent_score = mean(
                [base_scores[task.id], *[base_scores[item.id] for item in blockers]]
            )
            score_map[task.id] = dependent_score

            blocker_target = dependent_score + 1.0
            for blocker in blockers:
                score_map[blocker.id] = max(score_map[blocker.id], blocker_target)

    @staticmethod
    def _fallback_score(task: Task, now: datetime) -> float:
        current = MLScoringService._to_utc(now)
        priority_score = (5 - task.priority) * 20

        if task.deadline is None:
            urgency_score = 25
        else:
            hours_left = (MLScoringService._to_utc(task.deadline) - current).total_seconds() / 3600
            if hours_left <= 0:
                urgency_score = 120
            elif hours_left <= 24:
                urgency_score = 95
            elif hours_left <= 72:
                urgency_score = 70
            else:
                urgency_score = 40

        return float(priority_score + urgency_score)

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
