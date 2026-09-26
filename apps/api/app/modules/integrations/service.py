from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from app.modules.integrations.integration.cache_storage import SQLiteCacheStorage
from app.modules.integrations.integration.conflict_resolver import ConflictResolver
from app.modules.integrations.integration.kb_bridge import (
    KnowledgeBaseBridge,
    KnowledgeIngestClient,
)
from app.modules.integrations.integration.interfaces import IServiceAdapter
from app.modules.integrations.integration.retry_queue import RetryQueue
from app.modules.integrations.integration.sync_scheduler import SyncScheduler
from app.modules.integrations.models import (
    IntegrationAdapterStatus,
    IntegrationSyncResult,
    Lesson,
    WeekInfo,
)
from app.modules.integrations.models.iis_models import academic_week
from app.modules.integrations.models.sync import SyncResult
from app.modules.integrations.models.task import SourceType, Task
from app.modules.knowledge.service import KnowledgeService

IIS_SYNC_INTERVAL_SECONDS = 7200
GOOGLE_CALENDAR_SYNC_INTERVAL_SECONDS = 900

ADAPTER_SOURCES = {
    "IIS": "bsuir-lms",
    "GoogleCalendar": "google-calendar",
}

DAY_ORDER = {
    "Понедельник": 0,
    "Вторник": 1,
    "Среда": 2,
    "Четверг": 3,
    "Пятница": 4,
    "Суббота": 5,
    "Воскресенье": 6,
}


def _parse_description_fields(description: str | None) -> dict[str, str]:
    """Разбирает строки описания занятия вида «Ключ: значение»."""
    fields: dict[str, str] = {}

    if not description:
        return fields

    for line in description.split("\n"):
        if line.startswith("📘 "):
            fields["subject_full_name"] = line.replace("📘 ", "").strip()
        elif ": " in line:
            key, _, value = line.partition(": ")
            fields[key.strip()] = value.strip()

    return fields


