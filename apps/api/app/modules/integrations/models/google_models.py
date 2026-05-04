from datetime import datetime, timedelta
from typing import List, Optional
from models.task import Task, SourceType, TaskStatus


class GoogleCalendarEvent:
    """Промежуточная модель события Google Calendar"""

    @staticmethod
    def from_google_event(event: dict) -> Optional[Task]:
        """Конвертация события Google Calendar API в Task"""
        event_id = event.get("id")
        summary = event.get("summary", "Без названия")
        description = event.get("description", "")

        # Определяем время
        start = event.get("start", {})
        end = event.get("end", {})

        due_date = None
        duration_minutes = 30

        if "dateTime" in start:
            due_date = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
            end_date = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00"))
            duration_minutes = int((end_date - due_date).total_seconds() / 60)
        elif "date" in start:
            # Событие на весь день
            due_date = datetime.strptime(start["date"], "%Y-%m-%d")
            duration_minutes = 24 * 60

        # Извлекаем метки из описания или настроек
        labels = event.get("labels", [])
        if "colorId" in event:
            labels.append(f"color:{event['colorId']}")

        # Статус задачи
        status = TaskStatus.PENDING
        if event.get("status") == "cancelled":
            status = TaskStatus.ARCHIVED

        # Определяем приоритет по наличию напоминаний
        reminders = event.get("reminders", {}).get("useDefault", True)
        priority = 3  # По умолчанию средний
        if not reminders:
            priority = 4  # Низкий приоритет для событий без напоминаний

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
            last_modified=datetime.fromisoformat(
                event.get("updated", datetime.now().isoformat()).replace("Z", "+00:00")
            ),
            version=event.get("sequence", 1),
        )
