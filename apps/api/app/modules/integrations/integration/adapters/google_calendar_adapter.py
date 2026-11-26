import os
import pickle
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from wsgiref import simple_server
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer
from wsgiref.util import request_uri

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.modules.integrations.integration.interfaces import IServiceAdapter
from app.modules.integrations.models.google_models import (
    EXPORT_MARKER_KEY,
    GoogleCalendarEvent,
)
from app.modules.integrations.models.task import Task

# readonly не подходит: адаптер ещё и пишет события (экспорт плана).
# calendar.events — минимальный scope для чтения и записи событий.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class _OAuthCallbackApp:
    """WSGI-приложение локального сервера OAuth redirect.

    Принимает только корректный callback: параметры `code` и `state`
    должны совпасть с сгенерированными в процессе авторизации. Иначе
    считается неуспешным завершением и запрос просто отклоняется — без
    «успешной» страницы для произвольного GET.
    """

    def __init__(self, flow: InstalledAppFlow, state: str) -> None:
        self.flow = flow
        self.state = state
        self.uri: Optional[str] = None
        self.error: Optional[str] = None
        self.done = False

    def _respond(self, start_response, body: bytes, status: str) -> List[bytes]:
        start_response(status, [("Content-type", "text/plain; charset=utf-8")])
        return [body]

    def __call__(self, environ, start_response):  # noqa: ANN001, ANN202
        if self.done:
            return self._respond(start_response, b"bad_request", "400 Bad Request")
        uri = request_uri(environ)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(uri).query)
        if "error" in query:
            self.error = f"oauth_error:{query['error'][0]}"
            self.done = True
            return self._respond(start_response, f"error={self.error}".encode("utf-8"), "200 OK")
        if "code" not in query or query.get("state", [None])[0] != self.state:
            self.error = "invalid_request"
            self.done = True
            return self._respond(start_response, b"invalid_request", "400 Bad Request")
        self.uri = uri
        self.done = True
        return self._respond(start_response, b"ok", "200 OK")


