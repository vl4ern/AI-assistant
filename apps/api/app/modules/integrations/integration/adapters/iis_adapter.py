import requests
from datetime import datetime
from typing import List, Optional

from ..interfaces import IServiceAdapter
from app.modules.integrations.models.iis_models import IisScheduleItem
from app.modules.integrations.models.task import Task


class IisAdapter(IServiceAdapter):
    """Адаптер для получения расписания БГУИР"""

    def __init__(self, group_number: str):
        self.group_number = group_number
        self.base_url = "https://iis.bsuir.by/api/v1"

    def authenticate(self, token: str = None) -> bool:
        # API открытый, аутентификация не требуется
        return True

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        """
        Получает актуальное расписание группы.
        Параметр since не используется, т.к. API всегда возвращает весь семестр.
        """
        params = {"studentGroup": self.group_number}
        try:
            response = requests.get(
                f"{self.base_url}/schedule", params=params, timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Ошибка запроса к API БГУИР: {e}")

        data = response.json()
        tasks = []

        # Текущая дата для вычисления дат занятий
        base_date = datetime.now()

        # Обрабатываем регулярное расписание
        schedules = data.get("schedules", {})
        for day_name, lessons in schedules.items():
            if not isinstance(lessons, list):
                continue
            for lesson in lessons:
                item = IisScheduleItem.from_dict(lesson, day_of_week=day_name)
                tasks.append(item.to_task(base_date, is_exam=False))

        # Обрабатываем экзамены
        exams = data.get("exams", [])
        for exam in exams:
            if isinstance(exam, dict):
                item = IisScheduleItem.from_dict(exam, day_of_week=None)
                tasks.append(item.to_task(base_date, is_exam=True))

        return tasks

    def push_update(self, task: Task) -> bool:
        raise NotImplementedError(
            "Обновление расписания не поддерживается (только чтение)"
        )

    def delete_task(self, external_id: str) -> bool:
        raise NotImplementedError("Удаление расписания не поддерживается")
