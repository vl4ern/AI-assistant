from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum
from .task import Task, SourceType


class ConflictResolutionStrategy(Enum):
    LAST_WRITE_WINS = "lww"
    MERGE_WITH_NOTIFY = "merge_with_notify"
    MANUAL = "manual"


@dataclass
class SyncCommand:
    """Команда на синхронизацию"""

    command: str  # "upsert_task", "delete_task"
    task: Task
    source_type: SourceType
    sync_immediately: bool = True

    def execute(self) -> bool:
        """Заглушка: будет реализована в модуле синхронизации"""
        # Здесь будет реальная отправка во внешний сервис
        return True


@dataclass
class SyncResult:
    """Результат синхронизации"""

    success: bool = True
    tasks_synced: int = 0
    conflicts_detected: int = 0
    errors: List[str] = field(default_factory=list)
    sync_duration_ms: int = 0


@dataclass
class ConflictNotification:
    """Уведомление о конфликте"""

    conflict_id: str
    task_id: str
    external_service: SourceType
    local_version: int
    remote_version: int
    conflicting_fields: List[str]
    suggested_resolution: str
    timestamp: datetime = field(default_factory=datetime.now)

    def send(self) -> None:
        """Отправка уведомления пользователю"""
        print(f"[CONFLICT] {self.conflict_id}: {self.conflicting_fields}")
        # В системе здесь будет вызов UI

    def get_details(self) -> str:
        return f"Конфликт в задаче {self.task_id}: поля {self.conflicting_fields}"
