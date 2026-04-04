from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.settings import settings
from app.modules.integrations.providers import default_providers
from app.modules.integrations.service import IntegrationService
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.intelligence.service import SchedulerService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.models import EventCreate, TaskCreate


class Container:
    def __init__(self) -> None:
        self.knowledge_repository = InMemoryKnowledgeRepository()

        self.scheduler = GreedyScheduler(
            slot_minutes=settings.schedule_slot_minutes,
            horizon_days=settings.schedule_horizon_days,
            wake_start_hour=settings.wake_start_hour,
            wake_end_hour=settings.wake_end_hour,
        )

        self.scheduler_service = SchedulerService(
            repository=self.knowledge_repository,
            scheduler=self.scheduler,
        )

        self.integration_service = IntegrationService(
            providers=default_providers(),
        )

        self._seed_demo_data()

    def _seed_demo_data(self) -> None:
        if self.knowledge_repository.list_tasks():
            return

        now = datetime.now(timezone.utc)

        self.knowledge_repository.create_event(
            EventCreate(
                title="Лекции",
                start_at=now.replace(hour=10, minute=0, second=0, microsecond=0),
                end_at=now.replace(hour=13, minute=0, second=0, microsecond=0),
                source="bsuir-lms",
            )
        )

        self.knowledge_repository.create_task(
            TaskCreate(
                title="Лаба по ООП",
                description="Сделать и загрузить первую лабораторную",
                estimated_minutes=120,
                priority=1,
                deadline=now + timedelta(days=1),
                workspace_id="study",
                project_id="oop",
            )
        )

        self.knowledge_repository.create_task(
            TaskCreate(
                title="Подготовка к тесту по матану",
                estimated_minutes=90,
                priority=2,
                deadline=now + timedelta(days=2),
                workspace_id="study",
                project_id="math",
            )
        )


container = Container()
