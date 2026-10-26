from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from integration.interfaces import IServiceAdapter, ICacheStorage


@dataclass
class RetryItem:
    adapter_name: str
    task_id: Optional[str]
    error_message: str
    attempts: int = 0
    max_attempts: int = 3
    next_attempt: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=5)
    )


class RetryQueue:
    """Очередь повторных попыток синхронизации."""

    def __init__(self):
        self.queue: List[RetryItem] = []
        # Колбэк, который ставит scheduler. Позволяет избежать циклической
        # зависимости RetryQueue -> SyncScheduler.
        self._sync_callback: Optional[Callable[[str], bool]] = None

    def set_sync_callback(self, callback: Callable[[str], bool]):
        """Scheduler регистрирует здесь свой метод sync_adapter_now."""
        self._sync_callback = callback

    def add_sync_retry(self, adapter_name: str, error: str):
        # Не плодим дубликаты для одного адаптера.
        for item in self.queue:
            if item.adapter_name == adapter_name and item.task_id is None:
                item.error_message = error
                return
        self.queue.append(
            RetryItem(
                adapter_name=adapter_name,
                task_id=None,
                error_message=error,
            )
        )
        print(f"[RetryQueue] Добавлена повторная синхронизация {adapter_name}")

    def process(self, cache: ICacheStorage, adapters: Dict[str, IServiceAdapter]):
        if not self.queue:
            return

        now = datetime.now(timezone.utc)
        done: List[RetryItem] = []

        for item in list(self.queue):
            if item.next_attempt > now:
                continue

            if item.adapter_name not in adapters:
                # Адаптер удалён — выкидываем задачу.
                done.append(item)
                continue

            if self._sync_callback is None:
                # Некуда звать — ждём следующего цикла.
                continue

            print(
                f"[RetryQueue] Повторная попытка {item.adapter_name} "
                f"(попытка {item.attempts + 1})"
            )

            try:
                success = self._sync_callback(item.adapter_name)
            except Exception as e:
                success = False
                print(f"[RetryQueue] Исключение при retry: {e}")

            if success:
                print(f"[RetryQueue] Успешно для {item.adapter_name}")
                done.append(item)
            else:
                item.attempts += 1
                if item.attempts >= item.max_attempts:
                    print(
                        f"[RetryQueue] Исчерпаны попытки для "
                        f"{item.adapter_name}: {item.error_message}"
                    )
                    done.append(item)
                else:
                    backoff_min = 10 * (item.attempts + 1)
                    item.next_attempt = now + timedelta(minutes=backoff_min)
                    print(f"[RetryQueue] Следующая попытка через {backoff_min} мин")

        for item in done:
            if item in self.queue:
                self.queue.remove(item)
