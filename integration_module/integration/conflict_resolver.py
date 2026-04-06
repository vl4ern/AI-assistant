import uuid
from datetime import datetime
from typing import List, Tuple
from models.task import Task
from models.sync import ConflictNotification, ConflictResolutionStrategy
from integration.interfaces import ICacheStorage


class ConflictResolver:
    """Обработчик конфликтов при параллельном редактировании"""

    def __init__(
        self,
        cache_storage: ICacheStorage,
        strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.MERGE_WITH_NOTIFY,
    ):
        self.cache = cache_storage
        self.strategy = strategy

    def resolve(
        self, local_task: Task, remote_task: Task
    ) -> Tuple[Task, List[ConflictNotification]]:
        """
        Разрешение конфликта между локальной и удалённой версиями задачи
        Возвращает (решённую задачу, список уведомлений)
        """
        notifications = []

        if local_task.version == remote_task.version:
            return local_task, notifications  # Нет конфликта

        conflicting_fields = self._find_conflicting_fields(local_task, remote_task)

        if not conflicting_fields:
            # Нет реальных конфликтов, просто обновляем версию
            resolved = remote_task
            resolved.version = max(local_task.version, remote_task.version) + 1
            return resolved, notifications

        if self.strategy == ConflictResolutionStrategy.LAST_WRITE_WINS:
            resolved = (
                remote_task
                if remote_task.last_modified > local_task.last_modified
                else local_task
            )

        elif self.strategy == ConflictResolutionStrategy.MERGE_WITH_NOTIFY:
            resolved = self._merge_with_notify(
                local_task, remote_task, conflicting_fields
            )
            notifications.append(
                self._create_notification(local_task, remote_task, conflicting_fields)
            )

        else:  # MANUAL
            # Сохраняем обе версии, помечаем как конфликтующие
            resolved = local_task  # Временно
            notifications.append(
                self._create_notification(local_task, remote_task, conflicting_fields)
            )

        resolved.version = max(local_task.version, remote_task.version) + 1
        return resolved, notifications

    def _find_conflicting_fields(self, local: Task, remote: Task) -> List[str]:
        """Поиск полей, в которых есть расхождения"""
        conflicting = []

        # Сравниваем ключевые поля
        if local.title != remote.title:
            conflicting.append("title")
        if local.due_date != remote.due_date:
            conflicting.append("due_date")
        if local.priority != remote.priority:
            conflicting.append("priority")
        if local.status != remote.status:
            conflicting.append("status")
        if local.description != remote.description:
            conflicting.append("description")

        return conflicting

    def _merge_with_notify(
        self, local: Task, remote: Task, conflicting_fields: List[str]
    ) -> Task:
        """Слияние с уведомлением: приоритет у более поздней версии"""
        merged = Task(
            id=local.id,
            external_id=local.external_id,
            source_type=local.source_type,
            title=remote.title if "title" in conflicting_fields else local.title,
            description=(
                remote.description
                if "description" in conflicting_fields
                else local.description
            ),
            due_date=(
                remote.due_date if "due_date" in conflicting_fields else local.due_date
            ),
            duration_minutes=(
                remote.duration_minutes
                if remote.duration_minutes != local.duration_minutes
                else local.duration_minutes
            ),
            priority=(
                remote.priority if "priority" in conflicting_fields else local.priority
            ),
            status=remote.status if "status" in conflicting_fields else local.status,
            project_id=remote.project_id or local.project_id,
            labels=list(set(local.labels + remote.labels)),
            last_modified=datetime.now(),
            version=max(local.version, remote.version),
        )
        return merged

    def _create_notification(
        self, local: Task, remote: Task, conflicting_fields: List[str]
    ) -> ConflictNotification:
        """Создание уведомления о конфликте"""
        return ConflictNotification(
            conflict_id=str(uuid.uuid4()),
            task_id=local.id,
            external_service=local.source_type,
            local_version=local.version,
            remote_version=remote.version,
            conflicting_fields=conflicting_fields,
            suggested_resolution=f"merged: {', '.join(conflicting_fields)}",
        )
