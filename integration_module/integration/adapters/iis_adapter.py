import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..interfaces import IServiceAdapter
from models.iis_models import IisScheduleItem
from models.task import Task, utc_now
import threading

logger = logging.getLogger(__name__)


class IisAdapter(IServiceAdapter):
    """
    Адаптер для получения расписания БГУИР.

    Особенности API:
      - /schedule/current-week возвращает позицию недели В ЦИКЛЕ (1..week_cycle),
        а не номер недели семестра. Проверено вручную.
      - В каждой паре weekNumber содержит позиции недель цикла,
        в которые эта пара проводится (например, [1, 3]).
    """

    def __init__(
        self,
        group_number: str,
        week_cycle: int = 4,
        request_timeout: int = 30,
        max_retries: int = 3,
        on_group_change=None, # ДОБАВИТЬ
    ):
        self._group_number = str(group_number).strip() # ДОБАВИТЬ ПОДЧЕРКИВАНИЕ
        self.week_cycle = week_cycle
        self.request_timeout = request_timeout
        self._on_group_change = on_group_change # ДОБАВИТЬ
        self._group_lock = threading.Lock()      # ДОБАВИТЬ
        self.base_url = "https://iis.bsuir.by/api/v1"

        self._session = requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=1.5,  # 0с, 1.5с, 3с, 4.5с между попытками
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.mount("http://", HTTPAdapter(max_retries=retry))

    def authenticate(self, token: str = None) -> bool:
        return True  # API открытый

    # ---------------------------------------------------------------- helpers
    @property
    def group_number(self) -> str:
        with self._group_lock:
            return self._group_number

    def set_group_number(self, new_group: str) -> bool:
        new_group = str(new_group).strip()
        if not new_group:
            raise ValueError("group_number не может быть пустым")

        with self._group_lock:
            old = self._group_number
            if new_group == old:
                return False
            self._group_number = new_group

        print(f"[IIS] Группа изменена: {old} → {new_group}")
        if self._on_group_change:
            try:
                self._on_group_change(old, new_group)
            except Exception as e:
                print(f"[IIS] Ошибка в callback on_group_change: {e}")
        return True

    def _get_position_in_cycle(self) -> int:
        """
        Возвращает позицию текущей недели в цикле (1..week_cycle).
        API уже отдаёт это значение — нам не нужно ничего преобразовывать.
        """
        url = f"{self.base_url}/schedule/current-week"
        try:
            response = self._session.get(url, timeout=self.request_timeout)
            response.raise_for_status()
            raw = response.json()
        except requests.RequestException as e:
            raise Exception(f"Ошибка запроса current-week: {e}")

        logger.info(
            "[IIS] /schedule/current-week → HTTP %s, raw=%r (type=%s)",
            response.status_code,
            raw,
            type(raw).__name__,
        )

        # API может вернуть число или объект — нормализуем.
        if isinstance(raw, dict):
            for key in ("currentWeek", "week", "weekNumber", "value"):
                if key in raw:
                    raw = raw[key]
                    break
            else:
                raise ValueError(f"Неизвестный формат current-week: {raw}")

        try:
            value = int(raw)
        except (ValueError, TypeError):
            raise ValueError(f"current-week вернул не число: {raw!r}")

        # Защитная валидация: значение должно попадать в диапазон цикла.
        if not (1 <= value <= self.week_cycle):
            logger.warning(
                "[IIS] current-week вернул %s, что вне диапазона 1..%s. "
                "Применяю защитную нормализацию.",
                value,
                self.week_cycle,
            )
            value = ((value - 1) % self.week_cycle) + 1

        logger.info("[IIS] position_in_cycle = %s", value)
        return value

    def _fallback_position_in_cycle(self, now: datetime) -> int:
        """
        Если /current-week недоступен — считаем приблизительно
        от даты начала семестра и сворачиваем в цикл.
        """
        y, m = now.year, now.month
        if 9 <= m <= 12:
            start = datetime(y, 9, 1, tzinfo=timezone.utc)
        elif m == 1:
            start = datetime(y - 1, 9, 1, tzinfo=timezone.utc)
        elif 2 <= m <= 6:
            start = datetime(y, 2, 7, tzinfo=timezone.utc)
        else:
            start = datetime(y, 9, 1, tzinfo=timezone.utc)

        start = start - timedelta(days=start.weekday())  # на понедельник
        weeks_since_start = (now.date() - start.date()).days // 7 + 1
        return ((weeks_since_start - 1) % self.week_cycle) + 1

    # ---------------------------------------------------------------- fetch

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        with self._group_lock:
            group = self._group_number

        params = {"studentGroup": group}
        try:
            response = self._session.get(
                f"{self.base_url}/schedule",
                params=params,
                timeout=self.request_timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Ошибка запроса к API БГУИР: {e}")

        data = response.json()
        base_date = utc_now()

        # 2. Текущая позиция в цикле
        try:
            position_in_cycle = self._get_position_in_cycle()
        except Exception as e:
            logger.warning(
                "[IIS] Не удалось получить current-week (%s). Использую fallback.",
                e,
            )
            position_in_cycle = self._fallback_position_in_cycle(base_date)

        tasks: List[Task] = []

        # 3. Регулярное расписание
        schedules = data.get("schedules", {})
        for day_name, lessons in schedules.items():
            if not isinstance(lessons, list):
                continue
            for lesson in lessons:
                item = IisScheduleItem.from_dict(lesson, day_of_week=day_name)
                task = item.to_task(
                    base_date=base_date,
                    position_in_cycle=position_in_cycle,
                    group_number=group,
                    week_cycle=self.week_cycle,
                    is_exam=False,
                )
                if task is not None:
                    tasks.append(task)

        # 4. Экзамены
        for exam in data.get("exams", []):
            if not isinstance(exam, dict):
                continue
            item = IisScheduleItem.from_dict(exam, day_of_week=None)
            task = item.to_task(
                base_date=base_date,
                position_in_cycle=position_in_cycle,
                week_cycle=self.week_cycle,
                is_exam=True,
            )
            if task is not None:
                tasks.append(task)  

        logger.info(
            "[IIS] Сформировано задач: %d (позиция в цикле: %d/%d)",
            len(tasks),
            position_in_cycle,
            self.week_cycle,
        )
        return tasks

    def push_update(self, task: Task) -> bool:
        raise NotImplementedError(
            "Обновление расписания не поддерживается (только чтение)"
        )

    def delete_task(self, external_id: str) -> bool:
        raise NotImplementedError("Удаление расписания не поддерживается")
