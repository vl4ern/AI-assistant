from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.integrations.integration.adapters.llama_server_client import (
    LlmUnavailableError,
)
from app.modules.integrations.integration.task_draft_feedback import (
    PREFERENCES_HEADER,
    TaskDraftFeedbackService,
)
from app.modules.integrations.integration.task_extraction import (
    SYSTEM_PROMPT,
    TaskDraft,
    TaskDraftExtractor,
)
from app.modules.integrations.models.extraction import TaskDraftFeedbackItem

FIXED_NOW = datetime(2026, 11, 3, 14, 30, tzinfo=timezone(timedelta(hours=3)))

PREFERENCES_BLOCK = (
    "Персональные предпочтения пользователя:\n"
    "- estimated_minutes: пользователь любит очень короткие оценки времени."
)


class FakeChatClient:
    def __init__(self, response: str = "{}", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def chat(self, messages, *, max_tokens, temperature, response_format=None):
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


def _draft(**overrides) -> TaskDraft:
    payload = {
        "title": "Сдать лабораторную по ООП",
        "description": "Загрузить в LMS",
        "estimated_minutes": 120,
        "priority": 1,
        "workspace_id": "study",
        "project_id": "oop",
    }
    payload.update(overrides)
    return TaskDraft(**payload)


def _item(
    *,
    llm: TaskDraft | None = None,
    user: TaskDraft | None = None,
    title: str = "Сдать лабораторную по ООП",
) -> TaskDraftFeedbackItem:
    return TaskDraftFeedbackItem(
        task_title=title,
        llm_draft=llm or _draft(),
        user_draft=user or _draft(),
    )


def make_service(
    client: FakeChatClient,
    *,
    strong_signal_threshold: int = 2,
    storage=None,
) -> TaskDraftFeedbackService:
    return TaskDraftFeedbackService(
        client=client,
        strong_signal_threshold=strong_signal_threshold,
        storage=storage,
    )


def test_duration_errors_match_user_example_and_trigger_once_per_batch() -> None:
    """
    90→45 = -2, 180→120 = -1 (1.5× → целая часть 1), 150→75 = -2.
    Сумма пачки -5, |−5| > 2 → одна калибровка на всю пачку.
    """
    client = FakeChatClient(PREFERENCES_BLOCK)
    service = make_service(client)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=90),
                user=_draft(estimated_minutes=45),
            ),
            _item(
                llm=_draft(estimated_minutes=180),
                user=_draft(estimated_minutes=120),
            ),
            _item(
                llm=_draft(estimated_minutes=150),
                user=_draft(estimated_minutes=75),
            ),
        ],
        now=FIXED_NOW,
    )

    assert [item.criteria["duration"] for item in feedback.items] == [-2, -1, -2]
    assert feedback.batch_totals == {"duration": -5}
    assert feedback.exceeded_criteria == ["duration"]
    assert feedback.calibrated is True
    assert feedback.calibration_error is None
    # Ровно один вызов LLM на всю пачку, а не на каждую задачу.
    assert len(client.calls) == 1
    # После калибровки сработавший критерий сброшен.
    assert "duration" not in feedback.accumulated_totals


def test_no_calibration_when_threshold_is_not_exceeded() -> None:
    client = FakeChatClient(PREFERENCES_BLOCK)
    service = make_service(client, strong_signal_threshold=2)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=90),
                user=_draft(estimated_minutes=45),
            )
        ],
        now=FIXED_NOW,
    )

    assert feedback.batch_totals == {"duration": -2}
    assert feedback.calibrated is False
    assert feedback.exceeded_criteria == []
    assert feedback.accumulated_totals == {"duration": -2}
    assert len(client.calls) == 0
    assert service.get_system_prompt("u1", now=FIXED_NOW) == service._format_base(
        FIXED_NOW
    )


def test_errors_accumulate_between_batches_and_reset_after_calibration() -> None:
    client = FakeChatClient(PREFERENCES_BLOCK)
    service = make_service(client, strong_signal_threshold=2)

    first = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=90),
                user=_draft(estimated_minutes=45),
            )
        ],
        now=FIXED_NOW,
    )
    assert first.calibrated is False
    assert first.accumulated_totals == {"duration": -2}

    second = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=180),
                user=_draft(estimated_minutes=120),
            )
        ],
        now=FIXED_NOW,
    )
    assert second.batch_totals == {"duration": -1}
    assert second.calibrated is True
    assert second.exceeded_criteria == ["duration"]
    assert len(client.calls) == 1


