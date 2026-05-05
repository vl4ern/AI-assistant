from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.settings import settings
from app.modules.integrations.providers import default_providers
from app.modules.integrations.service import IntegrationService
from app.modules.intelligence.ml_scoring import MLScoringService
from app.modules.intelligence.scheduler import GreedyScheduler
from app.modules.intelligence.service import SchedulerService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.models import EventCreate, TaskCreate
from app.modules.knowledge.postgres_repository import PostgresKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


class Container:
    def __init__(self) -> None:
        try:
            if psycopg is None:
                raise RuntimeError("psycopg is not installed")

            self.knowledge_repository = PostgresKnowledgeRepository(
                settings.database_url,
                auto_init_schema=settings.postgres_auto_init_schema,
            )
        except (RuntimeError, psycopg.OperationalError if psycopg is not None else Exception):
            # Локальный fallback, если PostgreSQL недоступен.
            self.knowledge_repository = InMemoryKnowledgeRepository()

        self.knowledge_service = KnowledgeService(
            repository=self.knowledge_repository,
        )

        self.scheduler = GreedyScheduler(
            slot_minutes=settings.schedule_slot_minutes,
            horizon_days=settings.schedule_horizon_days,
            wake_start_hour=settings.wake_start_hour,
            wake_end_hour=settings.wake_end_hour,
        )

        self.scoring_service = MLScoringService(
            wake_start_hour=settings.wake_start_hour,
            wake_end_hour=settings.wake_end_hour,
            horizon_days=settings.schedule_horizon_days,
            retrain_batch_size=settings.ml_retrain_batch_size,
            overdue_bonus=settings.ml_overdue_bonus,
        )

        self.scheduler_service = SchedulerService(
            repository=self.knowledge_repository,
            scheduler=self.scheduler,
            scoring_service=self.scoring_service,
        )

        self.integration_service = IntegrationService(
            providers=default_providers(),
        )

        self._seed_demo_data()

    def _seed_demo_data(self) -> None:
        if self.knowledge_service.list_tasks():
            return

        now = datetime.now(timezone.utc)

        self.knowledge_service.create_event(
            EventCreate(
                title="Лекции",
                start_at=now.replace(hour=10, minute=0, second=0, microsecond=0),
                end_at=now.replace(hour=13, minute=0, second=0, microsecond=0),
                source="bsuir-lms",
            )
        )

        self.knowledge_service.create_task(
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

        self.knowledge_service.create_task(
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
