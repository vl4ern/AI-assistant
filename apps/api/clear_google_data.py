"""Однократная полная чистка всех данных, пришедших из Google Calendar.

Локально:
    PYTHONPATH=apps/api .venv/bin/python apps/api/clear_google_data.py

В Docker (скрипт смонтирован в /app через ./apps/api:/app):
    docker compose exec api python clear_google_data.py

Удаляет:
  - события базы знаний с source='google-calendar' (Postgres);
  - задачи кэша синхронизации с source_type='google_calendar' (SQLite);
  - привязки экспорта google_export:*.
"""

from app.core.settings import settings
from app.modules.integrations.integration.cache_storage import SQLiteCacheStorage
from app.modules.knowledge.service import KnowledgeService


def open_repository():
    """Вернуть (repository, описание) — Postgres если доступен, иначе in-memory."""
    try:
        from app.modules.knowledge.postgres_repository import (
            PostgresKnowledgeRepository,
        )

        repository = PostgresKnowledgeRepository(
            settings.database_url, auto_init_schema=False
        )
        with repository._connect() as conn:
            conn.execute("SELECT 1")
        return repository, "PostgreSQL"
    except Exception as exc:  # noqa: BLE001 — локально без базы работает in-memory
        from app.modules.knowledge.in_memory_repository import (
            InMemoryKnowledgeRepository,
        )

        return InMemoryKnowledgeRepository(), f"in-memory ({exc})"


repository, storage_kind = open_repository()
kb = KnowledgeService(repository)

events = kb.delete_events_by_source("google-calendar")

try:
    cache = SQLiteCacheStorage(settings.integration_cache_path)
    tasks = cache.delete_tasks_by_source("google_calendar")
    links = cache.list_settings("google_export:")
    for key in links:
        cache.delete_setting(key)
    print(f"Кэш: {settings.integration_cache_path}")
except Exception as exc:  # noqa: BLE001 — файл может быть root-owned после Docker
    tasks = 0
    links = []
    print(f"Не удалось почистить SQLite-кэш: {exc}")

print(f"Хранилище событий: {storage_kind}")
print(f"Удалено событий Google из базы знаний: {events}")
print(f"Удалено задач Google из кэша: {tasks}")
print(f"Удалено привязок экспорта: {len(links)}")
