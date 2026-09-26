from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.modules.auth.models import LoginRequest, RegisterRequest
from app.modules.auth.service import AuthService
from app.modules.integrations.integration.interfaces import IServiceAdapter
from app.modules.integrations.models.task import SourceType, Task
from app.modules.integrations.service import IntegrationService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.models import EventCreate, TaskCreate
from app.modules.knowledge.service import KnowledgeService


def make_auth_service() -> tuple[AuthService, KnowledgeService]:
    repository = InMemoryKnowledgeRepository()
    return AuthService(repository=repository, secret="test-secret"), KnowledgeService(repository)


def test_register_returns_token_and_user() -> None:
    auth, _ = make_auth_service()

    response = auth.register(RegisterRequest(username="student", password="secret123"))

    assert response.user.username == "student"
    assert auth.verify_token(response.token) is not None


def test_register_rejects_duplicate_username() -> None:
    auth, _ = make_auth_service()
    auth.register(RegisterRequest(username="student", password="secret123"))

    with pytest.raises(ValueError):
        auth.register(RegisterRequest(username="student", password="other456"))


def test_login_with_wrong_password_fails() -> None:
    auth, _ = make_auth_service()
    auth.register(RegisterRequest(username="student", password="secret123"))

    with pytest.raises(ValueError):
        auth.login(LoginRequest(username="student", password="wrong"))


def test_verify_token_rejects_tampered_token() -> None:
    auth, _ = make_auth_service()
    response = auth.register(RegisterRequest(username="student", password="secret123"))

    tampered = response.token[:-4] + "beef"
    assert auth.verify_token(tampered) is None
    assert auth.verify_token("nonsense") is None


def test_tasks_are_isolated_between_users() -> None:
    auth, kb = make_auth_service()
    first = auth.register(RegisterRequest(username="first", password="secret123"))
    second = auth.register(RegisterRequest(username="second", password="secret456"))

    kb.create_task(TaskCreate(title="Задача первого", user_id=first.user.id))
    kb.create_task(TaskCreate(title="Задача второго", user_id=second.user.id))
    kb.create_task(TaskCreate(title="Общая задача", user_id="shared"))

    first_tasks = {task.title for task in kb.list_tasks(first.user.id)}
    second_tasks = {task.title for task in kb.list_tasks(second.user.id)}

    assert first_tasks == {"Задача первого", "Общая задача"}
    assert second_tasks == {"Задача второго", "Общая задача"}


def test_events_are_isolated_between_users() -> None:
    auth, kb = make_auth_service()
    first = auth.register(RegisterRequest(username="first", password="secret123"))
    second = auth.register(RegisterRequest(username="second", password="secret456"))

    kb.create_event(
        EventCreate(
            title="Событие первого",
            start_at=datetime.now(),
            end_at=datetime.now() + timedelta(hours=1),
            user_id=first.user.id,
        )
    )

    assert len(kb.list_events(first.user.id)) == 1
    assert kb.list_events(second.user.id) == []


def test_list_lessons_returns_parsed_schedule(tmp_path: Path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
    )

    class FakeIisAdapter(IServiceAdapter):
        def authenticate(self, token=None):
            return True

        def fetch_changes(self, since=None):
            # Фиксированное время занятия (10:00 завтра), чтобы пара
            # не пересекала полночь при вечернем запуске тестов.
            tomorrow = (datetime.now() + timedelta(days=1)).date()
            start = datetime.combine(tomorrow, datetime.strptime("10:00", "%H:%M").time())
            return [
                Task(
                    id="lesson-1",
                    external_id="iis-lesson-1",
                    source_type=SourceType.IIS,
                    title="ООП",
                    description=(
                        "📘 Объектно-ориентированное программирование\n"
                        "День недели: Вторник\n"
                        "Тип: ЛК\n"
                        "Аудитория: 123-1\n"
                        "Преподаватель: Иванов И. И.\n"
                        "Недели: 1, 2, 3\n"
                    ),
                    due_date=start,
                    duration_minutes=90,
                )
            ]

        def push_update(self, task):
            return True

        def delete_task(self, external_id):
            return True

    service._scheduler.register_adapter("IIS", FakeIisAdapter(), sync_interval=3600)
    service.sync_all()

    lessons = service.list_lessons()

    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.subject == "ООП"
    assert lesson.day_of_week == "Вторник"
    assert lesson.lesson_type == "ЛК"
    assert lesson.teacher == "Иванов И. И."
    assert lesson.auditory == "123-1"
    assert lesson.subject_full_name == "Объектно-ориентированное программирование"
    assert lesson.end_time > lesson.start_time
