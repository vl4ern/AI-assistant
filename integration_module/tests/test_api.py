import pytest
import json
from unittest.mock import MagicMock
from integration.api import SyncAPIHandler
from models.task import SourceType


@pytest.fixture
def mock_handler():
    """Создает экземпляр хендлера с фейковым scheduler."""
    # Пропускаем __init__ базового класса, чтобы не открывать сокеты
    handler = SyncAPIHandler.__new__(SyncAPIHandler)

    # Фейковый scheduler
    handler.scheduler = MagicMock()
    handler.scheduler.adapters = {"IIS": MagicMock(), "google_calendar": MagicMock()}
    handler.scheduler.adapters["IIS"].group_number = "421701"

    # Фейковые методы для чтения тела запроса
    handler._read_json = MagicMock()

    return handler


def test_api_create_task_payload(mock_handler):
    """Тест: создание задачи через API парсит JSON правильно."""
    mock_handler._read_json.return_value = {
        "title": "Встреча",
        "due_date": "2026-10-01T10:00:00Z",
        "source_type": "google_calendar",
        "duration_minutes": 60,
    }

    task = mock_handler._task_from_payload(mock_handler._read_json(), task_id=None)

    assert task.title == "Встреча"
    assert task.source_type == SourceType.GOOGLE_CALENDAR
    assert task.duration_minutes == 60
    assert task.due_date.tzinfo is not None


def test_api_change_group_payload(mock_handler):
    """Тест: эндпоинт смены группы вызывает метод адаптера."""
    mock_handler._read_json.return_value = {"group": "421702"}

    # Вызываем обработчик напрямую (он обратится к адаптеру)
    # Нам нужно замокать _json, чтобы он не пытался писать в wfile
    mock_handler._json = MagicMock()

    mock_handler._set_iis_group()

    # Проверяем, что метод set_group_number был вызван
    mock_handler.scheduler.adapters["IIS"].set_group_number.assert_called_once_with(
        "421702"
    )
    # Проверяем, что вернулся успешный ответ
    mock_handler._json.assert_called_once()
    args, _ = mock_handler._json.call_args
    assert args[0] == 200
    assert args[1]["changed"] is True
