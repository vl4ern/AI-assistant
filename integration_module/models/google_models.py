from datetime import datetime, timezone
from typing import Optional, List
from models.task import Task, SourceType, TaskStatus, utc_now
import logging

logger = logging.getLogger(__name__)


class GoogleCalendarEvent:
    """Промежуточная модель события Google Calendar."""

    @staticmethod
    def from_google_event(event: dict) -> Optional[Task]:
        """Конвертация события Google Calendar API в Task.
        Возвращает None, если событие не подлежит учёту как задача."""
        event_id = event.get("id")
        if not event_id:
            return None

        # Отменённые события больше не являются задачами.
        # Возвращаем None — scheduler удалит их из кэша через cleanup.
        if event.get("status") == "cancelled":
            return None

        summary = event.get("summary", "Без названия")
        description = event.get("description", "")

        start = event.get("start", {})
        end = event.get("end", {})

        due_date = None
        duration_minutes = 30

        if "dateTime" in start:
            due_date = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=timezone.utc)
            end_dt = datetime.fromisoformat(
                end.get("dateTime", start["dateTime"]).replace("Z", "+00:00")
            )
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            duration_minutes = max(int((end_dt - due_date).total_seconds() / 60), 15)
        elif "date" in start:
            due_date = datetime.strptime(start["date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            duration_minutes = 24 * 60
            logger.debug("[GoogleCalendar] All-day событие: %s (%s)", event_id, due_date)
        else:
            return None

        # Метки — из extendedProperties (в Calendar поля "labels" нет).
        labels: List[str] = []
        ext = event.get("extendedProperties", {}).get("private", {})
        if "labels" in ext:
            labels = [l.strip() for l in ext["labels"].split(",") if l.strip()]
        if event.get("colorId"):
            labels.append(f"color:{event['colorId']}")

        # Приоритет — по наличию напоминаний.
        reminders = event.get("reminders", {})
        use_default = reminders.get("useDefault", True)
        overrides = reminders.get("overrides", [])
        has_reminders = use_default or bool(overrides)
        priority = 3 if has_reminders else 4

        updated_raw = event.get("updated") or utc_now().isoformat()
        last_modified = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)

        return Task(
            id=f"gc_{event_id}",
            external_id=event_id,
            source_type=SourceType.GOOGLE_CALENDAR,
            title=summary,
            description=description,
            due_date=due_date,
            duration_minutes=duration_minutes,
            priority=priority,
            status=TaskStatus.PENDING,
            labels=labels,
            last_modified=last_modified,
            version=event.get("sequence", 1),
        )
