from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.modules.integrations.integration.interfaces import IServiceAdapter
from app.modules.integrations.models.iis_models import IisScheduleItem
from app.modules.integrations.models.task import Task

REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 1.5  # 0с, 1.5с, 3с, 4.5с между попытками
RETRY_STATUS_CODES = (500, 502, 503, 504)


def resolve_payload_group(data: Dict[str, Any], override: str = "") -> str:
    """
    Определяет номер группы в данных расписания.

    Явное значение важнее; иначе берём группу из ответа портала
    (поле studentGroup.name), если она там есть.
    """
    if override.strip():
        return override.strip()

    student_group = data.get("studentGroup")
    if isinstance(student_group, dict):
        return str(student_group.get("name") or "").strip()
    if isinstance(student_group, str):
        return student_group.strip()
    return ""


def tasks_from_iis_payload(
    data: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    semester_start: Optional[date] = None,
    horizon_days: int = 28,
    group_number: str = "",
) -> List[Task]:
    """
    Преобразует JSON портала БГУИР (метод /api/v1/schedule) в список задач.

    Один и тот же парсер работает и для онлайн-синхронизации, и для
    импорта расписания из файла — формат идентичен.
    """
    now = now or datetime.now()
    group = resolve_payload_group(data, group_number)
    tasks: List[Task] = []

    schedules = data.get("schedules", {})
    for day_name, lessons in schedules.items():
        if not isinstance(lessons, list):
            continue
        for lesson in lessons:
            item = IisScheduleItem.from_dict(lesson, day_of_week=day_name)
            tasks.extend(
                item.to_tasks(
                    now,
                    semester_start=semester_start,
                    horizon_days=horizon_days,
                    group_number=group,
                )
            )

    exams = data.get("exams", [])
    for exam in exams:
        if isinstance(exam, dict):
            item = IisScheduleItem.from_dict(exam, day_of_week=None)
            tasks.extend(
                item.to_tasks(
                    now,
                    semester_start=semester_start,
                    horizon_days=horizon_days,
                    group_number=group,
                )
            )

    return tasks


def _build_retry_session() -> requests.Session:
    """HTTP-сессия с повторами и нарастающей паузой (идея из ветки коллеги)."""
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


class IisAdapter(IServiceAdapter):
    """Адаптер для получения расписания БГУИР через портал iis.bsuir.by."""

    BASE_URL = "https://iis.bsuir.by/api/v1"

    def __init__(
        self,
        group_number: str,
        *,
        semester_start: Optional[date] = None,
        horizon_days: int = 28,
    ):
        self.group_number = group_number
        self.semester_start = semester_start
        self.horizon_days = horizon_days
        self._session = _build_retry_session()

    def authenticate(self, token: str = None) -> bool:
        # API открытый, аутентификация не требуется
        return True

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        """
        Получает актуальное расписание группы и разворачивает занятия
        по датам учебных недель в пределах горизонта планирования.
        """
        params = {"studentGroup": self.group_number}
        try:
            response = self._session.get(
                f"{self.BASE_URL}/schedule", params=params, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Ошибка запроса к API БГУИР: {e}") from e

        return tasks_from_iis_payload(
            response.json(),
            semester_start=self.semester_start,
            horizon_days=self.horizon_days,
            group_number=self.group_number,
        )

    def push_update(self, task: Task) -> bool:
        raise NotImplementedError(
            "Обновление расписания не поддерживается (только чтение)"
        )

    def delete_task(self, external_id: str) -> bool:
        raise NotImplementedError("Удаление расписания не поддерживается")
