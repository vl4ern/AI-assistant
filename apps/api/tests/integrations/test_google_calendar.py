from datetime import datetime
from pathlib import Path

from app.modules.integrations.integration.adapters.google_calendar_adapter import (
    GoogleCalendarAdapter,
)
from app.modules.integrations.models.google_models import GoogleCalendarEvent
from app.modules.integrations.models.task import SourceType, Task, TaskStatus
from app.modules.integrations.service import IntegrationService
from app.modules.intelligence.models import ScheduledSlot
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService


def test_timed_event_converted_to_local_naive() -> None:
    task = GoogleCalendarEvent.from_google_event(
        {
            "id": "ev1",
            "summary": "Созвон",
            "start": {"dateTime": "2026-11-10T06:00:00Z"},
            "end": {"dateTime": "2026-11-10T07:30:00Z"},
        }
    )

    assert task is not None
    assert task.source_type == SourceType.GOOGLE_CALENDAR
    assert task.due_date is not None and task.due_date.tzinfo is None
    assert task.due_date == datetime(2026, 11, 10, 9, 0)  # Europe/Minsk, UTC+3
    assert task.duration_minutes == 90


def test_all_day_event() -> None:
    task = GoogleCalendarEvent.from_google_event(
        {"id": "ev2", "summary": "Дедлайн", "start": {"date": "2026-11-12"}, "end": {"date": "2026-11-13"}}
    )

    assert task is not None
    assert task.due_date == datetime(2026, 11, 12)
    assert task.duration_minutes == 24 * 60


def test_events_created_by_assistant_are_skipped() -> None:
    task = GoogleCalendarEvent.from_google_event(
        {
            "id": "ev3",
            "summary": "Лаба",
            "start": {"dateTime": "2026-11-10T06:00:00Z"},
            "end": {"dateTime": "2026-11-10T07:00:00Z"},
            "extendedProperties": {"private": {"ai_assistant": "1"}},
        }
    )

    assert task is None


def test_cancelled_event_is_archived() -> None:
    task = GoogleCalendarEvent.from_google_event({"id": "ev4", "status": "cancelled"})

    assert task is not None
    assert task.status == TaskStatus.ARCHIVED


class _FakeEvents:
    def __init__(self, calls: list) -> None:
        self.calls = calls

    def insert(self, calendarId, body):  # noqa: N803
        self.calls.append(("insert", body))
        return _Exec({"id": "evt-1"})

    def update(self, calendarId, eventId, body):  # noqa: N803
        self.calls.append(("update", eventId, body))
        return _Exec({"id": eventId})


class _Exec:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def execute(self) -> dict:
        return self.payload


class _FakeService:
    def __init__(self) -> None:
        self.calls: list = []

    def events(self) -> _FakeEvents:
        return _FakeEvents(self.calls)


def _adapter_with_fake_service() -> tuple[GoogleCalendarAdapter, _FakeService]:
    adapter = GoogleCalendarAdapter(credentials_file="x.json", token_file="x.pickle")
    service = _FakeService()
    adapter.service = service
    return adapter, service


def test_push_update_creates_marked_event_with_duration() -> None:
    adapter, service = _adapter_with_fake_service()
    task = Task(
        id="t1",
        external_id="",
        source_type=SourceType.MANUAL,
        title="Лаба по ООП",
        due_date=datetime(2026, 11, 10, 10, 0),
        duration_minutes=90,
    )

    assert adapter.push_update(task) is True

    action, body = service.calls[0]
    assert action == "insert"
    assert body["start"]["dateTime"] == "2026-11-10T10:00:00"
    assert body["end"]["dateTime"] == "2026-11-10T11:30:00"
    assert body["extendedProperties"]["private"]["ai_assistant"] == "1"
    assert task.external_id == "evt-1"


def test_authenticate_non_interactive_without_token_returns_false(tmp_path: Path) -> None:
    adapter = GoogleCalendarAdapter(
        credentials_file=str(tmp_path / "credentials.json"),
        token_file=str(tmp_path / "missing.pickle"),
    )

    assert adapter.authenticate(interactive=False) is False
    assert adapter.is_authenticated is False


def test_export_updates_existing_event_instead_of_duplicating(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    integration = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )
    adapter, fake = _adapter_with_fake_service()
    integration._google_adapter = adapter

    slot = ScheduledSlot(
        task_id="task-1",
        title="Подготовка к тесту",
        start_at=datetime(2026, 11, 10, 7, 0),
        end_at=datetime(2026, 11, 10, 8, 0),
        score=1.0,
    )

    first = integration.export_slots_to_google([slot])
    second = integration.export_slots_to_google([slot])

    assert first.exported == 1 and second.exported == 1
    assert [call[0] for call in fake.calls] == ["insert", "update"]
    assert fake.calls[1][1] == "evt-1"


def test_google_status_not_configured(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    integration = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )

    status = integration.google_status()

    assert status.configured is False
    assert status.connected is False
