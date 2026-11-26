from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from app.modules.integrations.integration.sync_scheduler import SyncScheduler
from app.modules.integrations.models.sync import ConflictNotification, SyncResult
from app.modules.integrations.models.task import Task
from app.modules.knowledge.models import EventCreate, TaskCreate
from app.modules.knowledge.service import KnowledgeService

DEFAULT_EVENT_DURATION_MINUTES = 90

SOURCE_TO_EVENT_SOURCE = {
    "IIS": "bsuir-lms",
    "google_calendar": "google-calendar",
}


class KnowledgeIngestClient:
    """
    Прямой клиент записи фактов в Knowledge Base (без HTTP).

    Занятия IIS и события Google Calendar сохраняются как события
    базы знаний (занятое время для планировщика), остальные — как задачи.
    Дедупликация защищает от повторного создания при пересинхронизации.
    """

    def __init__(self, knowledge_service: KnowledgeService) -> None:
        self._kb = knowledge_service
        self._event_keys: Optional[set[tuple[str, str, datetime]]] = None
        self._task_keys: Optional[set[tuple[str, Optional[datetime]]]] = None

    def ingest_fact(self, fact: dict) -> None:
        fact_type = fact.get("type")

        if fact_type == "task":
            self._ingest_task_fact(fact)
        elif fact_type == "sync_completed":
            print(
                f"[KBBridge] KB: синхронизация {fact.get('adapter')} завершена "
                f"({fact.get('tasks_synced')} задач, "
                f"{fact.get('conflicts_detected')} конфликтов)"
            )
        elif fact_type == "sync_error":
            print(f"[KBBridge] KB: ошибка синхронизации {fact.get('adapter')}: {fact.get('error')}")
        elif fact_type == "conflict":
            print(
                f"[KBBridge] KB: конфликт по задаче {fact.get('task_id')}, "
                f"поля: {fact.get('fields')}, предложение: {fact.get('suggestion')}"
            )
        elif fact_type == "task_deleted":
            # База знаний хранит факты immutable и не поддерживает удаление.
            print(f"[KBBridge] KB: задача {fact.get('external_id')} удалена из источника")

    def _ingest_task_fact(self, fact: dict) -> None:
        entity_type = fact.get("entity_type") or "manual_task"
        due_date = _parse_datetime(fact.get("due_date"))

        if entity_type in ("lesson", "calendar_event"):
            self._upsert_event(fact, due_date)
        else:
            self._upsert_task(fact, due_date)

    def _upsert_event(self, fact: dict, start: Optional[datetime]) -> None:
        if start is None:
            print(f"[KBBridge] Пропущено событие без времени: {fact.get('title')}")
            return

        source = SOURCE_TO_EVENT_SOURCE.get(fact.get("source"), fact.get("source") or "manual")
        title = fact.get("title") or "Событие внешнего календаря"
        key = (source, title, _normalize_key_datetime(start))

        if self._event_keys is None:
            self._event_keys = {
                (event.source, event.title, _normalize_key_datetime(event.start_at))
                for event in self._kb.list_events()
            }

        if key in self._event_keys:
            return

        duration_minutes = fact.get("duration_minutes") or DEFAULT_EVENT_DURATION_MINUTES
        end = start + timedelta(minutes=duration_minutes)

        event = self._kb.create_event(
            EventCreate(
                title=title,
                start_at=start,
                end_at=end,
                source=source,
            )
        )
        self._event_keys.add(key)
        print(f"[KBBridge] → KB: создано событие '{event.title}' ({source})")

    def _upsert_task(self, fact: dict, deadline: Optional[datetime]) -> None:
        title = fact.get("title") or "Задача из внешнего сервиса"
        key = (title, _normalize_key_datetime(deadline) if deadline else None)

        if self._task_keys is None:
            self._task_keys = {
                (task.title, _normalize_key_datetime(task.deadline) if task.deadline else None)
                for task in self._kb.list_tasks()
            }

        if key in self._task_keys:
            return

        task = self._kb.create_task(
            TaskCreate(
                title=title,
                description=fact.get("description"),
                estimated_minutes=max(15, fact.get("duration_minutes") or 30),
                priority=min(4, max(1, fact.get("priority") or 3)),
                deadline=deadline,
                project_id=fact.get("project_id") or None,
            )
        )
        self._task_keys.add(key)
        print(f"[KBBridge] → KB: создана задача '{task.title}'")


