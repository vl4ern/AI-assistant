import json
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from integration.sync_scheduler import SyncScheduler
from models.task import Task
from models.sync import ConflictNotification, SyncResult


class KnowledgeBaseBridge:
    """
    Мост между модулем синхронизации и Knowledge Base.
    Преобразует события синхронизации в факты для KB.
    """

    def __init__(
        self,
        scheduler: SyncScheduler,
        kb_api_url: str = "http://localhost:8000/api/knowledge",
        use_http: bool = True,
        direct_kb_client: Optional[Any] = None,
    ):
        """
        Args:
            scheduler: экземпляр планировщика синхронизации
            kb_api_url: URL API Knowledge Base (если use_http=True)
            use_http: использовать HTTP API или прямой клиент Python
            direct_kb_client: прямой клиент KB (если use_http=False)
        """
        self.scheduler = scheduler
        self.kb_api_url = kb_api_url
        self.use_http = use_http
        self.direct_kb_client = direct_kb_client

        # Подписываемся на все важные события
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
        print(f"[KBBridge] → KB: создана задача '{task.title}'")

    def on_task_updated(self, task: Task, old_task: Task):
        """Задача обновлена"""
        kb_fact = self._task_to_kb_fact(task, action="updated")
        # Добавляем информацию об изменениях
        changes = self._detect_changes(old_task, task)
        kb_fact["changes"] = changes
        self._send_to_kb(kb_fact)
        print(
            f"[KBBridge] → KB: обновлена задача '{task.title}' (изменений: {len(changes)})"
        )

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
        print(f"[KBBridge] → KB: удалена задача {external_id}")

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
        print(
            f"[KBBridge] → KB: синхронизация {adapter_name} завершена ({result.tasks_synced} задач)"
        )

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

    def force_sync_all_tasks(self):
        """
        Принудительная отправка ВСЕХ задач из кэша в KB.
        Полезно при первом подключении или восстановлении после сбоя.
        """
        print("[KBBridge] Полная синхронизация с KB...")
        all_tasks = self.scheduler.cache.get_all_tasks()

        for task in all_tasks:
            kb_fact = self._task_to_kb_fact(task, action="synced")
            self._send_to_kb(kb_fact)

        print(f"[KBBridge] Отправлено {len(all_tasks)} задач в KB")

    def _task_to_kb_fact(self, task: Task, action: str) -> dict:
        """
        Преобразование Task в формат Knowledge Base.

        Здесь можно добавить любую логику:
        - Разбиение на сущности (Lesson, Event, Task)
        - Извлечение из description структурированных данных
        - Связывание с другими сущностями в KB
        """
        # Базовое представление
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

        # Дополнительная семантическая обработка для IIS занятий
        if task.source_type.value == "IIS":
            fact["entity_type"] = "lesson"
            # Извлечение информации из description (аудитория, преподаватель и т.д.)
            extracted = self._extract_lesson_info(task.description)
            fact.update(extracted)
        elif task.source_type.value == "google_calendar":
            fact["entity_type"] = "calendar_event"
        elif task.source_type.value == "manual":
            fact["entity_type"] = "manual_task"

        return fact

    def _extract_lesson_info(self, description: str) -> dict:
        """Извлечение структурированной информации о занятии из описания"""
        info = {}
        lines = description.split("\n")

        for line in lines:
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
        """
        Отправка факта в Knowledge Base.
        Поддерживает HTTP API или прямой вызов.
        """
        if self.use_http:
            self._send_via_http(fact)
        elif self.direct_kb_client:
            self._send_via_direct_client(fact)
        else:
            print(f"[KBBridge] Ошибка: не настроен способ отправки в KB")

    def _send_via_http(self, fact: dict):
        """Отправка через HTTP API Knowledge Base"""
        try:
            response = requests.post(
                self.kb_api_url,
                json=fact,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            if response.status_code >= 400:
                print(
                    f"[KBBridge] Ошибка KB API ({response.status_code}): {response.text}"
                )
        except requests.exceptions.RequestException as e:
            print(f"[KBBridge] Ошибка соединения с KB: {e}")
            # Здесь можно добавить в retry_queue

    def _send_via_direct_client(self, fact: dict):
        """Отправка через прямой Python клиент KB"""
        try:
            # Предполагается, что у KB есть метод ingest_fact
            self.direct_kb_client.ingest_fact(fact)
        except Exception as e:
            print(f"[KBBridge] Ошибка прямого вызова KB: {e}")

    def shutdown(self):
        """Корректное завершение"""
        self.scheduler.unsubscribe("task_created", self.on_task_created)
        self.scheduler.unsubscribe("task_updated", self.on_task_updated)
        self.scheduler.unsubscribe("task_deleted", self.on_task_deleted)
        self.scheduler.unsubscribe("sync_completed", self.on_sync_completed)
        self.scheduler.unsubscribe("sync_error", self.on_sync_error)
        self.scheduler.unsubscribe("conflict_detected", self.on_conflict_detected)
        print("[KBBridge] Мост остановлен")
