import time
import threading
from datetime import datetime
from typing import List, Dict, Optional
from integration.interfaces import IServiceAdapter, ICacheStorage
from integration.conflict_resolver import ConflictResolver
from integration.retry_queue import RetryQueue
from models.sync import SyncResult
from models.task import Task


class SyncScheduler:
    """Планировщик синхронизации с поддержкой фонового режима"""

    def __init__(
        self, cache: ICacheStorage, resolver: ConflictResolver, retry_queue: RetryQueue
    ):
        self.cache = cache
        self.resolver = resolver
        self.retry_queue = retry_queue
        self.adapters: Dict[str, IServiceAdapter] = {}
        self.intervals: Dict[str, int] = {}  # имя_адаптера -> интервал в секундах
        self.last_sync_time: Dict[str, datetime] = {}

        # Для фонового режима
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def register_adapter(
        self, name: str, adapter: IServiceAdapter, sync_interval: int = 3600
    ):
        """
        Регистрация адаптера для синхронизации.
        sync_interval — интервал синхронизации в секундах (по умолчанию 1 час)
        """
        self.adapters[name] = adapter
        self.intervals[name] = sync_interval
        self.last_sync_time[name] = (
            datetime.min
        )  # Сразу запустится при старте фонового режима
        print(
            f"[SyncScheduler] Зарегистрирован адаптер '{name}' (интервал: {sync_interval}с)"
        )

    def sync_all(self) -> SyncResult:
        """Запуск синхронизации для всех зарегистрированных адаптеров (однократный)"""
        result = SyncResult()

        for name, adapter in self.adapters.items():
            try:
                self._sync_adapter(name, adapter, result)
            except Exception as e:
                error_msg = f"{name}: {str(e)}"
                result.errors.append(error_msg)
                result.success = False
                # Добавляем в очередь повторных попыток
                self.retry_queue.add_sync_retry(name, error_msg)

        return result

    def sync_adapter_now(self, name: str) -> Optional[SyncResult]:
        """Принудительная синхронизация одного адаптера"""
        adapter = self.adapters.get(name)
        if not adapter:
            return None

        result = SyncResult()
        try:
            self._sync_adapter(name, adapter, result)
        except Exception as e:
            result.errors.append(f"{name}: {str(e)}")
            result.success = False

        self.last_sync_time[name] = datetime.now()
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
                if self.cache.save_task(remote_task):
                    result.tasks_synced += 1
            else:
                # Возможен конфликт
                resolved, conflicts = self.resolver.resolve(local_task, remote_task)
                if self.cache.save_task(resolved):
                    result.tasks_synced += 1
                    result.conflicts_detected += len(conflicts)

                    for conflict in conflicts:
                        conflict.send()

        # Обновляем время последней синхронизации
        self.last_sync_time[name] = datetime.now()

        # Обрабатываем очередь повторных попыток
        self.retry_queue.process(self.cache, self.adapters)

    def start_background(self, check_interval: int = 10):
        """
        Запуск фоновой синхронизации в отдельном потоке.
        check_interval — как часто проверять необходимость синхронизации (сек)
        """
        if self._running:
            print("[SyncScheduler] Фоновый режим уже запущен")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._background_worker, args=(check_interval,), daemon=True
        )
        self._thread.start()
        print(
            f"[SyncScheduler] Запущен фоновый режим (проверка каждые {check_interval}с)"
        )

    def stop_background(self):
        """Остановка фоновой синхронизации"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            print("[SyncScheduler] Фоновый режим остановлен")

    def _background_worker(self, check_interval: int):
        """Фоновый воркер с проверкой интервалов"""
        while self._running:
            now = datetime.now()

            for name, adapter in self.adapters.items():
                last_sync = self.last_sync_time.get(name, datetime.min)
                interval = self.intervals.get(name, 3600)

                # Проверяем, пора ли синхронизировать
                if (now - last_sync).total_seconds() >= interval:
                    print(f"[SyncScheduler] Запуск плановой синхронизации '{name}'")
                    try:
                        result = self.sync_adapter_now(name)
                        if result and result.errors:
                            print(f"[SyncScheduler] Ошибки '{name}': {result.errors}")
                    except Exception as e:
                        print(f"[SyncScheduler] Ошибка синхронизации '{name}': {e}")
                        self.retry_queue.add_sync_retry(name, str(e))

            # Обрабатываем очередь повторных попыток
            self.retry_queue.process(self.cache, self.adapters)

            # Ждём до следующей проверки
            time.sleep(check_interval)
