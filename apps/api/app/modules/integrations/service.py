from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

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

# Маркер «настройка группы ещё никогда не записывалась»: отличается от
# пустой строки, которой группа сбрасывается при импорте без группы.
CURRENT_GROUP_UNSET = "__unset__"

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

        # Группа, выбранная пользователем в прошлый раз, важнее значения
        # из настроек: расписание продолжает синхронизироваться по ней.
        stored_group = cache.get_setting("current_group", CURRENT_GROUP_UNSET)
        if stored_group != CURRENT_GROUP_UNSET and stored_group:
            iis_group_number = stored_group

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
        """
        Возвращает занятия из кэша синхронизации в виде расписания.

        Показываем только текущую группу — ту, что пользователь ввёл
        последней (или загрузил из файла). Занятия других групп в кэше
        не отображаются. Прошедшие появления не показываем, а появления
        с одинаковым естественным ключом (дата, время, предмет, аудитория,
        подгруппа) сворачиваем в одно — портал иногда правит записи
        (например, список недель), от чего меняется идентификатор и старая
        копия зависает в кэше дублем.
        """
        today_start = datetime.combine(date.today(), time.min)
        current_group = self.get_current_group()
        lessons: list[Lesson] = []
        seen_keys: set[tuple] = set()

        for task in self._scheduler.cache.get_all_tasks():
            if task.source_type != SourceType.IIS:
                continue
            if task.due_date is not None and task.due_date < today_start:
                continue
            # Только текущая группа: после синка/импорта с новой группой
            # расписание прежней не должно смешиваться с новым.
            if current_group and task.group_number != current_group:
                continue

            lesson = self._task_to_lesson(task)
            key = (
                task.due_date,
                lesson.start_time,
                lesson.subject,
                lesson.auditory,
                lesson.subgroup,
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            lessons.append(lesson)

        lessons.sort(
            key=lambda lesson: (DAY_ORDER.get(lesson.day_of_week or "", 7), lesson.start_time)
        )
        return lessons

    def get_current_group(self) -> str:
        """Номер группы, расписание которой сейчас показывается."""
        get_setting = getattr(self._scheduler.cache, "get_setting", None)
        if get_setting is not None:
            stored = get_setting("current_group", CURRENT_GROUP_UNSET)
            if stored != CURRENT_GROUP_UNSET:
                return stored

        # Группу никогда не выбирали — фолбэк на группу IIS-адаптера из настроек
        adapter = self._scheduler.adapters.get("IIS")
        return getattr(adapter, "group_number", "") or ""

    def _set_current_group(self, group: str) -> None:
        set_setting = getattr(self._scheduler.cache, "set_setting", None)
        if set_setting is None:
            return
        set_setting("current_group", group.strip())

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
            group_number=task.group_number,
        )

    def sync_all(self) -> IntegrationSyncResult:
        result = self._scheduler.sync_all()
        self._purge_past_occurrences()
        self._reconcile_stale_occurrences(set(result.seen_external_ids))
        return self._to_sync_result("all", result)

    def sync_adapter(self, adapter_name: str) -> IntegrationSyncResult:
        if adapter_name not in self._scheduler.adapters:
            raise ValueError(f"Adapter '{adapter_name}' not found")

        result = self._scheduler.sync_adapter_now(adapter_name)
        if result is None:
            raise ValueError(f"Adapter '{adapter_name}' not found")

        self._purge_past_occurrences()
        # Реконсиляция — только по данным IIS: они авторитетны для расписания.
        # Синк другого адаптера не должен затирать занятия.
        if adapter_name == "IIS":
            self._reconcile_stale_occurrences(set(result.seen_external_ids))
        return self._to_sync_result(adapter_name, result)

    def _reconcile_stale_occurrences(
        self, keep_external_ids: set[str], force: bool = False
    ) -> None:
        """
        Удаляет «осиротевшие» появления с будущими датами.

        Если портал правит запись (недели, название), меняется её
        идентификатор, и старая копия зависает в кэше дублем. После
        синхронизации IIS его данные авторитетны: всё будущие появления,
        которых не было в ответе портала, — мусор. Прошедшие не трогаем
        (их чистит отдельная уборка). force=True применяется и без
        IIS-адаптера — так импорт из файла полностью заменяет прежнее
        расписание, а не смешивается с ним.
        """
        if not keep_external_ids:
            return
        if not force and "IIS" not in self._scheduler.adapters:
            return

        today_start = datetime.combine(date.today(), time.min)
        cache = self._scheduler.cache
        stale = [
            task
            for task in cache.get_all_tasks()
            if task.source_type == SourceType.IIS
            and task.external_id not in keep_external_ids
            and task.due_date is not None
            and task.due_date >= today_start
        ]
        for task in stale:
            cache.delete_task(task.id)
        if stale:
            print(f"[Integrations] Удалено устаревших появлений: {len(stale)}")

    def _purge_past_occurrences(self) -> None:
        """
        Чистит из кэша появления занятий с прошедшими датами.

        Без чистки кэш копит появления каждой синхронизации, и в недельном
        виде одна и та же пара показывается несколько раз (прошедший цикл +
        будущий). Чистим после синхронизации: дедупликация по external_id
        уже отработала, а новые появления с портала всегда начинаются
        с сегодняшнего дня.
        """
        purge_method = getattr(self._scheduler.cache, "delete_tasks_before", None)
        if purge_method is None:
            return

        cutoff = datetime.combine(date.today(), time.min)
        removed = purge_method(cutoff)
        if removed:
            print(f"[Integrations] Из кэша удалено прошедших появлений: {removed}")

    def get_week_info(self) -> WeekInfo:
        """Текущая учебная неделя (1–4) по дате начала семестра."""
        now = datetime.now()
        return WeekInfo(
            current_week=academic_week(now.date(), self._semester_start),
            semester_start=datetime.combine(self._semester_start, datetime.min.time()),
            today=now,
        )

    def import_schedule(self, data: dict, group_number: str = "") -> IntegrationSyncResult:
        """
        Импорт расписания (payload формата iis.bsuir.by/api/v1/schedule).

        Работает и для JSON-ответа портала, и для XLSX-файла, который
        парсер приводит к тому же формату. Импортированное расписание
        полностью заменяет прежнее: занятия, которых нет в файле,
        из кэша удаляются. Группа определяется из данных или берётся
        из подсказки (номер, введённый в интерфейсе) и становится текущей.
        """
        from app.modules.integrations.integration.adapters.iis_adapter import (
            resolve_payload_group,
            tasks_from_iis_payload,
        )

        group = resolve_payload_group(data, group_number)
        tasks = tasks_from_iis_payload(
            data,
            semester_start=self._semester_start,
            horizon_days=self._horizon_days,
            group_number=group,
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

        self._purge_past_occurrences()
        # Импорт авторитетен: прежнее расписание (в т.ч. другой группы) вычищаем
        self._reconcile_stale_occurrences(set(result.seen_external_ids), force=True)

        provider = group or "import"
        if not result.errors:
            self._set_current_group(group)
        return self._to_sync_result(provider, result)

    def import_schedule_file(
        self, content: bytes, group_hint: str = ""
    ) -> IntegrationSyncResult:
        """
        Импорт расписания из XLSX-файла (выгрузка расписания группы).

        Файл разбирается в формат портала и проходит обычный конвейер
        импорта: учебные недели, кэш, база знаний. Группа берётся из
        файла, а если её там нет — из номера, введённого пользователем.
        """
        from app.modules.integrations.integration.xlsx_import import parse_schedule_xlsx

        if not content:
            raise ValueError("Файл пустой")

        payload, group = parse_schedule_xlsx(content, group_hint=group_hint)
        return self.import_schedule(payload, group_number=group)

    def sync_group(self, group_number: str) -> IntegrationSyncResult:
        """
        Синхронизация расписания группы, введённой пользователем.

        Группа из настроек — лишь значение по умолчанию: пользователь может
        ввести свой номер группы в интерфейсе, и расписание загрузится с
        портала для неё. Введённая группа запоминается и для фоновых
        синхронизаций.
        """
        from app.modules.integrations.integration.adapters.iis_adapter import IisAdapter

        group = group_number.strip()
        if not group:
            raise ValueError("Укажите номер группы")

        adapter = IisAdapter(
            group,
            semester_start=self._semester_start,
            horizon_days=self._horizon_days,
        )

        # Группа становится текущей и для фоновых синхронизаций
        self._scheduler.register_adapter(
            "IIS", adapter, sync_interval=IIS_SYNC_INTERVAL_SECONDS
        )
        result = self._scheduler.sync_adapter_now("IIS")
        if result is None:
            result = SyncResult(success=False, errors=["Синхронизация не выполнена"])

        self._purge_past_occurrences()
        # Данные этой группы авторитетны: прошлую группу вычищаем
        self._reconcile_stale_occurrences(set(result.seen_external_ids))
        # Расписание показываем только для введённой группы — но лишь когда
        # синк прошёл успешно, иначе под новой подписью окажется старое.
        if not result.errors:
            self._set_current_group(group)
        return self._to_sync_result(group, result)

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