class KnowledgeBaseBridge:
    """
    Мост между модулем синхронизации и Knowledge Base.
    Преобразует события синхронизации в факты для KB.
    """

    def __init__(
        self,
        scheduler: SyncScheduler,
        kb_client: Optional[Any] = None,
    ):
        """
        Args:
            scheduler: экземпляр планировщика синхронизации
            kb_client: клиент записи фактов в KB
                (по умолчанию используется прямой клиент KnowledgeService)
        """
        self.scheduler = scheduler
        self.kb_client = kb_client

        self._subscribe_to_events()
        print("[KBBridge] Мост с Knowledge Base инициализирован")

    def _subscribe_to_events(self):
        """Подписка на события синхронизации"""
        self.scheduler.subscribe("task_created", self.on_task_created)
        self.scheduler.subscribe("task_updated", self.on_task_updated)
        self.scheduler.subscribe("task_deleted", self.on_task_deleted)
        self.scheduler.subscribe("sync_completed", self.on_sync_completed)
        self.scheduler.subscribe("sync_error", self.on_sync_error)
        self.scheduler.subscribe("conflict_detected", self.on_conflict_detected)
        print("[KBBridge] Подписки на события активированы")

    def on_task_created(self, task: Task):
        """Новая задача создана в кэше"""
        kb_fact = self._task_to_kb_fact(task, action="created")
        self._send_to_kb(kb_fact)

    def on_task_updated(self, task: Task, old_task: Task):
        """Задача обновлена"""
        kb_fact = self._task_to_kb_fact(task, action="updated")
        kb_fact["changes"] = self._detect_changes(old_task, task)
        self._send_to_kb(kb_fact)

    def on_task_deleted(self, task_id: str, external_id: str, source_type: str):
        """Задача удалена из кэша"""
        kb_fact = {
            "type": "task_deleted",
            "task_id": task_id,
            "external_id": external_id,
            "source_type": source_type,
            "timestamp": datetime.now().isoformat(),
        }
        self._send_to_kb(kb_fact)

    def on_sync_completed(self, adapter_name: str, result: SyncResult):
        """Синхронизация адаптера завершена"""
        kb_event = {
            "type": "sync_completed",
            "adapter": adapter_name,
            "tasks_synced": result.tasks_synced,
            "conflicts_detected": result.conflicts_detected,
            "success": result.success,
            "timestamp": datetime.now().isoformat(),
        }
        self._send_to_kb(kb_event)

    def on_sync_error(self, adapter_name: str, error: str):
        """Ошибка синхронизации"""
        kb_event = {
            "type": "sync_error",
            "adapter": adapter_name,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }
        self._send_to_kb(kb_event)

    def on_conflict_detected(self, conflict: ConflictNotification):
        """Обнаружен конфликт"""
        kb_event = {
            "type": "conflict",
            "conflict_id": conflict.conflict_id,
            "task_id": conflict.task_id,
            "fields": conflict.conflicting_fields,
            "suggestion": conflict.suggested_resolution,
            "timestamp": datetime.now().isoformat(),
        }
        self._send_to_kb(kb_event)

    def _task_to_kb_fact(self, task: Task, action: str) -> dict:
        """Преобразование Task в формат факта Knowledge Base."""
        fact = {
            "type": "task",
            "action": action,
            "id": task.id,
            "external_id": task.external_id,
            "source": task.source_type.value,
            "title": task.title,
            "description": task.description,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "duration_minutes": task.duration_minutes,
            "priority": task.priority,
            "status": task.status.value,
            "project_id": task.project_id,
            "labels": task.labels,
            "version": task.version,
            "last_modified": task.last_modified.isoformat(),
            "timestamp": datetime.now().isoformat(),
        }

        # Семантическая обработка для разных источников
        if task.source_type.value == "IIS":
            fact["entity_type"] = "lesson"
            extracted = self._extract_lesson_info(task.description)
            fact.update(extracted)
        elif task.source_type.value == "google_calendar":
            fact["entity_type"] = "calendar_event"
        else:
            fact["entity_type"] = "manual_task"

        return fact

    def _extract_lesson_info(self, description: str) -> dict:
        """Извлечение структурированной информации о занятии из описания"""
        info = {}
        if not description:
            return info

        for line in description.split("\n"):
            if line.startswith("Тип:"):
                info["lesson_type"] = line.replace("Тип:", "").strip()
            elif line.startswith("Аудитория:"):
                info["auditory"] = line.replace("Аудитория:", "").strip()
            elif line.startswith("Преподаватель:"):
                info["teacher"] = line.replace("Преподаватель:", "").strip()
            elif line.startswith("Недели:"):
                info["weeks"] = line.replace("Недели:", "").strip()
            elif line.startswith("Подгруппа:"):
                info["subgroup"] = line.replace("Подгруппа:", "").strip()

        return info

    def _detect_changes(self, old_task: Task, new_task: Task) -> List[str]:
        """Определение изменившихся полей между версиями задачи"""
        changes = []

        if old_task.title != new_task.title:
            changes.append("title")
        if old_task.description != new_task.description:
            changes.append("description")
        if old_task.due_date != new_task.due_date:
            changes.append("due_date")
        if old_task.priority != new_task.priority:
            changes.append("priority")
        if old_task.status != new_task.status:
            changes.append("status")
        if old_task.labels != new_task.labels:
            changes.append("labels")
        if old_task.duration_minutes != new_task.duration_minutes:
            changes.append("duration_minutes")

        return changes

    def _send_to_kb(self, fact: dict):
        """Отправка факта в Knowledge Base."""
        if self.kb_client is None:
            return
        try:
            self.kb_client.ingest_fact(fact)
        except Exception as e:
            print(f"[KBBridge] Ошибка записи в KB: {e}")

    def shutdown(self):
        """Корректное завершение"""
        self.scheduler.unsubscribe("task_created", self.on_task_created)
        self.scheduler.unsubscribe("task_updated", self.on_task_updated)
        self.scheduler.unsubscribe("task_deleted", self.on_task_deleted)
        self.scheduler.unsubscribe("sync_completed", self.on_sync_completed)
        self.scheduler.unsubscribe("sync_error", self.on_sync_error)
        self.scheduler.unsubscribe("conflict_detected", self.on_conflict_detected)
        print("[KBBridge] Мост остановлен")


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _normalize_key_datetime(value: datetime) -> datetime:
    """Приведение datetime к naive UTC для стабильных ключей дедупликации."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
