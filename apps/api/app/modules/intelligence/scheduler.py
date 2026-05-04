# -*- coding: utf-8 -*-
# Импортируем аннотации будущего, чтобы можно было использовать list[Task] и т.п. без кавычек
from __future__ import annotations

# Стандартные модули Python
from datetime import datetime, timedelta, timezone
import math

# Импортируем модели данных самого планировщика (SchedulePlan, ScheduledSlot)
from app.modules.intelligence.models import SchedulePlan, ScheduledSlot
# Импортируем модели сущностей из модуля knowledge (Task, Event)
from app.modules.knowledge.models import Event, Task
from app.modules.intelligence.utils.time_utils import build_working_windows

class GreedyScheduler:
    """
    Жадный планировщик задач.

    Принимает:
      - slot_minutes: минимальный размер временного слота (например, 15 мин).
      - horizon_days: на сколько дней вперёд строим расписание.
      - wake_start_hour, wake_end_hour: границы «рабочего дня» пользователя, когда он бодрствует
        и готов выполнять задачи.
    """

    def __init__(
        self,
        slot_minutes: int,
        horizon_days: int,
        wake_start_hour: int,
        wake_end_hour: int,
    ) -> None:
        # Сохраняем настройки в объект
        self.slot_minutes = slot_minutes
        self.horizon_days = horizon_days
        self.wake_start_hour = wake_start_hour
        self.wake_end_hour = wake_end_hour

    def build_plan(
        self,
        tasks: list[Task],             # все задачи пользователя
        events: list[Event],           # все занятые события (календарь, пары и т.п.)
        now: datetime,                 # текущий момент (обычно UTC)
        task_scores: dict[str, float] | None = None,  # словарь {task.id: скоринговый балл}, если уже рассчитан
    ) -> SchedulePlan:
        """
        Главный метод построения расписания.
        Возвращает SchedulePlan со слотами, нераспределёнными задачами и prime-задачей.
        """

        # Приводим «сейчас» к UTC, если вдруг пришло без таймзоны
        current = self._to_utc(now)
        # Определяем крайний срок планирования: текущий момент + horizon_days дней
        horizon_end = current + timedelta(days=self.horizon_days)

        # --- Шаг 1: Отбираем задачи, которые можно планировать ---

        # Множество id задач, которые ещё не завершены (статус не "completed")
        unfinished_ids = {task.id for task in tasks if task.status != "completed"}

        # Задачи, которые можно двигать (статус todo или in_progress и разрешён автосдвиг)
        movable = [
            task
            for task in tasks
            if task.status in {"todo", "in_progress"} and task.auto_reschedule
        ]

        # Из двигаемых оставляем только те, у которых нет невыполненных зависимостей
        # (т.е. все задачи, от которых она зависит, уже завершены)
        candidates = [
            task
            for task in movable
            if not any(dep_id in unfinished_ids for dep_id in task.depends_on)
        ]

        # --- Шаг 2: Формируем занятые интервалы (то, что нельзя использовать) ---

        # Занятые интервалы из событий (календари, пары, встречи)
        fixed_busy_intervals = [(event.start_at, event.end_at) for event in events]

        # Добавляем сюда также интервалы, занятые несдвигаемыми задачами,
        # у которых уже есть запланированное время (scheduled_start/scheduled_end).
        # Эти задачи мы не имеем права двигать, они как якорь.
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

        # --- Шаг 3: Вычисляем свободные окна (когда пользователь бодрствует и ничем не занят) ---

        free_windows = self._find_free_windows(current, horizon_end, fixed_busy_intervals)

        # --- Шаг 4: Ранжируем задачи по скоринговым баллам ---

        # Если нам не передали готовый score_map, создаём пустой (по умолчанию 0)
        score_map = task_scores or {}
        # Сортируем кандидатов по убыванию их скорингового балла (самые важные – вперёд)
        ranked = sorted(
            [(float(score_map.get(task.id, 0.0)), task) for task in candidates],
            key=lambda item: item[0],
            reverse=True,
        )

        # --- Шаг 5: Жадно раскладываем задачи по свободным окнам ---

        # Здесь будем накапливать готовые запланированные слоты
        scheduled_slots: list[ScheduledSlot] = []
        # Список id задач, которые вообще не удалось разместить
        unscheduled_task_ids: list[str] = []
        # Вспомогательный set, чтобы не дублировать id в unscheduled_task_ids
        unscheduled_seen: set[str] = set()

        # Идём по задачам в порядке убывания важности
        for task_score, task in ranked:
            # Округляем требуемое время до ближайшего слота (например, 13 мин -> 15 мин)
            needed_minutes = self._round_up_to_slot(task.estimated_minutes)
            # Самый поздний срок, когда задачу ещё можно закончить = дедлайн или конец горизонта планирования
            latest_end = self._to_utc(task.deadline) if task.deadline else horizon_end

            # Пытаемся найти цельное окно под задачу целиком
            whole_slot = self._allocate_window(free_windows, needed_minutes, latest_end)
            if whole_slot is not None:
                # Если нашли, сразу используем: начало и конец интервала
                start_at, end_at = whole_slot
                scheduled_slots.append(
                    ScheduledSlot(
                        task_id=task.id,
                        title=task.title,
                        start_at=start_at,
                        end_at=end_at,
                        score=task_score,
                    )
                )
                continue   # переходим к следующей задаче

            # Если цельного окна нет, проверяем, можно ли разбить задачу на части
            if not task.allow_split:
                # Разбивать нельзя — записываем в неразмещённые, если ещё не записана
                if task.id not in unscheduled_seen:
                    unscheduled_task_ids.append(task.id)
                    unscheduled_seen.add(task.id)
                continue

            # Если разбивать можно, пробуем разместить по кускам
            min_chunk = task.min_chunk_minutes or self.slot_minutes  # минимальный размер куска
            split_slots, remaining_minutes = self._allocate_split_windows(
                free_windows=free_windows,
                total_minutes=needed_minutes,
                latest_end=latest_end,
                min_chunk_minutes=min_chunk,
            )

            # Все найденные куски добавляем в расписание
            for start_at, end_at in split_slots:
                scheduled_slots.append(
                    ScheduledSlot(
                        task_id=task.id,
                        title=task.title,
                        start_at=start_at,
                        end_at=end_at,
                        score=task_score,
                    )
                )

            # Если что-то осталось неразмещённым (например, не хватило окон),
            # записываем задачу в неразмещённые, если ещё не записана
            if remaining_minutes > 0 and task.id not in unscheduled_seen:
                unscheduled_task_ids.append(task.id)
                unscheduled_seen.add(task.id)

        # --- Шаг 6: Финальная сборка результата ---

        # Сортируем все запланированные слоты по времени начала (чтобы выдать в хронологическом порядке)
        scheduled_slots.sort(key=lambda item: item.start_at)
        # Первая задача сегодня (слот который начинается раньше всех) объявляется prime-задачей
        prime_task_id = scheduled_slots[0].task_id if scheduled_slots else None

        return SchedulePlan(
            generated_at=current,
            slots=scheduled_slots,
            unscheduled_task_ids=unscheduled_task_ids,
            prime_task_id=prime_task_id,
        )

    # -------------------------------------------------------------------------
    # Вспомогательные методы планировщика
    # -------------------------------------------------------------------------

    def _allocate_split_windows(
        self,
        free_windows: list[tuple[datetime, datetime]],
        total_minutes: int,
        latest_end: datetime,
        min_chunk_minutes: int,
    ) -> tuple[list[tuple[datetime, datetime]], int]:
        """
        Пытается разместить задачу по кускам.
        Возвращает:
          - список найденных интервалов (начало, конец)
          - остаток минут, которые не удалось разместить (0 если всё разместили)
        """
        slots: list[tuple[datetime, datetime]] = []
        remaining = total_minutes   # сколько ещё минут разместить

        # Размер куска: не меньше минимального и выровнен по self.slot_minutes
        chunk_minutes = self._normalize_chunk_size(min_chunk_minutes)

        while remaining > 0:
            # Берём кусок не больше того, что требуется доразместить
            next_chunk = min(chunk_minutes, remaining)
            # Пытаемся найти окно под этот кусок
            slot = self._allocate_window(free_windows, next_chunk, latest_end)
            if slot is None:
                break   # больше ни одного окна нет – выходим

            slots.append(slot)
            remaining -= next_chunk

        return slots, remaining

    def _normalize_chunk_size(self, minutes: int) -> int:
        """Округляет минимальный размер куска до кратного slot_minutes, но не меньше слота."""
        return max(self.slot_minutes, self._round_up_to_slot(minutes))

    def _find_free_windows(
        self,
        start_at: datetime,
        end_at: datetime,
        busy_intervals: list[tuple[datetime, datetime]],
    ) -> list[tuple[datetime, datetime]]:
        """
        Основной метод поиска свободных временных окон.
        1. Строим все рабочие (бодрствующие) периоды внутри [start_at, end_at].
        2. Вычитаем из них занятые интервалы (busy_intervals).
        3. Возвращаем только те окна, где длина > 0.
        """
        # Генерируем окна бодрствования по дням
        working_windows = build_working_windows(start_at, end_at, self.wake_start_hour, self.wake_end_hour)
        # Приводим все занятые интервалы к UTC и удаляем кривые (None, отрицательные)
        busy = self._normalize_intervals(busy_intervals)

        free_windows = working_windows   # начнём с полных рабочих периодов
        # Последовательно вырезаем каждый занятый интервал
        for busy_start, busy_end in busy:
            free_windows = self._subtract_interval(free_windows, busy_start, busy_end)

        # Оставляем только ненулевые окна (окно может схлопнуться после вычитаний)
        return [window for window in free_windows if window[1] > window[0]]


    @staticmethod
    def _normalize_intervals(
        intervals: list[tuple[datetime | None, datetime | None]],
    ) -> list[tuple[datetime, datetime]]:
        """
        Приводит список интервалов к UTC, отбрасывает некорректные (None или конец раньше начала).
        Сортирует по времени начала.
        """
        normalized: list[tuple[datetime, datetime]] = []
        for start_at, end_at in intervals:
            # Пропускаем интервалы, у которых нет начала/конца или конец ≤ начала
            if start_at is None or end_at is None or end_at <= start_at:
                continue
            # Приводим к UTC и добавляем
            normalized.append((GreedyScheduler._to_utc(start_at), GreedyScheduler._to_utc(end_at)))
        # Сортируем по началу – важно для последующего вырезания
        normalized.sort(key=lambda interval: interval[0])
        return normalized

    @staticmethod
    def _subtract_interval(
        windows: list[tuple[datetime, datetime]],
        busy_start: datetime,
        busy_end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """
        Вырезает занятый интервал из списка свободных окон.
        Если занятый интервал пересекается с окном, окно разрезается на две части (до и после занятого).
        """
        result: list[tuple[datetime, datetime]] = []

        for window_start, window_end in windows:
            # Занятый интервал полностью левее или правее окна — окно остаётся без изменений
            if busy_end <= window_start or busy_start >= window_end:
                result.append((window_start, window_end))
                continue

            # Иначе есть пересечение. Оставляем часть окна до занятого интервала, если она есть.
            if busy_start > window_start:
                result.append((window_start, busy_start))
            # И часть после занятого интервала, если она есть.
            if busy_end < window_end:
                result.append((busy_end, window_end))

        return result

    def _allocate_window(
        self,
        free_windows: list[tuple[datetime, datetime]],
        needed_minutes: int,
        latest_end: datetime,
    ) -> tuple[datetime, datetime] | None:
        """
        Пытается найти первое подходящее свободное окно, способное вместить задачу.
        Возвращает (начало, конец) размещения или None, если нет подходящего окна.
        """
        needed = timedelta(minutes=needed_minutes)

        for index, (window_start, window_end) in enumerate(free_windows):
            # Обрезаем окно с учётом дедлайна (latest_end)
            effective_end = min(window_end, latest_end)
            # Если эффективная длина меньше нужной, это окно не подходит
            if effective_end - window_start < needed:
                continue

            # Нашли окно. Используем начало окна как начало задачи.
            start_at = window_start
            end_at = start_at + needed

            # Обновляем список свободных окон: убираем использованный кусок.
            # Если задача заняла не всё окно, оставляем хвост.
            if end_at < window_end:
                free_windows[index] = (end_at, window_end)
            else:
                # Иначе удаляем окно целиком
                free_windows.pop(index)

            return start_at, end_at

        return None

    def _round_up_to_slot(self, minutes: int) -> int:
        """Округляет минуты вверх до ближайшего числа, кратного slot_minutes."""
        chunks = math.ceil(minutes / self.slot_minutes)
        return chunks * self.slot_minutes

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        """Приводит datetime к UTC, даже если у него нет таймзоны (считаем, что тогда это UTC)."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