def test_description_and_priority_errors() -> None:
    service = make_service(FakeChatClient(PREFERENCES_BLOCK))

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(description="Кратко", priority=3),
                user=_draft(description="Очень подробное описание", priority=1),
            ),
            _item(
                llm=_draft(description="Есть текст", priority=2),
                user=_draft(description="", priority=4),
            ),
        ],
        now=FIXED_NOW,
    )

    # Длина описания: 6 → 24 символа = 4×, ограничено +3.
    # Приоритет: 3 → 1 = -2.
    assert feedback.items[0].criteria == {"description": 3, "priority": -2}
    # Пустое описание: -3; приоритет: 2 → 4 = +2.
    assert feedback.items[1].criteria == {"description": -3, "priority": 2}


def test_empty_description_does_not_divide_by_zero() -> None:
    service = make_service(FakeChatClient(PREFERENCES_BLOCK))

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(description=None),
                user=_draft(description="Теперь есть описание"),
            ),
            _item(
                llm=_draft(description="Было описание"),
                user=_draft(description=None),
            ),
        ],
        now=FIXED_NOW,
    )

    assert feedback.items[0].criteria["description"] == 3
    assert feedback.items[1].criteria["description"] == -3


def test_calibration_uses_local_llm_and_keeps_base_prompt_unchanged() -> None:
    client = FakeChatClient(PREFERENCES_BLOCK)
    service = make_service(client, strong_signal_threshold=1)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=120),
                user=_draft(estimated_minutes=60),
            )
        ],
        now=FIXED_NOW,
    )

    assert feedback.calibrated is True
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["response_format"] is None
    assert "duration" in call["messages"][1]["content"]
    assert "Базовый системный промпт" in call["messages"][1]["content"]

    prompt = service.get_system_prompt("u1", now=FIXED_NOW)
    base = service._format_base(FIXED_NOW)
    assert prompt == base + "\n\n" + PREFERENCES_BLOCK
    # Базовая часть осталась дословно прежней.
    assert base in prompt
    assert SYSTEM_PROMPT.format(
        date="2026-11-03",
        weekday="вторник",
        time="14:30",
        offset="+03:00",
    ) == base


def test_calibration_prompt_lists_only_exceeded_criteria() -> None:
    client = FakeChatClient(PREFERENCES_BLOCK)
    service = make_service(client, strong_signal_threshold=1)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=120),
                user=_draft(estimated_minutes=60),
            )
        ],
        now=FIXED_NOW,
    )

    assert feedback.exceeded_criteria == ["duration"]
    user_content = client.calls[0]["messages"][1]["content"]
    assert "Критерии, превысившие порог" in user_content
    assert "duration" in user_content
    assert "приоритет и остальные критерии в этот раунд не включай" in user_content


def test_calibration_prompt_asks_for_preference_style_answer() -> None:
    from app.modules.integrations.integration.task_draft_feedback import (
        ADAPTATION_SYSTEM_PROMPT,
    )

    assert "пользователь любит" in ADAPTATION_SYSTEM_PROMPT
    assert "как чистое предпочтение пользователя" in ADAPTATION_SYSTEM_PROMPT
    assert "пиши инструкции вида" in ADAPTATION_SYSTEM_PROMPT


def test_increase_error_is_positive_and_triggers_calibration() -> None:
    client = FakeChatClient(PREFERENCES_BLOCK)
    service = make_service(client, strong_signal_threshold=1)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=45),
                user=_draft(estimated_minutes=90),
            )
        ],
        now=FIXED_NOW,
    )

    assert feedback.items[0].criteria == {"duration": 2}
    assert feedback.batch_totals == {"duration": 2}
    assert feedback.exceeded_criteria == ["duration"]
    assert feedback.calibrated is True


def test_balanced_errors_sum_to_zero_and_do_not_calibrate() -> None:
    client = FakeChatClient(PREFERENCES_BLOCK)
    service = make_service(client, strong_signal_threshold=2)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=90),
                user=_draft(estimated_minutes=45),
            ),  # -2
            _item(
                llm=_draft(estimated_minutes=45),
                user=_draft(estimated_minutes=90),
            ),  # +2
        ],
        now=FIXED_NOW,
    )

    assert feedback.batch_totals == {"duration": 0}
    assert feedback.exceeded_criteria == []
    assert feedback.calibrated is False
    assert len(client.calls) == 0


