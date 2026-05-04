import time
import signal
import sys
import threading
from integration.cache_storage import SQLiteCacheStorage
from integration.conflict_resolver import ConflictResolver
from integration.sync_scheduler import SyncScheduler
from integration.retry_queue import RetryQueue
from integration.adapters.iis_adapter import IisAdapter
from integration.adapters.google_calendar_adapter import GoogleCalendarAdapter
from integration.api import start_api_server


def main():
    print("=" * 50)
    print("Модуль интеграции с внешними сервисами")
    print("=" * 50)

    # Инициализация компонентов
    cache = SQLiteCacheStorage("schedule_cache.db")
    resolver = ConflictResolver(cache)
    retry_queue = RetryQueue()
    scheduler = SyncScheduler(cache, resolver, retry_queue)

    # Регистрируем адаптер IIS (расписание БГУИР) - каждые 2 часа
    iis_adapter = IisAdapter(group_number="421701")
    scheduler.register_adapter("IIS", iis_adapter, sync_interval=7200)
    print("[Main] Адаптер IIS зарегистрирован")

    # Регистрируем адаптер Google Calendar - каждые 15 минут
    try:
        gc_adapter = GoogleCalendarAdapter(
            credentials_file="credentials.json", token_file="google_token.pickle"
        )
        if gc_adapter.authenticate():
            scheduler.register_adapter("GoogleCalendar", gc_adapter, sync_interval=900)
            print("[Main] Адаптер Google Calendar зарегистрирован")
        else:
            print("[Main] Ошибка аутентификации Google Calendar")
    except Exception as e:
        print(f"[Main] Google Calendar не настроен: {e}")
        print("[Main] Для использования Google Calendar:")
        print("  1. Создайте проект в Google Cloud Console")
        print("  2. Скачайте credentials.json в папку с программой")
        print("  3. Перезапустите программу")

    # Graceful shutdown
    def signal_handler(sig, frame):
        print("\n[Main] Завершение работы...")
        scheduler.stop_background()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Первичная синхронизация
    print("\n[Main] Первичная синхронизация...")
    result = scheduler.sync_all()
    print(f"[Main] Синхронизировано задач: {result.tasks_synced}")
    print(f"[Main] Конфликтов: {result.conflicts_detected}")

    if result.errors:
        print(f"[Main] Ошибки: {result.errors}")

    # HTTP API для внешнего управления
    api_thread = threading.Thread(
        target=start_api_server, args=(scheduler, 8090), daemon=True
    )
    api_thread.start()

    # Фоновый режим
    print("\n[Main] Запуск фонового обновления...")
    scheduler.start_background(check_interval=30)

    print("[Main] Модуль работает в фоновом режиме")
    print("[Main] API доступно на http://localhost:8090")
    print("[Main] Ctrl+C для выхода\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Main] Завершение работы...")
        scheduler.stop_background()


if __name__ == "__main__":
    main()
