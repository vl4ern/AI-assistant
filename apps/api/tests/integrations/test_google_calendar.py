import json
import pickle
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from google.oauth2.credentials import Credentials

from app.modules.integrations.integration.adapters.google_calendar_adapter import (
    GoogleCalendarAdapter,
    _OAuthCallbackApp,
)
from app.modules.integrations.models.google_models import GoogleCalendarEvent
from app.modules.integrations.models.task import SourceType, Task
from app.modules.integrations.service import IntegrationService
from app.modules.intelligence.models import ScheduledSlot
from app.modules.knowledge.models import EventCreate
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


def test_cancelled_event_is_skipped() -> None:
    # Отменённые события не должны становиться занятыми интервалами.
    task = GoogleCalendarEvent.from_google_event({"id": "ev4", "status": "cancelled"})

    assert task is None


def test_events_exported_by_assistant_are_skipped_even_without_marker() -> None:
    task = GoogleCalendarEvent.from_google_event(
        {
            "id": "ev5",
            "summary": "Подготовка к зачёту",
            "description": "Запланировано в AI-assistant",
            "start": {"dateTime": "2026-11-10T06:00:00Z"},
        }
    )

    assert task is None


class _FakeEvents:
    def __init__(self, calls: list) -> None:
        self.calls = calls

    def list(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(("list", kwargs))
        return _Exec({"items": [{"id": "exported-1"}, {"id": "exported-2"}]})

    def delete(self, calendarId, eventId):  # noqa: N803
        self.calls.append(("delete", eventId))
        return _Exec({})

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


def test_delete_exported_events_removes_app_copies_from_google() -> None:
    adapter, service = _adapter_with_fake_service()

    deleted = adapter.delete_exported_events()

    assert deleted == 2
    list_call = [call for call in service.calls if call[0] == "list"][0]
    assert list_call[1]["privateExtendedProperty"] == "ai_assistant=1"
    assert [call[1] for call in service.calls if call[0] == "delete"] == [
        "exported-1",
        "exported-2",
    ]


def test_authenticate_non_interactive_without_token_returns_false(tmp_path: Path) -> None:
    adapter = GoogleCalendarAdapter(
        credentials_file=str(tmp_path / "credentials.json"),
        token_file=str(tmp_path / "missing.pickle"),
    )

    assert adapter.authenticate(interactive=False) is False
    assert adapter.is_authenticated is False


def _callback_environ(query: str) -> dict:
    return {
        "REQUEST_METHOD": "GET",
        "wsgi.url_scheme": "http",
        "HTTP_HOST": "localhost",
        "PATH_INFO": "/",
        "QUERY_STRING": query,
    }


def _callback_start_response(status: str, headers: list) -> None:
    return None


def _run_callback(app: _OAuthCallbackApp, query: str) -> bytes:
    body = app(environ=_callback_environ(query), start_response=_callback_start_response)
    return b"".join(body)


def test_oauth_callback_accepts_matching_state_and_code() -> None:
    app = _OAuthCallbackApp(flow=object(), state="state-123")

    assert _run_callback(app, "code=abc&state=state-123") == b"ok"
    assert app.uri == "http://localhost/?code=abc&state=state-123"
    assert app.error is None


def test_oauth_callback_rejects_mismatching_state() -> None:
    app = _OAuthCallbackApp(flow=object(), state="state-123")

    assert _run_callback(app, "code=abc&state=evil") == b"invalid_request"
    assert app.error == "invalid_request"
    assert app.uri is None


def test_oauth_callback_rejects_oauth_error_param() -> None:
    app = _OAuthCallbackApp(flow=object(), state="state-123")

    assert _run_callback(app, "error=access_denied") == b"error=oauth_error:access_denied"
    assert app.error is not None
    assert app.uri is None


def test_oauth_callback_second_request_is_rejected() -> None:
    app = _OAuthCallbackApp(flow=object(), state="state-123")

    assert _run_callback(app, "code=abc&state=state-123") == b"ok"
    assert _run_callback(app, "code=abc&state=state-123") == b"bad_request"
    assert app.uri == "http://localhost/?code=abc&state=state-123"


def test_local_callback_server_releases_port_after_timeout() -> None:
    adapter = GoogleCalendarAdapter(
        credentials_file="/nonexistent/credentials.json",
        token_file="/tmp/nonexistent-token.pickle",
    )

    with pytest.raises(TimeoutError):
        adapter._run_local_callback_server(
            flow=object(),
            state="state-123",
            port=0,
            timeout_seconds=1.0,
        )


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


def _write_credentials_file(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client.apps.googleusercontent.com",
                    "client_secret": "secret",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )


def test_legacy_oauth2token_dict_is_converted_to_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Токен из старого бага (OAuth2Token вместо Credentials) должен работать."""
    credentials_file = tmp_path / "credentials.json"
    token_file = tmp_path / "token.pickle"
    _write_credentials_file(credentials_file)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
    with token_file.open("wb") as f:
        pickle.dump(
            {
                "access_token": "token",
                "refresh_token": "refresh",
                "scope": ["https://www.googleapis.com/auth/calendar.events"],
                "expires_at": expires_at,
            },
            f,
        )

    from app.modules.integrations.integration.adapters import (
        google_calendar_adapter as module,
    )

    monkeypatch.setattr(module, "build", lambda *a, **kw: "service")
    adapter = GoogleCalendarAdapter(
        credentials_file=str(credentials_file), token_file=str(token_file)
    )

    assert adapter.authenticate(interactive=False) is True
    assert adapter.is_authenticated is True
    with token_file.open("rb") as f:
        assert isinstance(pickle.load(f), Credentials)


def test_expired_legacy_token_without_refresh_is_rejected(tmp_path: Path) -> None:
    credentials_file = tmp_path / "credentials.json"
    token_file = tmp_path / "token.pickle"
    _write_credentials_file(credentials_file)
    with token_file.open("wb") as f:
        pickle.dump({"scope": ["https://www.googleapis.com/auth/calendar.events"]}, f)

    adapter = GoogleCalendarAdapter(
        credentials_file=str(credentials_file), token_file=str(token_file)
    )

    assert adapter.authenticate(interactive=False) is False
    assert adapter.is_authenticated is False
    assert adapter.last_auth_error


class _ListRequest:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs

    def execute(self) -> dict:
        return {"items": []}


class _ListEvents:
    def list(self, **kwargs):  # noqa: ANN003, ANN201
        return _ListRequest(kwargs)


class _ListService:
    def events(self) -> _ListEvents:
        return _ListEvents()


def test_fetch_changes_treats_datetime_min_as_no_since() -> None:
    adapter, _ = _adapter_with_fake_service()
    adapter.service = _ListService()

    # SyncScheduler использует datetime.min как «ещё не синхронизировали».
    # Раньше это падало ValueError: year must be in 1..9999.
    assert adapter.fetch_changes(since=datetime.min) == []


def test_oauth_callback_ignores_unrelated_get() -> None:
    app = _OAuthCallbackApp(flow=object(), state="state-123")

    assert _run_callback(app, "") == b"bad_request"
    assert app.done is False
    assert app.error is None

    # Настоящий callback после постороннего запроса всё ещё принимается.
    assert _run_callback(app, "code=abc&state=state-123") == b"ok"
    assert app.uri is not None


def test_startup_removes_all_legacy_google_events(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    kb.create_event(
        EventCreate(
            title="Старое событие Google",
            start_at=datetime(2026, 11, 29, 10, 0),
            end_at=datetime(2026, 11, 29, 11, 0),
            source="google-calendar",
            user_id="shared",
        )
    )
    kb.create_event(
        EventCreate(
            title="Пара",
            start_at=datetime(2026, 11, 29, 12, 0),
            end_at=datetime(2026, 11, 29, 13, 0),
            source="bsuir-lms",
        )
    )

    IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )

    assert [event.title for event in kb.list_events()] == ["Пара"]


def test_google_import_creates_events_only_for_the_owner(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    integration = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )

    class _GoogleAdapter:
        def fetch_changes(self, since=None):
            return [
                Task(
                    id="gc_1",
                    external_id="ev-1",
                    source_type=SourceType.GOOGLE_CALENDAR,
                    title="Моё событие",
                    due_date=datetime(2026, 11, 29, 13, 0),
                    duration_minutes=60,
                )
            ]

    integration._scheduler.register_adapter("GoogleCalendar", _GoogleAdapter(), 0)

    result = integration.sync_adapter("GoogleCalendar", user_id="user-1")

    assert result.synced_items == 1
    own = kb.list_events("user-1")
    assert [event.title for event in own] == ["Моё событие"]
    assert all(event.user_id == "user-1" for event in own)
    assert kb.list_events("user-2") == []
    assert kb.list_events("shared") == []


def test_google_import_requires_authenticated_user(tmp_path: Path) -> None:
    integration = IntegrationService(
        knowledge_service=KnowledgeService(repository=InMemoryKnowledgeRepository()),
        cache_path=str(tmp_path / "cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )

    with pytest.raises(ValueError):
        integration.sync_adapter("GoogleCalendar")


def test_kb_deduplication_key_is_stable_for_naive_and_aware_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.integrations.integration.kb_bridge import _normalize_key_datetime

    monkeypatch.setenv("GOOGLE_TIMEZONE", "Europe/Minsk")
    naive_local = datetime(2026, 11, 29, 13, 0)  # из адаптера Google
    aware_utc = datetime(2026, 11, 29, 10, 0, tzinfo=timezone.utc)  # из БД

    assert _normalize_key_datetime(naive_local) == _normalize_key_datetime(aware_utc)


def test_disconnect_google_clears_token_adapter_and_export_links(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    token_file = tmp_path / "token.pickle"
    token_file.write_bytes(b"token")
    integration = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )
    adapter = GoogleCalendarAdapter(
        credentials_file=str(tmp_path / "credentials.json"),
        token_file=str(token_file),
    )
    adapter.service = "fake"
    adapter.last_auth_url = "https://accounts.google.com/old"
    integration._google_adapter = adapter
    integration._scheduler.register_adapter("GoogleCalendar", adapter, 900)
    integration._scheduler.cache.set_setting("google_export:t1", "evt-1")

    status = integration.disconnect_google()

    assert status.connected is False
    assert status.auth_url is None
    assert not token_file.exists()
    assert adapter.service is None
    assert adapter.last_auth_url is None
    assert "GoogleCalendar" not in integration._scheduler.adapters
    assert integration._scheduler.cache.get_setting("google_export:t1", "") == ""


def test_connect_google_exposes_background_error(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    integration = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "cache.db"),
        iis_group_number="",
        google_credentials_file="",
    )

    class _FailingAdapter:
        is_authenticated = False
        last_auth_url = None
        last_auth_error = None

        def authenticate(self, interactive: bool = True) -> bool:
            raise RuntimeError("тестовая ошибка OAuth")

    integration._google_adapter = _FailingAdapter()  # type: ignore[assignment]
    status = integration.connect_google()

    assert status.auth_url is None
    for _ in range(20):
        if integration.google_status().auth_error and not integration._oauth_in_progress:
            break
        time.sleep(0.05)
    final = integration.google_status()
    assert final.auth_error == "тестовая ошибка OAuth"
    assert integration._oauth_in_progress is False