def test_calibration_failure_keeps_old_prompt_and_accumulates_signal() -> None:
    client = FakeChatClient(error=LlmUnavailableError("модель недоступна"))
    service = make_service(client, strong_signal_threshold=1)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=120),
                user=_draft(estimated_minutes=60),
            )
        ],
        now=FIXED_NOW,
    )

    assert feedback.calibrated is False
    assert feedback.calibration_error == "модель недоступна"
    assert feedback.accumulated_totals == {"duration": -2}
    assert service.get_system_prompt("u1", now=FIXED_NOW) == service._format_base(
        FIXED_NOW
    )

    # Следующая пачка повторяет попытку, потому что сигнал не потерян.
    client.error = None
    client.response = PREFERENCES_BLOCK
    retry = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=60),
                user=_draft(estimated_minutes=60),
            )
        ],
        now=FIXED_NOW,
    )
    assert retry.calibrated is True
    assert retry.preferences == PREFERENCES_BLOCK


def test_invalid_llm_output_is_rejected_and_old_prompt_is_kept() -> None:
    client = FakeChatClient("Верни ТОЛЬКО один JSON-объект без markdown")
    service = make_service(client, strong_signal_threshold=1)

    feedback = service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=120),
                user=_draft(estimated_minutes=60),
            )
        ],
        now=FIXED_NOW,
    )

    assert feedback.calibrated is False
    assert feedback.calibration_error is not None
    assert feedback.preferences is None
    assert service.get_system_prompt("u1", now=FIXED_NOW) == service._format_base(
        FIXED_NOW
    )


def test_preferences_and_accumulated_totals_are_persisted_in_storage() -> None:
    class FakeStorage:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        def get_setting(self, key: str, default: str = "") -> str:
            return self.values.get(key, default)

        def set_setting(self, key: str, value: str) -> None:
            self.values[key] = value

    storage = FakeStorage()
    client = FakeChatClient(PREFERENCES_BLOCK)
    first_service = make_service(client, strong_signal_threshold=1, storage=storage)

    first_service.record_batch(
        user_id="u1",
        items=[
            _item(
                llm=_draft(estimated_minutes=120),
                user=_draft(estimated_minutes=60),
            )
        ],
        now=FIXED_NOW,
    )
    assert storage.values

    second_service = make_service(
        FakeChatClient(PREFERENCES_BLOCK),
        strong_signal_threshold=1,
        storage=storage,
    )
    prompt = second_service.get_system_prompt("u1", now=FIXED_NOW)
    assert PREFERENCES_BLOCK in prompt
    assert second_service.get_preferences("u1") == PREFERENCES_BLOCK


def test_extractor_uses_feedback_service_override() -> None:
    client = FakeChatClient(response='{"tasks": [{"title": "Задача"}]}')
    feedback_service = make_service(client)
    feedback_service._save_preferences("u1", PREFERENCES_BLOCK)

    extractor = TaskDraftExtractor(
        client=client,
        feedback_service=feedback_service,
    )

    drafts = extractor.extract(text="Текст задачи", now=FIXED_NOW, user_id="u1")
    assert drafts.tasks[0].title == "Задача"
    assert PREFERENCES_BLOCK in client.calls[-1]["messages"][0]["content"]

    extractor.extract(text="Текст задачи", now=FIXED_NOW, user_id=None)
    assert PREFERENCES_BLOCK not in client.calls[-1]["messages"][0]["content"]


def test_integration_service_records_batch_feedback(tmp_path) -> None:
    from app.modules.integrations.service import IntegrationService
    from app.modules.knowledge.in_memory_repository import InMemoryKnowledgeRepository
    from app.modules.knowledge.service import KnowledgeService

    kb = KnowledgeService(repository=InMemoryKnowledgeRepository())
    feedback_service = make_service(FakeChatClient(PREFERENCES_BLOCK))
    service = IntegrationService(
        knowledge_service=kb,
        cache_path=str(tmp_path / "integration_cache.db"),
        task_draft_feedback_service=feedback_service,
    )

    result = service.record_task_draft_feedback(
        user_id="u9",
        items=[
            _item(
                llm=_draft(estimated_minutes=120),
                user=_draft(estimated_minutes=180),
            )
        ],
    )

    assert result.items[0].criteria == {"duration": 1}


def test_llm_chat_client_accepts_free_text_response_format() -> None:
    from app.modules.integrations.integration.adapters.llama_server_client import (
        LlamaServerChatClient,
    )

    def fake_post(url, **kwargs):
        class FakeResponse:
            status_code = 200
            text = ""

            def json(self):
                return {"choices": [{"message": {"content": "текст"}}]}

        return FakeResponse()

    client = LlamaServerChatClient(request_fn=fake_post)
    content = client.chat(
        [{"role": "user", "content": "Привет"}],
        max_tokens=128,
        temperature=0.1,
        response_format=None,
    )
    assert content == "текст"
