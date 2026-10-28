import pytest
from integration.cache_storage import SQLiteCacheStorage
from models.task import Task, SourceType
from datetime import datetime, timezone


@pytest.fixture
def cache(tmp_path):
    # Используем временную папку для тестовой БД
    db_file = tmp_path / "test_cache.db"
    return SQLiteCacheStorage(str(db_file))


def test_save_and_get_task(cache):
    task = Task(
        id="test_1",
        external_id="ext_1",
        source_type=SourceType.IIS,
        title="Тестовая задача",
        due_date=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
    )

    assert cache.save_task(task) is True

    loaded = cache.get_task("test_1")
    assert loaded is not None
    assert loaded.title == "Тестовая задача"
    assert loaded.due_date.tzinfo is not None  # Проверка, что TZ сохранился

    loaded_by_ext = cache.get_task_by_external_id("ext_1", "IIS")
    assert loaded_by_ext.id == "test_1"
