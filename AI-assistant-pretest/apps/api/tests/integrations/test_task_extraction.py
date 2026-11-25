from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from app.modules.integrations.integration.adapters.llama_server_client import (
    LlamaServerChatClient,
    LlmUnavailableError,
)
from app.modules.integrations.integration.task_extraction import (
    TaskDraftExtractor,
    TaskExtractFile,
    TaskExtractionError,
    is_supported_pdf,
)
from app.modules.integrations.service import IntegrationService
from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
from app.modules.knowledge.service import KnowledgeService

FIXED_NOW = datetime(2026, 11, 3, 14, 30, tzinfo=timezone(timedelta(hours=3)))


class FakeChatClient:
    def __init__(self, response: str = "{}", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def chat(self, messages, *, max_tokens, temperature):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


def make_extractor(client: FakeChatClient, **kwargs) -> TaskDraftExtractor:
    return TaskDraftExtractor(client=client, **kwargs)


def task_json(**overrides) -> str:
    payload = {
        "title": "Сдать лабораторную по ООП",
        "description": "Загрузить в LMS до вечера",
        "estimated_minutes": 120,
        "priority": 1,
        "deadline": "2026-11-06T23:59:00",
        "workspace_id": "study",
        "project_id": "oop",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def task_drafts_json(*tasks: dict) -> str:
    return json.dumps({"tasks": list(tasks)}, ensure_ascii=False)


def user_text(messages: list[dict]) -> str:
    content = messages[1]["content"]
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text", "") for part in content if part.get("type") == "text")


def test_extracts_task_from_text() -> None:
    client = FakeChatClient("```json\n" + task_json() + "\n```")
    extractor = make_extractor(client)

    drafts = extractor.extract(
        text="Сдать лабу по ООП до пятницы, примерно 2 часа, очень важно",
        now=FIXED_NOW,
    )
    draft = drafts.tasks[0]

    assert draft.title == "Сдать лабораторную по ООП"
    assert draft.estimated_minutes == 120
    assert draft.priority == 1
    assert draft.project_id == "oop"
    assert draft.deadline == datetime(2026, 11, 6, 23, 59)
    assert draft.input_kind == "text"

    messages = client.calls[0]["messages"]
    assert "2026-11-03" in messages[0]["content"]
    assert "вторник" in messages[0]["content"]
    assert "Сдать лабу по ООП" in user_text(messages)


def test_extract_returns_single_task_draft_in_tasks_array() -> None:
    drafts = make_extractor(FakeChatClient(task_json())).extract(text="Сдать отчёт")

    assert len(drafts.tasks) == 1
    assert drafts.tasks[0].title == "Сдать лабораторную по ООП"


def test_returns_several_task_drafts_when_model_proposes_several() -> None:
    """Несколько независимых задач — ответ модели с массивом tasks."""
    client = FakeChatClient(
        task_drafts_json(
            {
                "title": "Сдать лабораторную по ООП",
                "description": "Первые два задания",
                "estimated_minutes": 90,
                "priority": 2,
                "deadline": "2026-11-05T23:59:00",
                "workspace_id": "study",
                "project_id": "oop",
            },
            {
                "title": "Сдать лабораторную по базам данных",
                "description": "Третье задание",
                "estimated_minutes": 150,
                "priority": 1,
                "deadline": "2026-11-07T23:59:00",
                "workspace_id": "study",
                "project_id": "oop",
            },
        )
    )
    drafts = make_extractor(client).extract(text="Подготовить обе лабораторные по ООП")

    assert len(drafts.tasks) == 2
    first, second = drafts.tasks
    assert first.title == "Сдать лабораторную по ООП"
    assert first.estimated_minutes == 90
    assert first.priority == 2
    assert second.title == "Сдать лабораторную по базам данных"
    assert second.estimated_minutes == 150
    assert second.priority == 1
    assert second.deadline == datetime(2026, 11, 7, 23, 59)


def test_empty_tasks_array_is_rejected() -> None:
    extractor = make_extractor(FakeChatClient(json.dumps({"tasks": []})))

    with pytest.raises(TaskExtractionError) as exc_info:
        extractor.extract(text="Задача")

    assert exc_info.value.status_code == 502


def test_extracts_task_from_image_as_data_url() -> None:
    client = FakeChatClient(task_json())
    extractor = make_extractor(client)
    png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"

    drafts = extractor.extract(
        files=[TaskExtractFile(filename="task.png", content_type="image/png", content=png)],
        now=FIXED_NOW,
    )

    assert drafts.tasks[0].input_kind == "image"
    content = client.calls[0]["messages"][1]["content"]
    image_parts = [part for part in content if part["type"] == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_two_images_are_sent_as_separate_model_parts() -> None:
    client = FakeChatClient(task_json())
    extractor = make_extractor(client)
    png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"

    drafts = extractor.extract(
        files=[
            TaskExtractFile(filename="task1.png", content_type="image/png", content=png),
            TaskExtractFile(filename="task2.png", content_type="image/png", content=png),
        ],
        now=FIXED_NOW,
    )

    assert len(drafts.tasks) == 1
    content = client.calls[0]["messages"][1]["content"]
    image_parts = [part for part in content if part["type"] == "image_url"]
    assert len(image_parts) == 2
    assert all(
        part["image_url"]["url"].startswith("data:image/png;base64,")
        for part in image_parts
    )


def test_text_file_is_decoded_from_cp1251() -> None:
    client = FakeChatClient(task_json())
    extractor = make_extractor(client)
    content = "Лабораторная работа по базам данных".encode("cp1251")

    drafts = extractor.extract(
        files=[TaskExtractFile(filename="task.txt", content_type="text/plain", content=content)],
    )

    assert "Лабораторная работа по базам данных" in user_text(
        client.calls[0]["messages"]
    )


def test_multiple_text_files_are_combined_into_one_prompt() -> None:
    client = FakeChatClient(task_json())
    extractor = make_extractor(client)

    drafts = extractor.extract(
        files=[
            TaskExtractFile(filename="lab-oop.txt", content_type="text/plain", content="Лабораторная по ООП".encode("utf-8")),
            TaskExtractFile(filename="lab-math.txt", content_type="text/plain", content="Лабораторная по матану".encode("utf-8")),
        ],
    )

    assert len(drafts.tasks) == 1
    combined = user_text(client.calls[0]["messages"])
    assert "Лабораторная по ООП" in combined
    assert "Лабораторная по матану" in combined


def test_too_many_files_are_rejected() -> None:
    extractor = make_extractor(FakeChatClient(task_json()))
    files = [
        TaskExtractFile(filename=f"file{index}.txt", content_type="text/plain", content="текст".encode("utf-8"))
        for index in range(4)
    ]

    with pytest.raises(TaskExtractionError) as exc_info:
        extractor.extract(files=files)

    assert exc_info.value.status_code == 400
    assert "не более" in str(exc_info.value)


def test_deadline_date_only_becomes_end_of_day() -> None:
    client = FakeChatClient(task_json(deadline="2026-11-09"))
    extractor = make_extractor(client)

    drafts = extractor.extract(text="Сдать отчёт", now=FIXED_NOW)

    assert drafts.tasks[0].deadline == datetime(2026, 11, 9, 23, 59)


def test_invalid_model_values_are_clamped_with_warnings() -> None:
    client = FakeChatClient(
        task_json(
            estimated_minutes=1,
            priority=9,
            deadline="когда-нибудь",
        )
    )
    extractor = make_extractor(client)

    drafts = extractor.extract(text="Задача", now=FIXED_NOW)

    assert drafts.tasks[0].estimated_minutes == 15
    assert drafts.tasks[0].priority == 3
    assert drafts.tasks[0].deadline is None
    assert len(drafts.tasks[0].warnings) == 3


def test_missing_title_falls_back_to_description() -> None:
    client = FakeChatClient(task_json(title="", description="Купить билет на поезд"))
    extractor = make_extractor(client)

    drafts = extractor.extract(text="Купить билет на поезд", now=FIXED_NOW)

    assert drafts.tasks[0].title == "Купить билет на поезд"


def test_missing_title_and_description_is_rejected() -> None:
    client = FakeChatClient(task_json(title="", description=None))
    extractor = make_extractor(client)

    with pytest.raises(TaskExtractionError) as exc_info:
        extractor.extract(text="Непонятное описание", now=FIXED_NOW)

    assert exc_info.value.status_code == 400


def test_unavailable_model_maps_to_503() -> None:
    client = FakeChatClient(error=LlmUnavailableError("llama-server не запущен"))
    extractor = make_extractor(client)

    with pytest.raises(TaskExtractionError) as exc_info:
        extractor.extract(text="Задача", now=FIXED_NOW)

    assert exc_info.value.status_code == 503
    assert "llama-server" in str(exc_info.value)


def test_invalid_json_is_reported_as_bad_gateway() -> None:
    extractor = make_extractor(FakeChatClient("это не JSON"))

    with pytest.raises(TaskExtractionError) as exc_info:
        extractor.extract(text="Задача", now=FIXED_NOW)

    assert exc_info.value.status_code == 502


def test_unsupported_file_type_is_rejected() -> None:
    client = FakeChatClient(task_json())
    extractor = make_extractor(client)

    with pytest.raises(TaskExtractionError) as exc_info:
        extractor.extract(
            files=[
                TaskExtractFile(
                    filename="program.exe",
                    content_type="application/octet-stream",
                    content=b"MZ\x90\x00binary",
                )
            ],
            now=FIXED_NOW,
        )

    assert exc_info.value.status_code == 400


def test_empty_input_is_rejected() -> None:
    extractor = make_extractor(FakeChatClient(task_json()))

    with pytest.raises(TaskExtractionError):
        extractor.extract(now=FIXED_NOW)


def test_oversized_image_is_rejected() -> None:
    client = FakeChatClient(task_json())
    extractor = make_extractor(client, max_image_bytes=10)
    png = b"\x89PNG\r\n\x1a\n" + b"too-large"

    with pytest.raises(TaskExtractionError):
        extractor.extract(
            files=[TaskExtractFile(filename="task.png", content_type="image/png", content=png)],
            now=FIXED_NOW,
        )


def test_pdf_without_extractable_text_is_rejected() -> None:
    extractor = make_extractor(FakeChatClient(task_json()))

    with pytest.raises(TaskExtractionError) as exc_info:
        extractor.extract(
            files=[TaskExtractFile(filename="task.pdf", content_type="application/pdf", content=b"%PDF-1.4 broken")],
            now=FIXED_NOW,
        )

    assert exc_info.value.status_code == 400
    assert "PDF" in str(exc_info.value)
    assert is_supported_pdf("task.pdf")


def test_integration_service_returns_drafts_without_saving_fact(tmp_path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        task_draft_extractor=TaskDraftExtractor(FakeChatClient(task_json())),
    )

    drafts = service.extract_task_draft(text="Сдать лабу по ООП")

    assert drafts.tasks[0].title == "Сдать лабораторную по ООП"
    # Черновики не становятся фактами базы знаний сам по себе.
    assert kb.list_tasks() == []


def test_integration_service_reports_disabled_extractor(tmp_path) -> None:
    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
    )

    with pytest.raises(TaskExtractionError) as exc_info:
        service.extract_task_draft(text="Сдать лабу")

    assert exc_info.value.status_code == 503


class FakeHttpResponse:
    def __init__(self, status_code: int = 200, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_llama_client_sends_json_mode_and_disables_thinking() -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeHttpResponse(
            payload={
                "choices": [
                    {"message": {"content": '{"title": "Задача"}'}}
                ]
            }
        )

    client = LlamaServerChatClient(
        base_url="http://localhost:8080",
        model="qwen3.5-4b",
        request_fn=fake_post,
    )

    content = client.chat(
        [{"role": "user", "content": "Привет"}],
        max_tokens=128,
        temperature=0.1,
    )

    assert content == '{"title": "Задача"}'
    assert calls[0][0] == "http://localhost:8080/v1/chat/completions"
    payload = calls[0][1]["json"]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["model"] == "qwen3.5-4b"


def test_llama_client_does_not_duplicate_v1_in_url() -> None:
    client = LlamaServerChatClient(base_url="http://localhost:8080/v1")

    assert client.endpoint == "http://localhost:8080/v1/chat/completions"


def test_llama_client_maps_connection_error_to_unavailable() -> None:
    def broken_post(url, **kwargs):
        raise requests.ConnectionError("connection refused")

    client = LlamaServerChatClient(request_fn=broken_post)

    with pytest.raises(LlmUnavailableError):
        client.chat([{"role": "user", "content": "Привет"}], max_tokens=10, temperature=0)
