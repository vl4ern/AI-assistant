import os
import pickle
from datetime import datetime
from typing import List, Optional
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ..interfaces import IServiceAdapter
from models.google_models import GoogleCalendarEvent
from models.task import Task

# Если модифицируем права, удаляем сохраненный токен
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class GoogleCalendarAdapter(IServiceAdapter):
    """Адаптер для синхронизации с Google Calendar"""

    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.pickle",
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.sync_token = None  # Для инкрементальной синхронизации

    def authenticate(self, token: str = None) -> bool:
        """
        Выполняет OAuth 2.0 аутентификацию.
        При первом запуске откроет браузер для авторизации.
        """
        creds = None

        # Загружаем сохраненный токен
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token_file:
                creds = pickle.load(token_file)

        # Если токена нет или он недействителен
        if not creds or not creds.valid:
            # Пробуем обновить токен
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Первый запуск — открываем браузер для авторизации
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=8080)

            # Сохраняем токен для будущих запусков
            with open(self.token_file, "wb") as token:
                pickle.dump(creds, token)

        # Создаем сервис Google Calendar
        self.service = build("calendar", "v3", credentials=creds)
        return True

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        """
        Получает изменения из Google Calendar.
        Использует инкрементальную синхронизацию через syncToken для эффективности.
        """
        if not self.service:
            raise Exception("Not authenticated. Call authenticate() first.")

        tasks = []

        try:
            if self.sync_token:
                # Инкрементальная синхронизация
                events_result = (
                    self.service.events()
                    .list(
                        calendarId="primary",
                        syncToken=self.sync_token,
                        showDeleted=True,
                    )
                    .execute()
                )
            else:
                # Первая полная синхронизация
                time_min = since or datetime(
                    2020, 1, 1
                )  # Если since не задан, берем далекое прошлое
                events_result = (
                    self.service.events()
                    .list(
                        calendarId="primary",
                        timeMin=time_min.isoformat() + "Z" if since else None,
                        showDeleted=True,
                        singleEvents=True,
                        maxResults=2500,  # Максимальное количество событий
                    )
                    .execute()
                )

            # Сохраняем токен для следующей инкрементальной синхронизации
            self.sync_token = events_result.get("nextSyncToken")

            # Конвертируем события в Task
            for event in events_result.get("items", []):
                task = GoogleCalendarEvent.from_google_event(event)
                if task:
                    tasks.append(task)

        except Exception as e:
            # Если syncToken устарел (ошибка 410), сбрасываем и пробуем заново
            if "410" in str(e) or "syncToken" in str(e).lower():
                self.sync_token = None
                return self.fetch_changes(since)
            raise

        return tasks

    def push_update(self, task: Task) -> bool:
        """
        Создает или обновляет событие в Google Calendar.
        """
        if not self.service:
            raise Exception("Not authenticated. Call authenticate() first.")

        event_body = {
            "summary": task.title,
            "description": task.description,
        }

        # Настройка времени
        if task.due_date:
            end_time = task.due_date + task.duration_minutes * 60  # approximated
            event_body["start"] = {
                "dateTime": task.due_date.isoformat(),
                "timeZone": "Europe/Minsk",
            }
            event_body["end"] = {
                "dateTime": end_time.isoformat(),
                "timeZone": "Europe/Minsk",
            }

        # Проверяем, существует ли событие
        try:
            if task.external_id:
                # Обновляем существующее
                self.service.events().update(
                    calendarId="primary", eventId=task.external_id, body=event_body
                ).execute()
            else:
                # Создаем новое
                self.service.events().insert(
                    calendarId="primary", body=event_body
                ).execute()
            return True
        except Exception as e:
            print(f"Error pushing to Google Calendar: {e}")
            return False

    def delete_task(self, external_id: str) -> bool:
        """Удаляет событие из Google Calendar"""
        if not self.service:
            raise Exception("Not authenticated. Call authenticate() first.")

        try:
            self.service.events().delete(
                calendarId="primary", eventId=external_id
            ).execute()
            return True
        except Exception as e:
            print(f"Error deleting from Google Calendar: {e}")
            return False
