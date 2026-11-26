from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Minsk"


def app_timezone():
    """Часовой пояс приложения (переменная GOOGLE_TIMEZONE)."""
    name = os.getenv("GOOGLE_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — нет tzdata в окружении
        return timezone(timedelta(hours=3))


def to_utc(value: Optional[datetime]) -> Optional[datetime]:
    """naive-время локального пояса → aware UTC для TIMESTAMPTZ.

    Вся доменная логика (IIS, планировщик, Google) работает с naive-датами
    в поясе приложения. Без явной локализации psycopg трактует их как UTC,
    из-за чего время в интерфейсе и в Google уезжает на +3 часа.
    Уже aware-значения не трогаем.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=app_timezone()).astimezone(timezone.utc)
