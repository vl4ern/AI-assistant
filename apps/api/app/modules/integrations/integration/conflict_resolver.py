import uuid
from datetime import datetime
from typing import List, Tuple

from app.modules.integrations.integration.interfaces import ICacheStorage
from app.modules.integrations.models.sync import (
    ConflictNotification,
    ConflictResolutionStrategy,
)
from app.modules.integrations.models.task import Task


class ConflictResolver:
    """
    Обработчик конфликтов при параллельном редактировании.

    Версия на основе наработок коллеги (ветка integration_module2):
    по конфликтующим полям выигрывает более свежая сторона, неконфликтующие
    поля добираются из второй стороны, уведомление создаётся только
    при реальном расхождении полей.
    """

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
        notifications: List[ConflictNotification] = []
        conflicting_fields = self._find_conflicting_fields(local_task, remote_task)

        # Ничего не поменялось — возвращаем локальную как есть.
        if not conflicting_fields and local_task.version == remote_task.version:
            return local_task, notifications

        # Поля совпадают, но версия у remote выше — это метаданные,
        # просто берём remote как более свежий.
        if not conflicting_fields:
            resolved = remote_task
            resolved.version = max(local_task.version, remote_task.version) + 1
            resolved.last_modified = datetime.now()
            return resolved, notifications

        # Есть реальные расхождения полей.
        if self.strategy == ConflictResolutionStrategy.LAST_WRITE_WINS:
            resolved = (
                remote_task
                if remote_task.last_modified >= local_task.last_modified
                else local_task
            )
            resolved = self._merge_non_conflicting(local_task, remote_task, resolved)

        elif self.strategy == ConflictResolutionStrategy.MERGE_WITH_NOTIFY:
            resolved = self._merge_with_notify(
                local_task, remote_task, conflicting_fields
            )
            notifications.append(
                self._create_notification(local_task, remote_task, conflicting_fields)
            )

        else:  # MANUAL
            resolved = local_task
            notifications.append(
                self._create_notification(local_task, remote_task, conflicting_fields)
            )

        resolved.version = max(local_task.version, remote_task.version) + 1
        resolved.last_modified = datetime.now()
        return resolved, notifications

    def _find_conflicting_fields(self, local: Task, remote: Task) -> List[str]:
        """Поиск полей, в которых есть расхождения"""
        conflicting = []

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
        if local.duration_minutes != remote.duration_minutes:
            conflicting.append("duration_minutes")
        if local.project_id != remote.project_id:
            conflicting.append("project_id")
        if set(local.labels) != set(remote.labels):
            conflicting.append("labels")

        return conflicting

    def _merge_non_conflicting(
        self, local: Task, remote: Task, base: Task
    ) -> Task:
        """Добирает неконфликтующие поля из второй стороны."""
        other = remote if base is local else local
        if not base.description:
            base.description = other.description
        if not base.project_id:
            base.project_id = other.project_id
        base.labels = list({*base.labels, *other.labels})
        return base

    def _merge_with_notify(
        self, local: Task, remote: Task, conflicting_fields: List[str]
    ) -> Task:
        """Слияние с уведомлением: по конфликтующим полям приоритет у более поздней версии"""
        prefer_remote = remote.last_modified >= local.last_modified

        def pick(field_name: str, local_val, remote_val):
            if field_name not in conflicting_fields:
                return local_val
            return remote_val if prefer_remote else local_val

        return Task(
            id=local.id,
            external_id=local.external_id,
            source_type=local.source_type,
            title=pick("title", local.title, remote.title),
            description=pick("description", local.description, remote.description),
            due_date=pick("due_date", local.due_date, remote.due_date),
            duration_minutes=pick(
                "duration_minutes", local.duration_minutes, remote.duration_minutes
            ),
            priority=pick("priority", local.priority, remote.priority),
            status=pick("status", local.status, remote.status),
            project_id=pick("project_id", local.project_id, remote.project_id),
            labels=list({*local.labels, *remote.labels}),
            group_number=remote.group_number or local.group_number,
            last_modified=datetime.now(),
            version=max(local.version, remote.version),
        )

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
