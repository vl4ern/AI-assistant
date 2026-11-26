import json
import os
import pickle
import threading
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
    get_local_tz,
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
        raw_query = urllib.parse.urlparse(uri).query
        query = urllib.parse.parse_qs(raw_query)
        if "error" in query:
            self.error = f"oauth_error:{query['error'][0]}"
            self.done = True
            return self._respond(start_response, f"error={self.error}".encode("utf-8"), "200 OK")
        if "code" not in query:
            # Посторонний запрос (favicon.ico, проверка порта) не должен
            # завершать OAuth-флоу — иначе он срывается до прихода callback'а.
            return self._respond(start_response, b"bad_request", "400 Bad Request")
        if query.get("state", [None])[0] != self.state:
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
        self.last_auth_url: Optional[str] = None
        self.last_auth_error: Optional[str] = None
        self._token_needs_normalization = False
        self._flow_lock = threading.Lock()

    @property
    def is_authenticated(self) -> bool:
        return self.service is not None

    # ---------- аутентификация ----------

    def _client_config(self) -> dict:
        """OAuth-ключ установленного приложения (client_id/secret/token_uri)."""
        with open(self.credentials_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("installed") or config.get("web") or {}

    @staticmethod
    def _expiry_from_token(token: dict) -> Optional[datetime]:
        expires_at = token.get("expires_at")
        if not expires_at:
            return None
        try:
            # google.auth.Credentials ожидает naive UTC (сравнивает с
            # helpers.utcnow(), у которого tzinfo снят).
            return datetime.fromtimestamp(float(expires_at), tz=timezone.utc).replace(
                tzinfo=None
            )
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    def _coerce_credentials(self, creds):
        """Привести прочитанный из pickle объект к google Credentials.

        Исторически в токен-файл попадал результат ``flow.fetch_token()`` —
        ``OAuth2Token`` (обычный dict), а не ``Credentials``. Такой файл
        нельзя использовать ни для build(), ни для refresh(), поэтому
        восстанавливаем Credentials из сохранённых полей и OAuth-ключа.
        """
        if creds is None:
            return None
        if isinstance(creds, Credentials):
            return creds
        if not hasattr(creds, "get"):
            return None

        config = self._client_config()
        if not config.get("client_id") or not config.get("token_uri"):
            return None
        try:
            return Credentials(
                token=creds.get("access_token"),
                refresh_token=creds.get("refresh_token"),
                token_uri=config["token_uri"],
                client_id=config["client_id"],
                client_secret=config.get("client_secret", ""),
                scopes=creds.get("scope") or SCOPES,
                expiry=self._expiry_from_token(creds),
            )
        except Exception:  # noqa: BLE001 — несовместимый формат токена
            return None

    def _load_saved_credentials(self):
        if not os.path.exists(self.token_file):
            return None
        try:
            with open(self.token_file, "rb") as f:
                creds = pickle.load(f)
        except Exception:  # noqa: BLE001 — битый/чужой файл токена
            self._token_needs_normalization = False
            return None

        self._token_needs_normalization = not isinstance(creds, Credentials)
        creds = self._coerce_credentials(creds)
        if creds is None:
            return None
        # Токен, выданный на старый scope (readonly), для записи не годится.
        if not creds.has_scopes(SCOPES):
            return None
        return creds

    def authenticate(
        self, token: Optional[str] = None, interactive: bool = True
    ) -> bool:
        """
        OAuth 2.0.

        interactive=False — только сохранённый токен (с автообновлением),
        без ожидания браузера: так безопасно вызывать при старте сервера.
        interactive=True — при отсутствии токена генерирует auth_url и
        ждёт callback на локальном сервере (фронтенд открывает окно входа).
        """
        creds = self._load_saved_credentials()
        self.last_auth_error = None
        needs_save = self._token_needs_normalization

        if creds is not None and not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    needs_save = True
                except Exception as exc:  # noqa: BLE001 — токен отозван/просрочен
                    self.last_auth_error = f"не удалось обновить токен: {exc}"
                    creds = None
            else:
                creds = None

        fresh_auth = creds is None or not creds.valid
        if fresh_auth:
            if not interactive:
                if creds is None:
                    self.last_auth_error = self.last_auth_error or "сохранённый токен недействителен"
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
            self.last_auth_url = auth_url
            self.last_auth_error = None

            print("\n" + "="*50)
            print("ПЕРЕЙДИ ПО ЭТОЙ ССЫЛКЕ В БРАУЗЕРЕ:")
            print(auth_url)
            print("="*50 + "\n")

            creds = self._run_local_callback_server(flow=flow, state=state, port=8080)
            needs_save = True

        if needs_save:
            token_dir = os.path.dirname(self.token_file)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
            try:
                with open(self.token_file, "wb") as f:
                    pickle.dump(creds, f)
            except OSError as exc:
                message = (
                    f"Не удалось записать токен в {self.token_file} "
                    "(проверьте, что каталог смонтирован для записи)"
                )
                if fresh_auth:
                    # После согласия в браузере потерять токен нельзя —
                    # пользователь должен увидеть ошибку и повторить вход.
                    raise ValueError(message) from exc
                # Старый формат токена можно переконвертировать в памяти:
                # авторизация рабочая, просто файл остаётся старым.
                print(f"[GoogleCalendar] {message}: {exc}")
                self.last_auth_error = message

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

        # Несколько параллельных OAuth-флоу на одном порту не должны
        # конфликтовать — второй ждёт, пока первый отпустит порт.
        with self._flow_lock:
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

        authorization_response = callback_app.uri.replace("http://", "https://", 1)
        # flow.fetch_token() возвращает OAuth2Token (dict), а не Credentials.
        # Нужен именно flow.credentials — иначе в токен-файл попадёт словарь,
        # с которым не работает ни build(), ни refresh().
        flow.fetch_token(authorization_response=authorization_response)
        return flow.credentials

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
                    # SyncScheduler передаёт datetime.min как «никогда не
                    # синхронизировали» — его нельзя переводить в UTC
                    # (вылезет год 0), поэтому считаем его отсутствием since.
                    effective_since = since
                    if effective_since is not None and effective_since.year < 1900:
                        effective_since = None
                    effective_since = effective_since or (
                        datetime.now(timezone.utc) - timedelta(days=90)
                    )
                    if effective_since.tzinfo is None:
                        # Локальный naive → aware в поясе приложения.
                        effective_since = effective_since.replace(tzinfo=get_local_tz())
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

    def delete_exported_events(self) -> int:
        """Удалить из Google все события, созданные экспортом ассистента.

        Импорт намеренно пропускает такие события (метка `ai_assistant`),
        поэтому без этой операции они копятся в календаре копиями расписания
        и задач. Возвращает число удалённых событий.
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        event_ids: List[str] = []
        page_token: Optional[str] = None
        while True:
            result = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id,
                    privateExtendedProperty=f"{EXPORT_MARKER_KEY}=1",
                    maxResults=2500,
                    pageToken=page_token,
                )
                .execute()
            )
            event_ids.extend(
                item["id"] for item in result.get("items", []) if item.get("id")
            )
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        deleted = 0
        for event_id in event_ids:
            if self.delete_task(event_id):
                deleted += 1
        return deleted
