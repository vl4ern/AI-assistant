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
from models.task import SourceType
from integration.config_store import ConfigStore
import os

def main():
    print("=" * 50)
    print("Модуль интеграции с внешними сервисами")
    print("=" * 50)

    # Инициализация компонентов
    config = ConfigStore("config.json")
    group = os.environ.get("IIS_GROUP") or config.get("iis_group") or "421701"
    cache = SQLiteCacheStorage("schedule_cache.db")
    resolver = ConflictResolver(cache)
    retry_queue = RetryQueue()
    # --- после создания scheduler ---
    scheduler = SyncScheduler(cache, resolver, retry_queue)
    retry_queue.set_sync_callback(
        lambda name: scheduler.sync_adapter_now(name) is not None
    )
    def on_group_change(old_group: str, new_group: str):
        config.set("iis_group", new_group)

    # Регистрируем адаптер IIS (расписание БГУИР) - каждые 2 часа
    iis_adapter = IisAdapter(group_number=group, on_group_change=on_group_change)
    scheduler.register_adapter(SourceType.IIS.value, iis_adapter, sync_interval=120)
    print("[Main] Адаптер IIS зарегистрирован")

    # Регистрируем адаптер Google Calendar - каждые 15 минут
    try:
        gc_adapter = GoogleCalendarAdapter(
            credentials_file="credentials.json", token_file="google_token.pickle"
        )
        if gc_adapter.authenticate():
            scheduler.register_adapter(
                SourceType.GOOGLE_CALENDAR.value, gc_adapter, sync_interval=30
            )
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
        if scheduler._running:
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
