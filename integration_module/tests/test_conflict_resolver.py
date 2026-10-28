import pytest
from datetime import datetime, timezone
from integration.conflict_resolver import ConflictResolver
from models.task import Task, SourceType, TaskStatus


@pytest.fixture
def resolver():
    return ConflictResolver(cache_storage=None)  # cache здесь не нужен


@pytest.fixture
def base_task():
    return Task(
        id="1",
        external_id="ext1",
        source_type=SourceType.IIS,
        title="ООП",
        description="Аудитория: 111",
        due_date=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
        version=1,
    )


def test_conflict_resolver_equal_versions(resolver, base_task):
    """Тест: если версии равны, но поля разные — изменения должны примениться."""
    remote_task = Task(
        id="1",  # ID тот же
        external_id="ext1",
        source_type=SourceType.IIS,
        title="ООП (изменено)",  # Изменилось
        description="Аудитория: 222",  # Изменилось
        due_date=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
        version=1,  # Версия осталась 1
    )

    resolved, conflicts = resolver.resolve(base_task, remote_task)

    # Поля должны обновиться
    assert resolved.title == "ООП (изменено)"
    assert resolved.description == "Аудитория: 222"
    # Должен зафиксироваться конфликт (т.к. strategy=MERGE_WITH_NOTIFY по умолчанию)
    assert len(conflicts) == 1
    # Версия должна инкрементироваться
    assert resolved.version == 2
