from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from app.modules.intelligence.models import SchedulePlan, ScheduledSlot
from app.modules.intelligence.scoring import score_task
from app.modules.knowledge.models import Event, Task


class GreedyScheduler:
    def __init__(
        self,
        slot_minutes: int,
        horizon_days: int,
        wake_start_hour: int,
        wake_end_hour: int,
    ) -> None:
        self.slot_minutes = slot_minutes
        self.horizon_days = horizon_days
        self.wake_start_hour = wake_start_hour
        self.wake_end_hour = wake_end_hour

    def build_plan(self, tasks: list[Task], events: list[Event], now: datetime) -> SchedulePlan:
        current = self._to_utc(now)
        horizon_end = current + timedelta(days=self.horizon_days)

        unfinished_ids = {task.id for task in tasks if task.status != "completed"}
        movable = [
            task
            for task in tasks
            if task.status in {"todo", "in_progress"} and task.auto_reschedule
        ]
        candidates = [
            task
            for task in movable
            if not any(dep_id in unfinished_ids for dep_id in task.depends_on)
        ]

        fixed_busy_intervals = [(event.start_at, event.end_at) for event in events]
        fixed_busy_intervals.extend(
            [
                (task.scheduled_start, task.scheduled_end)
                for task in tasks
                if task.scheduled_start
                and task.scheduled_end
                and not task.auto_reschedule
                and task.status in {"todo", "in_progress"}
            ]
        )

        free_windows = self._find_free_windows(current, horizon_end, fixed_busy_intervals)

        scored_tasks = sorted(
            [(score_task(task, current), task) for task in candidates],
            key=lambda item: item[0],
            reverse=True,
        )

        scheduled_slots: list[ScheduledSlot] = []
        unscheduled_task_ids: list[str] = []

        for task_score, task in scored_tasks:
            needed_minutes = self._round_up_to_slot(task.estimated_minutes)
            latest_end = self._to_utc(task.deadline) if task.deadline else horizon_end
            slot = self._allocate_window(free_windows, needed_minutes, latest_end)
            if slot is None:
                unscheduled_task_ids.append(task.id)
                continue

            start_at, end_at = slot
            scheduled_slots.append(
                ScheduledSlot(
                    task_id=task.id,
                    title=task.title,
                    start_at=start_at,
                    end_at=end_at,
                    score=task_score,
                )
            )

        scheduled_slots.sort(key=lambda item: item.start_at)
        prime_task_id = scheduled_slots[0].task_id if scheduled_slots else None

        return SchedulePlan(
            generated_at=current,
            slots=scheduled_slots,
            unscheduled_task_ids=unscheduled_task_ids,
            prime_task_id=prime_task_id,
        )

    def _find_free_windows(
        self,
        start_at: datetime,
        end_at: datetime,
        busy_intervals: list[tuple[datetime, datetime]],
    ) -> list[tuple[datetime, datetime]]:
        working_windows = self._build_working_windows(start_at, end_at)
        busy = self._normalize_intervals(busy_intervals)

        free_windows = working_windows
        for busy_start, busy_end in busy:
            free_windows = self._subtract_interval(free_windows, busy_start, busy_end)

        return [window for window in free_windows if window[1] > window[0]]

    def _build_working_windows(
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

    @staticmethod
    def _normalize_intervals(
        intervals: list[tuple[datetime | None, datetime | None]],
    ) -> list[tuple[datetime, datetime]]:
        normalized: list[tuple[datetime, datetime]] = []
        for start_at, end_at in intervals:
            if start_at is None or end_at is None or end_at <= start_at:
                continue
            normalized.append((GreedyScheduler._to_utc(start_at), GreedyScheduler._to_utc(end_at)))
        normalized.sort(key=lambda interval: interval[0])
        return normalized

    @staticmethod
    def _subtract_interval(
        windows: list[tuple[datetime, datetime]],
        busy_start: datetime,
        busy_end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        result: list[tuple[datetime, datetime]] = []

        for window_start, window_end in windows:
            if busy_end <= window_start or busy_start >= window_end:
                result.append((window_start, window_end))
                continue

            if busy_start > window_start:
                result.append((window_start, busy_start))
            if busy_end < window_end:
                result.append((busy_end, window_end))

        return result

    def _allocate_window(
        self,
        free_windows: list[tuple[datetime, datetime]],
        needed_minutes: int,
        latest_end: datetime,
    ) -> tuple[datetime, datetime] | None:
        needed = timedelta(minutes=needed_minutes)

        for index, (window_start, window_end) in enumerate(free_windows):
            effective_end = min(window_end, latest_end)
            if effective_end - window_start < needed:
                continue

            start_at = window_start
            end_at = start_at + needed

            if end_at < window_end:
                free_windows[index] = (end_at, window_end)
            else:
                free_windows.pop(index)

            return start_at, end_at

        return None

    def _round_up_to_slot(self, minutes: int) -> int:
        chunks = math.ceil(minutes / self.slot_minutes)
        return chunks * self.slot_minutes

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
