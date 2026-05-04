import time
import signal
import sys
import threading
from app.modules.integrations.integration.cache_storage import SQLiteCacheStorage
from app.modules.integrations.integration.conflict_resolver import ConflictResolver
from app.modules.integrations.integration.sync_scheduler import SyncScheduler
from app.modules.integrations.integration.retry_queue import RetryQueue
from app.modules.integrations.integration.adapters.iis_adapter import IisAdapter
from app.modules.integrations.integration.api import start_api_server


def main():
    print("=" * 50)
    print("Модуль интеграции с расписанием БГУИР")
    print("=" * 50)

    # Инициализация компонентов
    cache = SQLiteCacheStorage("iis_cache.db")
    resolver = ConflictResolver(cache)
    retry_queue = RetryQueue()
    scheduler = SyncScheduler(cache, resolver, retry_queue)

    api_thread = threading.Thread(
        target=start_api_server, args=(scheduler, 8090), daemon=True
    )
    api_thread.start()

    # Регистрируем адаптер IIS с интервалом обновления 2 часа (7200 секунд)
    iis_adapter = IisAdapter(group_number="421701")
    scheduler.register_adapter("IIS", iis_adapter, sync_interval=7200)  # Каждые 2 часа

    # Обработчик для graceful shutdown
    def signal_handler(sig, frame):
        print("\n[Main] Завершение работы...")
        scheduler.stop_background()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Первый запуск — немедленная синхронизация
    print("[Main] Первичная синхронизация...")
    result = scheduler.sync_all()
    print(f"[Main] Синхронизировано задач: {result.tasks_synced}")
    print(f"[Main] Конфликтов: {result.conflicts_detected}")

    if result.errors:
        print(f"[Main] Ошибки: {result.errors}")

    # Запускаем фоновый режим
    print("\n[Main] Запуск фонового обновления...")
    scheduler.start_background(check_interval=30)  # Проверка каждые 30 секунд

    print("[Main] Модуль работает в фоновом режиме (Ctrl+C для выхода)")
    print("[Main] Следующее обновление через 2 часа\n")

    try:
        # Держим основной поток живым
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Main] Завершение работы...")
        scheduler.stop_background()


if __name__ == "__main__":
    main()
