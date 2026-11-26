from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import math
from typing import Any

from app.modules.intelligence.models import SchedulePlan, ScheduledSlot
from app.modules.intelligence.scheduler import GreedyScheduler, SchedulerBase
from app.modules.knowledge.models import Event, Task

try:
    from ortools.sat.python import cp_model
except ImportError:  # pragma: no cover - зависимость обязательна в requirements
    cp_model = None

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Slot:
    """Один слот времени в свободном окне."""

    start_at: datetime
    end_at: datetime


@dataclass
class _ChunkGroup:
    """
    Группа одинаковых по длине кусков задачи.

    Например, задача на 180 минут при минимальном куске 60 минут даёт
    группу из трёх кусков по 60 минут. Вместо отдельной переменной на
    каждый кусок достаточно одной группы и ограничения на количество
    выбранных интервалов.
    """

    size_slots: int
    required: int
    selected: Any
    starts: list[tuple[int, Any]]


@dataclass
class _TaskModel:
    """Переменные CP-SAT, относящиеся к одной задаче."""

    task: Task
    full_var: Any
    groups: list[_ChunkGroup]


class CpSatScheduler(SchedulerBase):
    """
    Планировщик на CP-SAT (OR-Tools).

    В отличие от жадного алгоритма, решение ищется глобально: задачи
    раскладываются по слотам так, чтобы максимизировать суммарную
    ценность запланированной работы, по возможности завершить задачи
    целиком и поставить более важные задачи раньше.

    Сохраняются все ограничения прежнего планировщика:
    - окна бодрствования;
    - события и несдвигаемые задачи;
    - дедлайны;
    - зависимости;
    - запрет пересечений;
    - дробление задач (`allow_split`, `min_chunk_minutes`).

    Если OR-Tools недоступен или решатель не нашёл решение, используется
    жадный алгоритм, чтобы API оставался работоспособным.
    """

    # Масштаб основного критерия. Благодаря ему ценность одного слота
    # всегда больше любых штрафов за более позднее начало.
    _VALUE_SCALE = 1_000_000
    # Максимальный целочисленный скор после нормализации. Ограничение
    # защищает целевую функцию от переполнения int64.
    _MAX_SCORE_INT = 10_000
    # Завершённая задача дополнительно ценится как 8 слотов.
    _COMPLETION_SLOT_BONUS = 8
    # Небольшое предпочтение целого блока перед дроблением.
    _WHOLE_BLOCK_BONUS = 1
    # Штраф за лишний кусок — только для выбора между равными вариантами.
    _CHUNK_PENALTY = 1

    def __init__(
        self,
        slot_minutes: int,
        horizon_days: int,
        wake_start_hour: int,
        wake_end_hour: int,
        max_time_in_seconds: float = 10.0,
    ) -> None:
        """Инициализирует планировщик и лимит времени работы решателя."""
        super().__init__(
            slot_minutes=slot_minutes,
            horizon_days=horizon_days,
            wake_start_hour=wake_start_hour,
            wake_end_hour=wake_end_hour,
        )
        self.max_time_in_seconds = max_time_in_seconds
        self._fallback = GreedyScheduler(
            slot_minutes=slot_minutes,
            horizon_days=horizon_days,
            wake_start_hour=wake_start_hour,
            wake_end_hour=wake_end_hour,
        )

    def build_plan(
        self,
        tasks: list[Task],
        events: list[Event],
        now: datetime,
        task_scores: dict[str, float] | None = None,
    ) -> SchedulePlan:
        """
        Строит оптимальный план CP-SAT.

        Если решатель недоступен или не смог найти ни одного решения,
        возвращает результат жадного планировщика, чтобы API оставался
        работоспособным.
        """
        if cp_model is None:
            logger.warning(
                "OR-Tools не установлен: используется жадный планировщик. "
                "Установите зависимости backend."
            )
            return self._fallback.build_plan(tasks, events, now, task_scores)

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

        score_map = task_scores or {}
        ranked = sorted(
            [(float(score_map.get(task.id, 0.0)), task) for task in candidates],
            key=lambda item: item[0],
            reverse=True,
        )

        if not ranked:
            return SchedulePlan(
                generated_at=current,
                slots=[],
                unscheduled_task_ids=[],
                prime_task_id=None,
            )

        fixed_busy_intervals: list[tuple[datetime | None, datetime | None]] = [
            (event.start_at, event.end_at) for event in events
        ]
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

        free_windows = self._find_free_windows(
            current,
            horizon_end,
            fixed_busy_intervals,
        )
        slots, window_slot_indices = self._build_slots(free_windows)

        if not slots:
            return SchedulePlan(
                generated_at=current,
                slots=[],
                unscheduled_task_ids=[task.id for _, task in ranked],
                prime_task_id=None,
            )

        # Нормируем скоры к [1, _MAX_SCORE_INT], сохраняя их отношения.
        # Это делает веса целевой функции предсказуемыми при любых
        # значениях регрессии и защищает от переполнения.
        max_raw_score = max((score for score, _ in ranked), default=0.0)
        score_scale = (
            self._MAX_SCORE_INT / max_raw_score if max_raw_score > 0 else 1.0
        )

        model = cp_model.CpModel()
        intervals: list[Any] = []
        objective_terms: list[Any] = []
        task_models: list[_TaskModel] = []

        for task_index, (score_value, task) in enumerate(ranked):
            score_int = max(
                1,
                min(
                    self._MAX_SCORE_INT,
                    int(round(float(score_value) * score_scale)),
                ),
            )
            needed_slots = max(
                1,
                math.ceil(task.estimated_minutes / self.slot_minutes),
            )
            latest_end = (
                self._to_utc(task.deadline) if task.deadline else horizon_end
            )
            latest_end = min(latest_end, horizon_end)

            task_model = self._add_task_model(
                model=model,
                task=task,
                task_index=task_index,
                needed_slots=needed_slots,
                latest_end=latest_end,
                score_int=score_int,
                slots=slots,
                window_slot_indices=window_slot_indices,
                intervals=intervals,
                objective_terms=objective_terms,
            )
            task_models.append(task_model)

        if intervals:
            model.AddNoOverlap(intervals)

        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.max_time_in_seconds
        # Один worker и фиксированный seed дают воспроизводимый результат.
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 42
        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.warning(
                "CP-SAT не нашёл решение (status=%s): используется жадный fallback",
                status,
            )
            return self._fallback.build_plan(tasks, events, now, task_scores)

        scheduled_slots: list[ScheduledSlot] = []
        unscheduled_task_ids: list[str] = []

        for task_model in task_models:
            task = task_model.task
            score = float(score_map.get(task.id, 0.0))

            if solver.Value(task_model.full_var) == 0:
                unscheduled_task_ids.append(task.id)

            for group in task_model.groups:
                for start_index, start_var in group.starts:
                    if solver.Value(start_var) == 0:
                        continue
                    scheduled_slots.append(
                        ScheduledSlot(
                            task_id=task.id,
                            title=task.title,
                            start_at=slots[start_index].start_at,
                            end_at=slots[
                                start_index + group.size_slots - 1
                            ].end_at,
                            score=score,
                        )
                    )

        scheduled_slots.sort(
            key=lambda item: (item.start_at, item.end_at, item.task_id)
        )
        prime_task_id = scheduled_slots[0].task_id if scheduled_slots else None

        return SchedulePlan(
            generated_at=current,
            slots=scheduled_slots,
            unscheduled_task_ids=unscheduled_task_ids,
            prime_task_id=prime_task_id,
        )

    def _add_task_model(
        self,
        *,
        model: Any,
        task: Task,
        task_index: int,
        needed_slots: int,
        latest_end: datetime,
        score_int: int,
        slots: list[_Slot],
        window_slot_indices: list[list[int]],
        intervals: list[Any],
        objective_terms: list[Any],
    ) -> _TaskModel:
        """Добавляет в модель переменные одной задачи и её кусков."""
        split_sizes = self._split_sizes(task, needed_slots)

        # Задача без дробления или слишком короткая для нескольких кусков:
        # один обязательный блок.
        if not task.allow_split or split_sizes == [needed_slots]:
            selected, group = self._add_chunk_group(
                model=model,
                name=f"task_{task_index}_whole",
                size_slots=needed_slots,
                required=1,
                latest_end=latest_end,
                score_int=score_int,
                slots=slots,
                window_slot_indices=window_slot_indices,
                intervals=intervals,
                objective_terms=objective_terms,
            )
            model.Add(sum(var for _, var in group.starts) == selected)
            objective_terms.append(
                selected
                * self._COMPLETION_SLOT_BONUS
                * score_int
                * self._VALUE_SCALE
            )
            return _TaskModel(task=task, full_var=selected, groups=[group])

        # Дробимую задачу можно выполнить целиком одним блоком или
        # несколькими кусками. Целый блок предпочтительнее, если помещается.
        whole, whole_group = self._add_chunk_group(
            model=model,
            name=f"task_{task_index}_whole",
            size_slots=needed_slots,
            required=1,
            latest_end=latest_end,
            score_int=score_int,
            slots=slots,
            window_slot_indices=window_slot_indices,
            intervals=intervals,
            objective_terms=objective_terms,
        )
        model.Add(sum(var for _, var in whole_group.starts) == whole)
        objective_terms.append(
            whole
            * self._WHOLE_BLOCK_BONUS
            * score_int
            * self._VALUE_SCALE
        )

        split_groups: list[_ChunkGroup] = []
        split_full_vars: list[Any] = []
        groups_by_size: dict[int, _ChunkGroup] = {}
        required_by_size: dict[int, int] = {}
        for size in split_sizes:
            required_by_size[size] = required_by_size.get(size, 0) + 1

        for size, required in required_by_size.items():
            group_full = model.NewBoolVar(
                f"task_{task_index}_group_{size}_full"
            )
            group_selected, group = self._add_chunk_group(
                model=model,
                name=f"task_{task_index}_group_{size}",
                size_slots=size,
                required=required,
                latest_end=latest_end,
                score_int=score_int,
                slots=slots,
                window_slot_indices=window_slot_indices,
                intervals=intervals,
                objective_terms=objective_terms,
            )
            count = sum(var for _, var in group.starts)
            model.Add(count >= required).OnlyEnforceIf(group_full)
            model.Add(count <= required - 1).OnlyEnforceIf(group_full.Not())
            split_groups.append(group)
            split_full_vars.append(group_full)
            groups_by_size[size] = group

        # Остаток можно ставить только после всех полноразмерных кусков.
        # Это повторяет прежнюю семантику: сначала задача режется на куски
        # не меньше min_chunk_minutes, и только последний кусок может быть
        # короче.
        if len(groups_by_size) > 1:
            full_size = max(groups_by_size)
            remainder_group = groups_by_size[min(groups_by_size)]
            full_group = groups_by_size[full_size]
            model.Add(
                sum(var for _, var in full_group.starts) == full_group.required
            ).OnlyEnforceIf(remainder_group.selected)

        all_split_chunks = [
            var for group in split_groups for _, var in group.starts
        ]
        # Либо целый блок, либо куски — не одновременно.
        model.Add(sum(all_split_chunks) == 0).OnlyEnforceIf(whole)

        all_splits = model.NewBoolVar(f"task_{task_index}_all_splits")
        for group_full in split_full_vars:
            model.Add(all_splits <= group_full)
        model.Add(
            all_splits >= sum(split_full_vars) - (len(split_full_vars) - 1)
        )

        full = model.NewBoolVar(f"task_{task_index}_full")
        model.Add(full >= whole)
        model.Add(full >= all_splits)
        model.Add(full <= whole + all_splits)
        objective_terms.append(
            full * self._COMPLETION_SLOT_BONUS * score_int * self._VALUE_SCALE
        )

        return _TaskModel(
            task=task,
            full_var=full,
            groups=[whole_group, *split_groups],
        )

    def _add_chunk_group(
        self,
        *,
        model: Any,
        name: str,
        size_slots: int,
        required: int,
        latest_end: datetime,
        score_int: int,
        slots: list[_Slot],
        window_slot_indices: list[list[int]],
        intervals: list[Any],
        objective_terms: list[Any],
    ) -> tuple[Any, _ChunkGroup]:
        """
        Добавляет группу одинаковых кусков.

        Возвращает булеву переменную «выбран хотя бы один кусок» и саму
        группу. Для целого блока `required == 1`, поэтому переменная
        означает выбор этого блока.
        """
        selected = model.NewBoolVar(f"{name}_selected")
        starts: list[tuple[int, Any]] = []

        for start_index in self._possible_starts(
            window_slot_indices=window_slot_indices,
            size_slots=size_slots,
            latest_end=latest_end,
            slots=slots,
        ):
            start_var = model.NewBoolVar(f"{name}_start_{start_index}")
            starts.append((start_index, start_var))
            intervals.append(
                model.NewOptionalIntervalVar(
                    start_index,
                    size_slots,
                    start_index + size_slots,
                    start_var,
                    f"{name}_interval_{start_index}",
                )
            )
            objective_terms.append(
                start_var
                * (
                    size_slots * score_int * self._VALUE_SCALE
                    - self._CHUNK_PENALTY
                    - self._earliness_coeff(score_int) * start_index
                )
            )

        count = sum(var for _, var in starts)
        model.Add(count <= required)
        model.Add(count >= 1).OnlyEnforceIf(selected)
        model.Add(count == 0).OnlyEnforceIf(selected.Not())

        return selected, _ChunkGroup(
            size_slots=size_slots,
            required=required,
            selected=selected,
            starts=starts,
        )

    def _build_slots(
        self,
        free_windows: list[tuple[datetime, datetime]],
    ) -> tuple[list[_Slot], list[list[int]]]:
        """Разбивает свободные окна на слоты фиксированной длины."""
        slots: list[_Slot] = []
        window_slot_indices: list[list[int]] = []

        for window_start, window_end in free_windows:
            total_minutes = int(
                (window_end - window_start).total_seconds() // 60
            )
            slot_count = total_minutes // self.slot_minutes
            indices: list[int] = []

            for slot_index in range(slot_count):
                start_at = window_start + timedelta(
                    minutes=slot_index * self.slot_minutes
                )
                indices.append(len(slots))
                slots.append(
                    _Slot(
                        start_at=start_at,
                        end_at=start_at + timedelta(minutes=self.slot_minutes),
                    )
                )

            if indices:
                window_slot_indices.append(indices)

        return slots, window_slot_indices

    def _possible_starts(
        self,
        *,
        window_slot_indices: list[list[int]],
        size_slots: int,
        latest_end: datetime,
        slots: list[_Slot],
    ) -> list[int]:
        """
        Возвращает индексы слотов, с которых может начинаться блок.

        Блок не может пересекать границу свободного окна и не может
        заканчиваться позже дедлайна/горизонта.
        """
        starts: list[int] = []

        for indices in window_slot_indices:
            max_position = len(indices) - size_slots
            for position in range(max_position + 1):
                start_index = indices[position]
                end_at = slots[indices[position + size_slots - 1]].end_at
                if end_at <= latest_end:
                    starts.append(start_index)

        return starts

    def _split_sizes(self, task: Task, needed_slots: int) -> list[int]:
        """
        Возвращает размеры кусков для дробимой задачи.

        Повторяет прежнюю семантику: сначала идут куски не меньше
        `min_chunk_minutes`, последний кусок может быть остатком.
        """
        if not task.allow_split:
            return [needed_slots]

        min_chunk_minutes = task.min_chunk_minutes or self.slot_minutes
        chunk_slots = max(
            1,
            self._round_up_to_slot(min_chunk_minutes) // self.slot_minutes,
        )
        chunk_slots = min(chunk_slots, needed_slots)
        full_chunks, remainder = divmod(needed_slots, chunk_slots)

        sizes = [chunk_slots] * full_chunks
        if remainder:
            sizes.append(remainder)
        return sizes or [needed_slots]

    @staticmethod
    def _earliness_coeff(score_int: int) -> int:
        """Небольшой штраф за позднее начало, чтобы порядок был стабильным."""
        return max(1, score_int)
