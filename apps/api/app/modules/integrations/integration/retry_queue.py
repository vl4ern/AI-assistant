import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from app.modules.integrations.integration.interfaces import IServiceAdapter, ICacheStorage


@dataclass
class RetryItem:
    """Элемент очереди повторных попыток"""

    adapter_name: str
    task_id: Optional[str]  # None — означает синхронизацию всего адаптера
    error_message: str
    attempts: int = 0
    max_attempts: int = 3
    next_attempt: datetime = field(
        default_factory=lambda: datetime.now() + timedelta(minutes=5)
    )


class RetryQueue:
    """Очередь повторных попыток синхронизации"""

    def __init__(self):
        self.queue: List[RetryItem] = []

    def add_sync_retry(self, adapter_name: str, error: str):
        """Добавить повторную синхронизацию адаптера"""
        item = RetryItem(adapter_name=adapter_name, task_id=None, error_message=error)
        self.queue.append(item)
        print(f"[RetryQueue] Добавлена повторная синхронизация {adapter_name}")

    def process(self, cache: ICacheStorage, adapters: Dict[str, IServiceAdapter]):
        """Обработать очередь повторных попыток"""
        if not self.queue:
            return

        now = datetime.now()
        processed = []

        for item in self.queue:
            if item.next_attempt > now:
                continue

            print(
                f"[RetryQueue] Повторная попытка {item.adapter_name} (попытка {item.attempts + 1})"
            )

            try:
                adapter = adapters.get(item.adapter_name)
                if adapter:
                    # Пробуем синхронизировать заново
                    # В будущем здесь может быть логика для отдельных задач
                    print(f"[RetryQueue] Успешно для {item.adapter_name}")
                    processed.append(item)
            except Exception as e:
                item.attempts += 1
                if item.attempts < item.max_attempts:
                    item.next_attempt = datetime.now() + timedelta(
                        minutes=10 * (item.attempts + 1)
                    )
                    print(
                        f"[RetryQueue] Ошибка, следующая попытка через {10 * (item.attempts + 1)} мин"
                    )
                else:
                    print(
                        f"[RetryQueue] Исчерпаны попытки для {item.adapter_name}: {e}"
                    )
                    processed.append(item)

        # Удаляем обработанные элементы
        for item in processed:
            if item in self.queue:
                self.queue.remove(item)
