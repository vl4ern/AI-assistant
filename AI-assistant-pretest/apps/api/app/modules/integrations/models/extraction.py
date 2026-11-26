from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TaskDraft(BaseModel):
    """
    Черновик задачи, распознанный локальной моделью.

    Это не факт базы знаний: черновик возвращается пользователю для
    проверки и сохраняется только явным вызовом POST /v1/tasks.
    """

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    estimated_minutes: int = Field(default=60, ge=15, le=24 * 60)
    priority: int = Field(default=3, ge=1, le=4)
    deadline: datetime | None = None
    workspace_id: str = "study"
    project_id: str | None = None
    input_kind: Literal["text", "image"] = "text"
    warnings: list[str] = Field(default_factory=list)


class TaskDrafts(BaseModel):
    """
    Набор черновиков задач, распознанных локальной моделью.

    Мультизадачный ввод (несколько задач в одном ответе — например, несколько
    лабораторных) модель возвращает массивом: один черновик или несколько.
    """

    tasks: list[TaskDraft] = Field(default_factory=list)


class TaskDraftFeedbackItem(BaseModel):
    """
    Одна пара «что предложила модель / что оставил пользователь».

    `user_draft` — версия, которую пользователь принял или скорректировал;
    `llm_draft` — версия, которую предложила локальная модель.
    """

    task_title: str = Field(min_length=1, max_length=200)
    user_draft: TaskDraft
    llm_draft: TaskDraft


class TaskDraftFeedbackCreate(BaseModel):
    """
    Запрос на запись обратной связи по всей пачке черновиков.

    Обратная связь отправляется один раз — после того, как пользователь
    добавил последнюю задачу из пачки, а не после каждой отдельной задачи.
    По разнице между `llm_draft` и `user_draft` сервис считает ошибки модели
    по критериям (длительность, описание, приоритет), суммирует их по пачке
    и при превышении порога перекалибровывает персональный блок предпочтений.
    """

    items: list[TaskDraftFeedbackItem] = Field(min_length=1, max_length=100)


class TaskDraftFeedbackItemResult(BaseModel):
    """Ошибки модели по одной задаче из пачки."""

    task_title: str = Field(..., max_length=200)
    criteria: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Критерий -> ошибка модели (целое число в диапазоне -3..3). "
            "Нулевые значения не включаются."
        ),
    )


class TaskDraftFeedback(BaseModel):
    """
    Результат обработки пачки обратной связи.

    `batch_totals` — сумма ошибок только по этой пачке; `accumulated_totals`
    — накопленная сумма после её применения (без критериев, которые только
    что были перекалиброваны). `calibrated` показывает, обновилась ли
    персональная настройка промпта.
    """

    user_id: str = Field(..., description="Кто дал обратную связь (user.id)")
    items: list[TaskDraftFeedbackItemResult] = Field(default_factory=list)
    batch_totals: dict[str, int] = Field(default_factory=dict)
    accumulated_totals: dict[str, int] = Field(default_factory=dict)
    exceeded_criteria: list[str] = Field(default_factory=list)
    calibrated: bool = False
    preferences: str | None = Field(
        default=None,
        description="Актуальный блок персональных предпочтений (если есть).",
    )
    calibration_error: str | None = Field(
        default=None,
        description="Почему калибровка не удалась (если была попытка и ошибка).",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskDraftSystemPrompt(BaseModel):
    """
    Системный промпт, которым пользуется пользователь для распознавания
    задач через локальную LLM (базовый или адаптированный под обратную
    связь этого пользователя).
    """

    prompt: str = Field(..., description="Текст системного промпта.")