class GoogleCalendarAdapter(IServiceAdapter):
    """Адаптер двусторонней синхронизации с Google Calendar."""

    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "google_token.pickle",
        calendar_id: str = "primary",
        timezone_name: str = "Europe/Minsk",
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.calendar_id = calendar_id
        self.timezone_name = timezone_name
        self.service = None
        self.sync_token: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return self.service is not None

    # ---------- аутентификация ----------

    def _load_saved_credentials(self):
        if not os.path.exists(self.token_file):
            return None
        try:
            with open(self.token_file, "rb") as f:
                creds = pickle.load(f)
        except Exception:  # noqa: BLE001 — битый/чужой файл токена
            return None
        # Токен, выданный на старый scope (readonly), для записи не годится.
        if (
            creds is not None
            and hasattr(creds, "has_scopes")
            and not creds.has_scopes(SCOPES)
        ):
            return None
        return creds

    def authenticate(
        self, token: Optional[str] = None, interactive: bool = True
    ) -> bool:
        """
        OAuth 2.0.

        interactive=False — только сохранённый токен (с автообновлением),
        без открытия браузера: так безопасно вызывать при старте сервера.
        interactive=True — при отсутствии токена откроет браузер
        на машине, где запущен backend.
        """
        creds = self._load_saved_credentials()

        if creds and not creds.valid and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:  # noqa: BLE001 — токен отозван/просрочен
                creds = None

        if not creds or not creds.valid:
            if not interactive:
                return False
            if not os.path.exists(self.credentials_file):
                raise FileNotFoundError(
                    f"Файл {self.credentials_file} не найден. "
                    "Скачайте OAuth-ключ (Desktop app) из Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file, SCOPES
            )
            # Явно задаём локальный callback: сервер слушает 0.0.0.0:8080
            # (порт публикуется compose), а без явного redirect_uri у flow
            # redirect_uri = None — и Google отклоняет запрос авторизации.
            flow.oauth2session.redirect_uri = "http://localhost:8080/"
            auth_url, state = flow.authorization_url(prompt="consent")
            
            print("\n" + "="*50)
            print("ПЕРЕЙДИ ПО ЭТОЙ ССЫЛКЕ В БРАУЗЕРЕ:")
            print(auth_url)
            print("="*50 + "\n")

            creds = self._run_local_callback_server(flow=flow, state=state, port=8080)

        with open(self.token_file, "wb") as f:
            pickle.dump(creds, f)

        self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return True

    def _run_local_callback_server(
        self,
        flow: InstalledAppFlow,
        state: str,
        port: int = 8080,
        timeout_seconds: float = 300.0,
    ) -> Credentials:
        """
        Запускает локальный callback-сервер OAuth-потока.

        - сервер слушает `0.0.0.0:{port}` (в Docker порт публикуется наружу);
        - ожидание ограничено `timeout_seconds` — после таймаута сервер
          закрывается и порт освобождается;
        - callback обрабатывается только при корректном `state`/`code`;
        - после ответа сервер обязательно закрывается (на порт не остаётся
          «зависший» процесс, иначе повторные попытки дают EADDRINUSE).
        """
        callback_app = _OAuthCallbackApp(flow, state)

        server = simple_server.make_server(
            "0.0.0.0",
            port,
            callback_app,
            server_class=WSGIServer,
            handler_class=WSGIRequestHandler,
        )
        server.timeout = timeout_seconds
        try:
            server.handle_request()
        finally:
            server.server_close()

        if callback_app.error is not None:
            raise ValueError(f"OAuth-авторизация не удалась: {callback_app.error}")
        if callback_app.uri is None:
            raise TimeoutError("Время ожидания ответа от Google истекло")

        authorization_response = callback_app.uri.replace("http", "https")
        return flow.fetch_token(authorization_response=authorization_response)

    # ---------- чтение ----------

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        tasks: List[Task] = []
        page_token: Optional[str] = None

        while True:
            try:
                if self.sync_token:
                    request = self.service.events().list(
                        calendarId=self.calendar_id,
                        syncToken=self.sync_token,
                        showDeleted=True,
                        pageToken=page_token,
                        maxResults=2500,
                    )
                else:
                    # Без since берём последние 90 дней, а не весь календарь.
                    effective_since = since or (datetime.now() - timedelta(days=90))
                    if effective_since.tzinfo is None:
                        effective_since = (
                            effective_since.astimezone()
                        )  # локальный → aware
                    time_min = effective_since.astimezone(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                    request = self.service.events().list(
                        calendarId=self.calendar_id,
                        timeMin=time_min,
                        showDeleted=True,
                        singleEvents=True,
                        orderBy="startTime",
                        maxResults=2500,
                        pageToken=page_token,
                    )

                events_result = request.execute()
            except Exception as e:  # noqa: BLE001
                # syncToken устарел (410) — сбрасываем и начинаем с нуля.
                if self.sync_token and (
                    "410" in str(e) or "sync token" in str(e).lower()
                ):
                    self.sync_token = None
                    page_token = None
                    tasks = []
                    continue
                raise

            for event in events_result.get("items", []):
                task = GoogleCalendarEvent.from_google_event(event)
                if task is not None:
                    tasks.append(task)

            page_token = events_result.get("nextPageToken")
            if page_token:
                continue

            self.sync_token = events_result.get("nextSyncToken")
            break

        return tasks

    # ---------- запись ----------

    def push_update(self, task: Task) -> bool:
        """
        Создаёт или обновляет событие в Google Calendar.
        due_date — naive, в локальном поясе (timezone_name).
        Событие помечается extendedProperties.private.ai_assistant,
        чтобы при обратной синхронизации его можно было отличить.
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        if not task.due_date:
            return False

        start = task.due_date
        end = start + timedelta(minutes=max(task.duration_minutes, 15))
        event_body = {
            "summary": task.title,
            "description": task.description or "",
            "start": {"dateTime": start.isoformat(), "timeZone": self.timezone_name},
            "end": {"dateTime": end.isoformat(), "timeZone": self.timezone_name},
            "extendedProperties": {"private": {EXPORT_MARKER_KEY: "1"}},
        }

        try:
            if task.external_id:
                updated = (
                    self.service.events()
                    .update(
                        calendarId=self.calendar_id,
                        eventId=task.external_id,
                        body=event_body,
                    )
                    .execute()
                )
                if updated.get("id"):
                    task.external_id = updated["id"]
            else:
                created = (
                    self.service.events()
                    .insert(calendarId=self.calendar_id, body=event_body)
                    .execute()
                )
                if created.get("id"):
                    task.external_id = created["id"]
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[GoogleCalendar] Ошибка push_update: {e}")
            return False

    def delete_task(self, external_id: str) -> bool:
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        try:
            self.service.events().delete(
                calendarId=self.calendar_id, eventId=external_id
            ).execute()
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[GoogleCalendar] Ошибка delete_task: {e}")
            return False
