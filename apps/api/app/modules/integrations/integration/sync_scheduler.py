import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Callable
from integration.interfaces import IServiceAdapter, ICacheStorage
from integration.conflict_resolver import ConflictResolver
from integration.retry_queue import RetryQueue
from models.sync import SyncResult
from models.task import Task


class SyncEvent:
    """Событие синхронизации для передачи подписчикам"""

    def __init__(self, event_type: str, data: dict):
        self.type = event_type
        self.data = data
        self.timestamp = datetime.now()


class SyncScheduler:
    """Планировщик синхронизации с поддержкой push-уведомлений"""

    def __init__(
        self, cache: ICacheStorage, resolver: ConflictResolver, retry_queue: RetryQueue
    ):
        self.cache = cache
        self.resolver = resolver
        self.retry_queue = retry_queue
        self.adapters: Dict[str, IServiceAdapter] = {}
        self.intervals: Dict[str, int] = {}
        self.last_sync_time: Dict[str, datetime] = {}

        # Система событий для push-уведомлений
        self._event_callbacks: Dict[str, List[Callable]] = {
            "task_created": [],
            "task_updated": [],
            "task_deleted": [],
            "sync_started": [],
            "sync_completed": [],
            "sync_error": [],
            "conflict_detected": [],
        }
        self._event_queue: List[SyncEvent] = []
        self._event_lock = threading.Lock()

        # Для фонового режима
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def subscribe(self, event_type: str, callback: Callable):
        """
        Подписка на события синхронизации.

        Типы событий:
        - task_created: (task: Task) — новая задача добавлена
        - task_updated: (task: Task, old_task: Task) — задача обновлена
        - task_deleted: (task_id: str, external_id: str) — задача удалена
        - sync_started: (adapter_name: str) — началась синхронизация адаптера
        - sync_completed: (adapter_name: str, result: SyncResult) — синхронизация завершена
        - sync_error: (adapter_name: str, error: str) — ошибка синхронизации
        - conflict_detected: (conflict: ConflictNotification) — обнаружен конфликт
        """
        if event_type in self._event_callbacks:
            self._event_callbacks[event_type].append(callback)
            print(f"[SyncScheduler] Подписка на '{event_type}' добавлена")
        else:
            raise ValueError(f"Неизвестный тип события: {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable):
        """Отписка от событий"""
        if event_type in self._event_callbacks:
            self._event_callbacks[event_type].remove(callback)

    def _emit_event(self, event_type: str, data: dict):
        """Вызов всех подписчиков события"""
        event = SyncEvent(event_type, data)

        # Сохраняем в очередь для асинхронной обработки (опционально)
        with self._event_lock:
            self._event_queue.append(event)

        # Вызываем всех подписчиков
        for callback in self._event_callbacks.get(event_type, []):
            try:
                callback(**data)
            except Exception as e:
                print(
                    f"[SyncScheduler] Ошибка в обработчике события '{event_type}': {e}"
                )

    def register_adapter(
        self, name: str, adapter: IServiceAdapter, sync_interval: int = 3600
    ):
        """Регистрация адаптера для синхронизации"""
        self.adapters[name] = adapter
        self.intervals[name] = sync_interval
        self.last_sync_time[name] = datetime.min
        print(
            f"[SyncScheduler] Зарегистрирован адаптер '{name}' (интервал: {sync_interval}с)"
        )

    def sync_all(self) -> SyncResult:
        """Запуск синхронизации для всех зарегистрированных адаптеров"""
        result = SyncResult()

        for name, adapter in self.adapters.items():
            try:
                self._emit_event("sync_started", {"adapter_name": name})
                self._sync_adapter(name, adapter, result)
                self._emit_event(
                    "sync_completed", {"adapter_name": name, "result": result}
                )
            except Exception as e:
                error_msg = f"{name}: {str(e)}"
                result.errors.append(error_msg)
                result.success = False
                self._emit_event(
                    "sync_error", {"adapter_name": name, "error": error_msg}
                )
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
        """Синхронизация одного адаптера с генерацией событий"""
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
                    self._emit_event("task_created", {"task": remote_task})
            else:
                # Возможен конфликт
                old_version = local_task.version
                resolved, conflicts = self.resolver.resolve(local_task, remote_task)

                if self.cache.save_task(resolved):
                    result.tasks_synced += 1

                    if resolved.version != old_version or len(conflicts) > 0:
                        # Задача действительно изменилась
                        self._emit_event(
                            "task_updated", {"task": resolved, "old_task": local_task}
                        )

    def _cleanup_deleted_tasks(self, adapter_name: str, remote_tasks: List[Task]):
        """Удаление задач, которых больше нет в источнике"""
        remote_ids = {t.external_id for t in remote_tasks}
        # Получаем все задачи этого адаптера из кэша
        all_cached = self.cache.get_all_tasks()

        for cached_task in all_cached:
            if cached_task.source_type.value == adapter_name.lower():
                if cached_task.external_id not in remote_ids:
                    self.cache.delete_task(cached_task.id)
                    self._emit_event(
                        "task_deleted",
                        {
                            "task_id": cached_task.id,
                            "external_id": cached_task.external_id,
                            "source_type": adapter_name,
                        },
                    )

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
