from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
from models.task import Task


class IServiceAdapter(ABC):
    """Унифицированный интерфейс для адаптеров внешних сервисов"""

    @abstractmethod
    def authenticate(self, token: str) -> bool:
        """Аутентификация во внешнем сервисе"""
        pass

    @abstractmethod
    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        """Получение изменений с указанного времени"""
        pass

    @abstractmethod
    def push_update(self, task: Task) -> bool:
        """Отправка обновления задачи во внешний сервис"""
        pass

    @abstractmethod
    def delete_task(self, external_id: str) -> bool:
        """Удаление задачи во внешнем сервисе"""
        pass


class ICacheStorage(ABC):
    """Интерфейс для кэш-хранилища"""

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[Task]:
        pass

    @abstractmethod
    def get_task_by_external_id(
        self, external_id: str, source_type: str
    ) -> Optional[Task]:
        pass

    @abstractmethod
    def save_task(self, task: Task) -> bool:
        pass

    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        pass

    @abstractmethod
    def get_version(self, task_id: str) -> int:
        pass
