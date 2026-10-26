import os
import pickle
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ..interfaces import IServiceAdapter
from models.google_models import GoogleCalendarEvent
from models.task import Task, utc_now

# ВАЖНО: readonly НЕ подходит, потому что мы пишем события.
# calendar.events — минимально необходимый scope для CRUD событий.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class GoogleCalendarAdapter(IServiceAdapter):
    """Адаптер для двусторонней синхронизации с Google Calendar."""

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

    # ---------- аутентификация ----------

    def authenticate(self, token: str = None) -> bool:
        creds = None

        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Файл {self.credentials_file} не найден. "
                        f"См. инструкцию по получению OAuth-ключа."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_file, "wb") as f:
                pickle.dump(creds, f)

        self.service = build("calendar", "v3", credentials=creds)
        return True

    # ---------- чтение ----------

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        tasks: List[Task] = []
        page_token: Optional[str] = None

        # Если есть sync_token — инкрементальная синхронизация.
        # Иначе — полная, с ограничением по времени.
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
                    # Если since не задан — берём данные за последние 90 дней,
                    # чтобы не тянуть весь календарь целиком.
                    effective_since = since or (utc_now() - timedelta(days=90))
                    if effective_since.tzinfo is None:
                        effective_since = effective_since.replace(tzinfo=timezone.utc)

                    request = self.service.events().list(
                        calendarId=self.calendar_id,
                        timeMin=effective_since.isoformat(),
                        showDeleted=True,
                        singleEvents=True,
                        orderBy="startTime",
                        maxResults=2500,
                        pageToken=page_token,
                    )

                events_result = request.execute()
            except Exception as e:
                # syncToken устарел — сбрасываем и перезапрашиваем с нуля.
                if "410" in str(e) or "sync token" in str(e).lower():
                    self.sync_token = None
                    page_token = None
                    continue
                raise

            for event in events_result.get("items", []):
                task = GoogleCalendarEvent.from_google_event(event)
                if task is not None:
                    tasks.append(task)

            page_token = events_result.get("nextPageToken")
            if page_token:
                continue

            # Дошли до последней страницы — сохраняем syncToken.
            self.sync_token = events_result.get("nextSyncToken")
            break

        return tasks

    # ---------- запись ----------

    def push_update(self, task: Task) -> bool:
        """
        Создаёт или обновляет событие в Google Calendar.
        Если у задачи время 00:00 — создаём all-day событие (поле date),
        иначе — timed (поле dateTime).
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        if not task.due_date:
            return False

        start = task.due_date
        is_all_day = start.hour == 0 and start.minute == 0 and start.second == 0

        if is_all_day:
            # Google ожидает end.date = следующий день (эксклюзивная граница)
            end_date = (start + timedelta(days=1)).date()
            event_body = {
                "summary": task.title,
                "description": task.description or "",
                "start": {"date": start.date().isoformat()},
                "end": {"date": end_date.isoformat()},
            }
        else:
            end = start + timedelta(minutes=max(task.duration_minutes, 15))
            event_body = {
                "summary": task.title,
                "description": task.description or "",
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": self.timezone_name,
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": self.timezone_name,
                },
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
                    task.id = f"gc_{created['id']}"
            return True
        except Exception as e:
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
        except Exception as e:
            print(f"[GoogleCalendar] Ошибка delete_task: {e}")
            return False
