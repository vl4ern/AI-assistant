import time
from datetime import datetime
from typing import List, Dict
from integration.interfaces import IServiceAdapter, ICacheStorage
from integration.conflict_resolver import ConflictResolver
from integration.retry_queue import RetryQueue
from models.sync import SyncResult
from models.task import Task


class SyncScheduler:
    """Планировщик синхронизации"""

    def __init__(
        self, cache: ICacheStorage, resolver: ConflictResolver, retry_queue: RetryQueue
    ):
        self.cache = cache
        self.resolver = resolver
        self.retry_queue = retry_queue
        self.adapters: Dict[str, IServiceAdapter] = {}
        self.last_sync_time: Dict[str, datetime] = {}

    def register_adapter(self, name: str, adapter: IServiceAdapter):
        """Регистрация адаптера для синхронизации"""
        self.adapters[name] = adapter
        self.last_sync_time[name] = datetime.now()

    def sync_all(self) -> SyncResult:
        """Запуск синхронизации для всех зарегистрированных адаптеров"""
        result = SyncResult()

        for name, adapter in self.adapters.items():
            try:
                self._sync_adapter(name, adapter, result)
            except Exception as e:
                result.errors.append(f"{name}: {str(e)}")
                result.success = False

        return result

    def _sync_adapter(self, name: str, adapter: IServiceAdapter, result: SyncResult):
        """Синхронизация одного адаптера"""
        since = self.last_sync_time.get(name)

        # Получаем изменения из внешнего сервиса
        remote_tasks = adapter.fetch_changes(since)

        for remote_task in remote_tasks:
            local_task = self.cache.get_task_by_external_id(
                remote_task.external_id, remote_task.source_type.value
            )

            if local_task is None:
                # Новая задача
                self.cache.save_task(remote_task)
                result.tasks_synced += 1
            else:
                # Возможен конфликт
                resolved, conflicts = self.resolver.resolve(local_task, remote_task)
                self.cache.save_task(resolved)
                result.tasks_synced += 1
                result.conflicts_detected += len(conflicts)

                for conflict in conflicts:
                    conflict.send()

        # Обновляем время последней синхронизации
        self.last_sync_time[name] = datetime.now()

        # Обрабатываем очередь повторных попыток
        self.retry_queue.process(self.cache, self.adapters)
