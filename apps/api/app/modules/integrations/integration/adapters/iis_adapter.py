from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests

from app.modules.integrations.integration.interfaces import IServiceAdapter
from app.modules.integrations.models.iis_models import IisScheduleItem
from app.modules.integrations.models.task import Task


def tasks_from_iis_payload(
    data: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    semester_start: Optional[date] = None,
    horizon_days: int = 28,
) -> List[Task]:
    """
    Преобразует JSON портала БГУИР (метод /api/v1/schedule) в список задач.

    Один и тот же парсер работает и для онлайн-синхронизации, и для
    импорта расписания из файла — формат идентичен.
    """
    now = now or datetime.now()
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
                )
            )

    return tasks


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
            response = requests.get(
                f"{self.BASE_URL}/schedule", params=params, timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Ошибка запроса к API БГУИР: {e}") from e

        return tasks_from_iis_payload(
            response.json(),
            semester_start=self.semester_start,
            horizon_days=self.horizon_days,
        )

    def push_update(self, task: Task) -> bool:
        raise NotImplementedError(
            "Обновление расписания не поддерживается (только чтение)"
        )

    def delete_task(self, external_id: str) -> bool:
        raise NotImplementedError("Удаление расписания не поддерживается")
