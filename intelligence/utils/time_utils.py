from __future__ import annotations
from datetime import datetime, timedelta


def build_working_windows(
    start_at: datetime,
    end_at: datetime,
    wake_start_hour: int,
    wake_end_hour: int,
) -> list[tuple[datetime, datetime]]:
    """
    Генерирует рабочие интервалы (время бодрствования) на каждый день
    от start_at до end_at.
    """
    windows: list[tuple[datetime, datetime]] = []
    # Идём по дням, начиная с полуночи первого дня
    day_cursor = start_at.replace(hour=0, minute=0, second=0, microsecond=0)

    while day_cursor < end_at:
        # Начало рабочего окна сегодня = этот день + час пробуждения
        day_start = day_cursor.replace(
            hour=wake_start_hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        # Конец рабочего окна: если wake_end_hour == 24, то это начало следующих суток,
        # иначе – заданный час сегодня._build_working_windows
        if wake_end_hour == 24:
            day_end = day_cursor + timedelta(days=1)
        else:
            day_end = day_cursor.replace(
                hour=wake_end_hour,
                minute=0,
                second=0,
                microsecond=0,
            )

        # Обрезаем окно границами планирования (start_at, end_at)
        window_start = max(day_start, start_at)
        window_end = min(day_end, end_at)

        # Добавляем, только если окно не пустое
        if window_end > window_start:
            windows.append((window_start, window_end))

        day_cursor += timedelta(days=1)

    return windows