class IntegrationService:
    """
    Сервис интеграции с внешними источниками (IIS БГУИР, Google Calendar).

    Управляет планировщиком синхронизации и мостом в базу знаний:
    новые занятия и события автоматически попадают в KnowledgeService
    и становятся доступны планировщику задач.
    """

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        cache_path: str = "data/integration_cache.db",
        iis_group_number: str = "",
        google_credentials_file: str = "",
        google_token_file: str = "",
        semester_start_date: str = "",
        iis_horizon_days: int = 28,
    ) -> None:
        self._semester_start = self._parse_semester_start(semester_start_date)
        self._horizon_days = iis_horizon_days

        cache = SQLiteCacheStorage(cache_path)

        self._scheduler = SyncScheduler(
            cache=cache,
            resolver=ConflictResolver(cache),
            retry_queue=RetryQueue(),
        )
        self._bridge = KnowledgeBaseBridge(
            scheduler=self._scheduler,
            kb_client=KnowledgeIngestClient(knowledge_service),
        )

        self._register_adapters(
            iis_group_number=iis_group_number,
            google_credentials_file=google_credentials_file,
            google_token_file=google_token_file,
        )

    @staticmethod
    def _parse_semester_start(value: str) -> date:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return datetime.strptime("2026-09-01", "%Y-%m-%d").date()

    def _register_adapters(
        self,
        iis_group_number: str,
        google_credentials_file: str,
        google_token_file: str,
    ) -> None:
        if iis_group_number:
            from app.modules.integrations.integration.adapters.iis_adapter import IisAdapter

            self._scheduler.register_adapter(
                "IIS",
                IisAdapter(
                    iis_group_number,
                    semester_start=self._semester_start,
                    horizon_days=self._horizon_days,
                ),
                sync_interval=IIS_SYNC_INTERVAL_SECONDS,
            )

        if google_credentials_file and os.path.exists(google_credentials_file):
            try:
                from app.modules.integrations.integration.adapters.google_calendar_adapter import (
                    GoogleCalendarAdapter,
                )

                adapter = GoogleCalendarAdapter(
                    credentials_file=google_credentials_file,
                    token_file=google_token_file,
                )
                if adapter.authenticate():
                    self._scheduler.register_adapter(
                        "GoogleCalendar",
                        adapter,
                        sync_interval=GOOGLE_CALENDAR_SYNC_INTERVAL_SECONDS,
                    )
                else:
                    print("[Integrations] Ошибка аутентификации Google Calendar")
            except Exception as e:
                print(f"[Integrations] Google Calendar не настроен: {e}")

        if not self._scheduler.adapters:
            print("[Integrations] Адаптеры не настроены (укажите IIS_GROUP_NUMBER или credentials.json)")

    def list_adapters(self) -> list[IntegrationAdapterStatus]:
        statuses: list[IntegrationAdapterStatus] = []
        for name, adapter in self._scheduler.adapters.items():
            last_sync = self._scheduler.last_sync_time.get(name)
            statuses.append(
                IntegrationAdapterStatus(
                    name=name,
                    source=ADAPTER_SOURCES.get(name, "external"),
                    sync_interval_seconds=self._scheduler.intervals.get(name, 0),
                    last_sync_at=(last_sync if last_sync and last_sync != datetime.min else None),
                    running=self._scheduler._running,
                )
            )
        return statuses

    def list_lessons(self) -> list[Lesson]:
        """Возвращает занятия из кэша синхронизации в виде расписания."""
        lessons: list[Lesson] = []
        for task in self._scheduler.cache.get_all_tasks():
            if task.source_type != SourceType.IIS:
                continue
            lessons.append(self._task_to_lesson(task))
        lessons.sort(
            key=lambda lesson: (DAY_ORDER.get(lesson.day_of_week or "", 7), lesson.start_time)
        )
        return lessons

    def _task_to_lesson(self, task: Task) -> Lesson:
        fields = _parse_description_fields(task.description)

        start_time = task.due_date.strftime("%H:%M") if task.due_date else "00:00"
        end_dt = task.due_date + timedelta(minutes=task.duration_minutes)
        end_time = end_dt.strftime("%H:%M") if end_dt else "00:00"

        weeks_value = fields.get("Недели", "")
        week_numbers = [int(w) for w in weeks_value.replace(",", " ").split() if w.isdigit()]

        occurrence_week = None
        if task.due_date is not None:
            occurrence_week = academic_week(task.due_date.date(), self._semester_start)

        subgroup_value = fields.get("Подгруппа", "")
        try:
            subgroup = int(subgroup_value)
        except (ValueError, TypeError):
            subgroup = 0

        return Lesson(
            id=task.external_id,
            subject=task.title,
            subject_full_name=fields.get("subject_full_name", ""),
            day_of_week=fields.get("День недели"),
            start_time=start_time,
            end_time=end_time,
            lesson_type=fields.get("Тип", ""),
            teacher=fields.get("Преподаватель", ""),
            auditory=fields.get("Аудитория", ""),
            weeks=weeks_value,
            week_numbers=week_numbers,
            week=occurrence_week,
            subgroup=subgroup,
            next_date=task.due_date,
        )

    def sync_all(self) -> IntegrationSyncResult:
        result = self._scheduler.sync_all()
        return self._to_sync_result("all", result)

    def sync_adapter(self, adapter_name: str) -> IntegrationSyncResult:
        if adapter_name not in self._scheduler.adapters:
            raise ValueError(f"Adapter '{adapter_name}' not found")

        result = self._scheduler.sync_adapter_now(adapter_name)
        if result is None:
            raise ValueError(f"Adapter '{adapter_name}' not found")

        return self._to_sync_result(adapter_name, result)

    def get_week_info(self) -> WeekInfo:
        """Текущая учебная неделя (1–4) по дате начала семестра."""
        now = datetime.now()
        return WeekInfo(
            current_week=academic_week(now.date(), self._semester_start),
            semester_start=datetime.combine(self._semester_start, datetime.min.time()),
            today=now,
        )

    def import_schedule(self, data: dict) -> IntegrationSyncResult:
        """
        Импорт расписания из JSON-файла портала БГУИР.

        Формат тот же, что отдаёт iis.bsuir.by/api/v1/schedule — можно
        скачать расписание любой группы и загрузить его вручную, если
        онлайн-доступ к порталу недоступен или группа не задана в настройках.
        """
        from app.modules.integrations.integration.adapters.iis_adapter import (
            tasks_from_iis_payload,
        )

        tasks = tasks_from_iis_payload(
            data,
            semester_start=self._semester_start,
            horizon_days=self._horizon_days,
        )

        one_shot = _OneShotAdapter(tasks)
        self._scheduler.register_adapter("import", one_shot, sync_interval=0)
        try:
            result = self._scheduler.sync_adapter_now("import")
        finally:
            self._scheduler.adapters.pop("import", None)
            self._scheduler.intervals.pop("import", None)
            self._scheduler.last_sync_time.pop("import", None)

        if result is None:
            result = SyncResult(success=False, errors=["Импорт не выполнен"])

        return self._to_sync_result("import", result)

    def start_background(self, check_interval: int = 30) -> None:
        self._scheduler.start_background(check_interval=check_interval)

    def stop_background(self) -> None:
        self._scheduler.stop_background()

    def shutdown(self) -> None:
        self._bridge.shutdown()
        self._scheduler.stop_background()

    @staticmethod
    def _to_sync_result(provider: str, result: SyncResult) -> IntegrationSyncResult:
        has_errors = bool(result.errors)
        return IntegrationSyncResult(
            provider=provider,
            synced_items=result.tasks_synced,
            conflicts_detected=result.conflicts_detected,
            errors=list(result.errors),
            status="error" if has_errors else "ok",
            message=(
                "Synchronization completed with errors"
                if has_errors
                else "Synchronization completed"
            ),
        )


class _OneShotAdapter(IServiceAdapter):
    """Адаптер с заранее подготовленными задачами — для разового импорта."""

    def __init__(self, tasks: list[Task]) -> None:
        self._tasks = tasks

    def authenticate(self, token: str | None = None) -> bool:
        return True

    def fetch_changes(self, since: datetime | None = None) -> list[Task]:
        return self._tasks

    def push_update(self, task: Task) -> bool:
        return False

    def delete_task(self, external_id: str) -> bool:
        return False
