import os
from datetime import datetime, timedelta, timezone, tzinfo
from typing import List, Optional

from app.modules.integrations.models.task import SourceType, Task, TaskStatus

# Метка, которой помечаются события, созданные самим ассистентом
# (экспорт плана). При чтении календаря такие события пропускаются,
# иначе запланированные слоты вернулись бы обратно как «занятое время».
EXPORT_MARKER_KEY = "ai_assistant"

_DEFAULT_TZ_NAME = "Europe/Minsk"


def get_local_tz() -> tzinfo:
    """Локальный часовой пояс приложения (GOOGLE_TIMEZONE, по умолчанию Минск)."""
    name = os.getenv("GOOGLE_TIMEZONE", _DEFAULT_TZ_NAME)
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — нет tzdata в окружении
        return timezone(timedelta(hours=3))


def to_local_naive(value: datetime) -> datetime:
    """aware → naive в локальном поясе; naive остаётся как есть.

    Остальная часть приложения (IIS, кэш, planner) работает с naive-датами,
    поэтому события Google приводим к тому же виду.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(get_local_tz()).replace(tzinfo=None)


def _parse_google_datetime(raw: str) -> datetime:
    return to_local_naive(datetime.fromisoformat(raw.replace("Z", "+00:00")))


class GoogleCalendarEvent:
    """Промежуточная модель события Google Calendar"""

    @staticmethod
    def from_google_event(event: dict) -> Optional[Task]:
        """Конвертация события Google Calendar API в Task.

        Возвращает None, если событие не нужно учитывать (создано самим
        ассистентом или не имеет id).
        """
        event_id = event.get("id")
        if not event_id:
            return None

        private_props = event.get("extendedProperties", {}).get("private", {})
        if private_props.get(EXPORT_MARKER_KEY):
            return None

        summary = event.get("summary", "Без названия")
        description = event.get("description", "")

        start = event.get("start", {})
        end = event.get("end", {})

        due_date = None
        duration_minutes = 30

        if "dateTime" in start:
            due_date = _parse_google_datetime(start["dateTime"])
            end_date = _parse_google_datetime(end.get("dateTime", start["dateTime"]))
            duration_minutes = max(int((end_date - due_date).total_seconds() / 60), 15)
        elif "date" in start:
            # Событие на весь день
            due_date = datetime.strptime(start["date"], "%Y-%m-%d")
            duration_minutes = 24 * 60

        labels: List[str] = list(event.get("labels", []))
        if "colorId" in event:
            labels.append(f"color:{event['colorId']}")

        status = TaskStatus.PENDING
        if event.get("status") == "cancelled":
            status = TaskStatus.ARCHIVED

        # Определяем приоритет по наличию напоминаний
        reminders = event.get("reminders", {}).get("useDefault", True)
        priority = 3  # По умолчанию средний
        if not reminders:
            priority = 4  # Низкий приоритет для событий без напоминаний

        updated_raw = event.get("updated")
        last_modified = (
            _parse_google_datetime(updated_raw) if updated_raw else datetime.now()
        )

        return Task(
            id=f"gc_{event_id}",  # Префикс для идентификации источника
            external_id=event_id,
            source_type=SourceType.GOOGLE_CALENDAR,
            title=summary,
            description=description,
            due_date=due_date,
            duration_minutes=duration_minutes,
            priority=priority,
            status=status,
            labels=labels,
            last_modified=last_modified,
            version=event.get("sequence", 1),
        )
