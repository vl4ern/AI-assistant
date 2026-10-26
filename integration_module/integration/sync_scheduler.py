import time
import threading
from typing import List, Dict, Optional, Callable
from integration.interfaces import IServiceAdapter, ICacheStorage
from integration.conflict_resolver import ConflictResolver
from integration.retry_queue import RetryQueue
from models.sync import SyncResult, ConflictNotification
from models.task import Task, utc_now, SourceType


class SyncEvent:
    def __init__(self, event_type: str, data: dict):
        self.type = event_type
        self.data = data
        self.timestamp = utc_now()


class SyncScheduler:
    def __init__(
        self, cache: ICacheStorage, resolver: ConflictResolver, retry_queue: RetryQueue
    ):
        self.cache = cache
        self.resolver = resolver
        self.retry_queue = retry_queue
        self.adapters: Dict[str, IServiceAdapter] = {}
        self.intervals: Dict[str, int] = {}
        self.last_sync_time: Dict[str, Optional[datetime]] = {}  # type: ignore

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

        self._running = False
        self._thread: Optional[threading.Thread] = None

    # --- подписки/события без изменений ---

    @staticmethod
    def _is_routine_due_date_shift(remote_task, conflicts) -> bool:
        """
        У IIS-задач due_date — «плавающая» дата ближайшего вхождения.
        Если единственное отличие — due_date, это не конфликт, а плановый пересчёт.
        """
        if remote_task.source_type != SourceType.IIS:
            return False
        if len(conflicts) != 1:
            return False
        fields = set(conflicts[0].conflicting_fields)
        return fields == {"due_date"}

    def subscribe(self, event_type: str, callback: Callable):
        if event_type in self._event_callbacks:
            self._event_callbacks[event_type].append(callback)
            print(f"[SyncScheduler] Подписка на '{event_type}' добавлена")
        else:
            raise ValueError(f"Неизвестный тип события: {event_type}")

    def unsubscribe(self, event_type: str, callback: Callable):
        if event_type in self._event_callbacks:
            self._event_callbacks[event_type].remove(callback)

    def _emit_event(self, event_type: str, data: dict):
        event = SyncEvent(event_type, data)
        with self._event_lock:
            self._event_queue.append(event)
        for callback in self._event_callbacks.get(event_type, []):
            try:
                callback(**data)
            except Exception as e:
                print(
                    f"[SyncScheduler] Ошибка в обработчике события '{event_type}': {e}"
                )

    # --- регистрация ---

    def register_adapter(
        self, name: str, adapter: IServiceAdapter, sync_interval: int = 3600
    ):
        self.adapters[name] = adapter
        self.intervals[name] = sync_interval
        self.last_sync_time[name] = None
        print(
            f"[SyncScheduler] Зарегистрирован адаптер '{name}' "
            f"(интервал: {sync_interval}с)"
        )

    # --- синхронизация ---

    def sync_all(self) -> SyncResult:
        total = SyncResult()
        for name, adapter in list(self.adapters.items()):
            try:
                self._emit_event("sync_started", {"adapter_name": name})
                adapter_result = SyncResult()
                self._sync_adapter(name, adapter, adapter_result)
                self.last_sync_time[name] = utc_now()

                # агрегация
                total.tasks_synced += adapter_result.tasks_synced
                total.conflicts_detected += adapter_result.conflicts_detected
                total.errors.extend(adapter_result.errors)
                if adapter_result.errors:
                    total.success = False

                self._emit_event(
                    "sync_completed",
                    {"adapter_name": name, "result": adapter_result},
                )
            except Exception as e:
                error_msg = f"{name}: {str(e)}"
                total.errors.append(error_msg)
                total.success = False
                self._emit_event(
                    "sync_error", {"adapter_name": name, "error": error_msg}
                )
                self.retry_queue.add_sync_retry(name, error_msg)
        return total

    def sync_adapter_now(self, name: str) -> Optional[SyncResult]:
        adapter = self.adapters.get(name)
        if not adapter:
            return None
        result = SyncResult()
        try:
            self._sync_adapter(name, adapter, result)
            self.last_sync_time[name] = utc_now()
        except Exception as e:
            result.errors.append(f"{name}: {str(e)}")
            result.success = False
        return result

    def _sync_adapter(self, name: str, adapter: IServiceAdapter, result: SyncResult):
        since = self.last_sync_time.get(name)

        remote_tasks = adapter.fetch_changes(since)

        for remote_task in remote_tasks:
            local_task = self.cache.get_task_by_external_id(
                remote_task.external_id, remote_task.source_type.value
            )

            if local_task is None:
                if self.cache.save_task(remote_task):
                    result.tasks_synced += 1
                    self._emit_event("task_created", {"task": remote_task})
                continue

            old_version = local_task.version
            resolved, conflicts = self.resolver.resolve(local_task, remote_task)
            resolved.id = local_task.id

            if conflicts and self._is_routine_due_date_shift(remote_task, conflicts):
                conflicts = []

            if self.cache.save_task(resolved):
                result.tasks_synced += 1
                if conflicts:
                    result.conflicts_detected += len(conflicts)
                    for c in conflicts:
                        self._emit_event("conflict_detected", {"conflict": c})
                if resolved.version != old_version or conflicts:
                    self._emit_event(
                        "task_updated", {"task": resolved, "old_task": local_task}
                    )

        self._cleanup_deleted_tasks(name, remote_tasks)

    def _cleanup_deleted_tasks(self, adapter_name: str, remote_tasks: List[Task]):
        """Удаляет из кэша задачи, которых больше нет в источнике."""
        if not remote_tasks:
            return  # не знаем, какой source_type — не рискуем

        source_type = remote_tasks[0].source_type
        remote_ids = {t.external_id for t in remote_tasks}

        for cached in self.cache.get_all_tasks():
            if cached.source_type != source_type:
                continue
            if cached.external_id in remote_ids:
                continue
            self.cache.delete_task(cached.id)
            self._emit_event(
                "task_deleted",
                {
                    "task_id": cached.id,
                    "external_id": cached.external_id,
                    "source_type": adapter_name,
                },
            )

    # --- фоновый режим ---

    def start_background(self, check_interval: int = 10):
        if self._running:
            print("[SyncScheduler] Фоновый режим уже запущен")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._background_worker, args=(check_interval,), daemon=True
        )
        self._thread.start()
        print(
            f"[SyncScheduler] Запущен фоновый режим "
            f"(проверка каждые {check_interval}с)"
        )

    def stop_background(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            print("[SyncScheduler] Фоновый режим остановлен")

    def _background_worker(self, check_interval: int):
        while self._running:
            now = utc_now()
            for name, adapter in list(self.adapters.items()):
                last_sync = self.last_sync_time.get(name)
                interval = self.intervals.get(name, 3600)

                due = last_sync is None or (now - last_sync).total_seconds() >= interval
                if not due:
                    continue

                print(f"[SyncScheduler] Запуск плановой синхронизации '{name}'")
                try:
                    result = self.sync_adapter_now(name)
                    if result and result.errors:
                        print(f"[SyncScheduler] Ошибки '{name}': {result.errors}")
                except Exception as e:
                    print(f"[SyncScheduler] Ошибка синхронизации '{name}': {e}")
                    self.retry_queue.add_sync_retry(name, str(e))

            self.retry_queue.process(self.cache, self.adapters)
            time.sleep(check_interval)
