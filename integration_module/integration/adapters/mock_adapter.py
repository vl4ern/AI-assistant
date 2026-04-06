import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from models.task import Task, SourceType, TaskStatus
from integration.interfaces import IServiceAdapter


class MockAdapter(IServiceAdapter):
    """Тестовый адаптер, имитирующий внешний API"""

    def __init__(self):
        self.tasks: List[Task] = []
        self.authenticated = False
        self._init_mock_data()

    def _init_mock_data(self):
        """Создание тестовых задач"""
        for i in range(5):
            task = Task(
                id=str(uuid.uuid4()),
                external_id=f"mock_{i}",
                source_type=SourceType.MANUAL,
                title=f"Тестовая задача {i}",
                description=f"Описание задачи {i}",
                due_date=datetime.now() + timedelta(days=i),
                priority=(i % 4) + 1,
                status=TaskStatus.PENDING,
            )
            self.tasks.append(task)

    def authenticate(self, token: str) -> bool:
        self.authenticated = token == "valid_token"
        return self.authenticated

    def fetch_changes(self, since: Optional[datetime] = None) -> List[Task]:
        if not self.authenticated:
            raise Exception("Not authenticated")

        if since is None:
            return self.tasks

        # Возвращаем только задачи, изменённые после since
        return [t for t in self.tasks if t.last_modified > since]

    def push_update(self, task: Task) -> bool:
        if not self.authenticated:
            return False

        # Обновляем или добавляем задачу
        for i, existing in enumerate(self.tasks):
            if existing.external_id == task.external_id:
                self.tasks[i] = task
                return True

        self.tasks.append(task)
        return True

    def delete_task(self, external_id: str) -> bool:
        self.tasks = [t for t in self.tasks if t.external_id != external_id]
        return True
