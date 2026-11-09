import os
import pickle
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from google.auth.transport.requests import Request
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
        if creds is not None and hasattr(creds, "has_scopes") and not creds.has_scopes(SCOPES):
            return None
        return creds

    def authenticate(self, token: Optional[str] = None, interactive: bool = True) -> bool:
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
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(self.token_file, "wb") as f:
            pickle.dump(creds, f)

        self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return True

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
                        effective_since = effective_since.astimezone()  # локальный → aware
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
                if self.sync_token and ("410" in str(e) or "sync token" in str(e).lower()):
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
                    .update(calendarId=self.calendar_id, eventId=task.external_id, body=event_body)
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
