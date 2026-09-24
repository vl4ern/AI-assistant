from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.modules.integrations.integration.interfaces import IServiceAdapter
from app.modules.integrations.models.sync import SyncResult
from app.modules.integrations.models.task import SourceType, Task, TaskStatus
from app.modules.integrations.service import IntegrationService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService


class FakeAdapter(IServiceAdapter):
    """Адаптер с предзаданным списком задач для тестов."""

    def __init__(self, tasks: list[Task]) -> None:
        self.tasks = tasks
        self.fetch_calls = 0

    def authenticate(self, token: str | None = None) -> bool:
        return True

    def fetch_changes(self, since: datetime | None = None) -> list[Task]:
        self.fetch_calls += 1
        return self.tasks

    def push_update(self, task: Task) -> bool:
        return True

    def delete_task(self, external_id: str) -> bool:
        return True


def make_lesson() -> Task:
    start = datetime.now().replace(microsecond=0) + timedelta(days=1)
    return Task(
        id="lesson-1",
        external_id="iis-abc123",
        source_type=SourceType.IIS,
        title="ООП",
        description="Тип: ЛК\nАудитория: 123-1\nПреподаватель: Иванов И. И.",
        due_date=start,
        duration_minutes=90,
    )


def make_external_todo() -> Task:
    return Task(
        id="todo-1",
        external_id="cal-xyz-1",
        source_type=SourceType.MANUAL,
        title="Сдать отчёт",
        description="Из внешнего календаря",
        due_date=datetime.now() + timedelta(days=2),
        duration_minutes=60,
        priority=2,
    )


def build_service(tmp_path: Path, tasks: list[Task]) -> tuple[IntegrationService, KnowledgeService, FakeAdapter]:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
    )
    adapter = FakeAdapter(tasks)
    service._scheduler.register_adapter("Fake", adapter, sync_interval=3600)
    return service, kb, adapter


def test_sync_creates_events_and_tasks_in_knowledge_base(tmp_path: Path) -> None:
    service, kb, adapter = build_service(tmp_path, [make_lesson(), make_external_todo()])

    result = service.sync_all()

    assert result.provider == "all"
    assert result.synced_items == 2
    assert result.status == "ok"

    events = kb.list_events()
    assert len(events) == 1
    assert events[0].title == "ООП"
    assert events[0].source == "bsuir-lms"
    assert events[0].end_at > events[0].start_at

    tasks = kb.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].title == "Сдать отчёт"


def test_repeated_sync_does_not_duplicate_knowledge_facts(tmp_path: Path) -> None:
    service, kb, adapter = build_service(tmp_path, [make_lesson(), make_external_todo()])

    service.sync_all()
    service.sync_all()

    assert len(kb.list_events()) == 1
    assert len(kb.list_tasks()) == 1


def test_sync_all_adapter_error_is_reported(tmp_path: Path) -> None:
    class BrokenAdapter(FakeAdapter):
        def fetch_changes(self, since=None):
            raise RuntimeError("IIS недоступен")

    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
    )
    service._scheduler.register_adapter("Broken", BrokenAdapter([]), sync_interval=3600)

    result = service.sync_all()

    assert result.status == "error"
    assert any("Broken" in error for error in result.errors)


def test_sync_unknown_adapter_raises(tmp_path: Path) -> None:
    service, _, _ = build_service(tmp_path, [])

    with pytest.raises(ValueError):
        service.sync_adapter("nonexistent")


def test_list_adapters_reports_status(tmp_path: Path) -> None:
    service, _, adapter = build_service(tmp_path, [])

    adapters = service.list_adapters()
    assert len(adapters) == 1
    assert adapters[0].name == "Fake"
    assert adapters[0].last_sync_at is None

    service.sync_all()

    adapters = service.list_adapters()
    assert adapters[0].last_sync_at is not None


def test_updated_external_task_propagates_to_knowledge_base(tmp_path: Path) -> None:
    service, kb, adapter = build_service(tmp_path, [make_lesson()])

    service.sync_all()

    # Внешний источник изменил название занятия (версия увеличилась)
    changed = make_lesson()
    changed.version = 2
    changed.title = "ООП (обновлено)"
    adapter.tasks = [changed]

    service.sync_all()

    # Новое занятие создаётся как новое событие, старое остаётся фактом
    titles = {event.title for event in kb.list_events()}
    assert "ООП (обновлено)" in titles


def test_service_without_adapters_works(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )

    result = service.sync_all()

    assert result.synced_items == 0
    assert result.status == "ok"
    assert service.list_adapters() == []
