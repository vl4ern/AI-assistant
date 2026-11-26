from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Protocol

from app.modules.integrations.integration.adapters.llama_server_client import (
    LlmChatClient,
    LlmClientError,
    LlmUnavailableError,
)
from app.modules.integrations.integration.task_extraction import (
    RU_WEEKDAYS,
    SYSTEM_PROMPT,
)
from app.modules.integrations.models.extraction import (
    TaskDraft,
    TaskDraftFeedback,
    TaskDraftFeedbackItem,
    TaskDraftFeedbackItemResult,
)

logger = logging.getLogger(__name__)

# Три параметра, по которым сравниваются черновик модели и черновик
# пользователя. Ошибка по каждому параметру — целое число в [-3, 3].
CRITERION_DURATION = "duration"
CRITERION_DESCRIPTION = "description"
CRITERION_PRIORITY = "priority"

MIN_ERROR_BOUND = -3
MAX_ERROR_BOUND = 3

# Порог суммарной ошибки по критерию. Калибровка запускается только если
# |сумма| строго больше порога.
STRONG_SIGNAL_THRESHOLD = 2

ADAPTATION_MAX_TOKENS = 512
ADAPTATION_TEMPERATURE = 0.2

PREFERENCES_HEADER = "Персональные предпочтения пользователя:"
PREFERENCES_STORAGE_PREFIX = "task_draft_feedback:preferences:"
ACCUMULATED_STORAGE_PREFIX = "task_draft_feedback:accumulated:"
MAX_PREFERENCES_CHARS = 3000
MAX_EXAMPLES_IN_PROMPT = 20

ADAPTATION_SYSTEM_PROMPT = """\
Ты — редактор персональных предпочтений пользователя для системы, которая
превращает текст и файлы в черновики задач.

Твоя задача — обновить ТОЛЬКО блок «Персональные предпочтения пользователя»
на основе накопленной обратной связи. Базовый системный промпт и правила
извлечения задач менять нельзя.

Что означает обратная связь:
- duration: ошибка = знак × целая часть того, во сколько раз пользователь
  изменил оценку длительности относительно модели. Отрицательная ошибка —
  пользователь уменьшает длительность (модель завышает время); положительная —
  пользователь увеличивает длительность (модель занижает время).
- description: ошибка = знак × целая часть того, во сколько раз пользователь
  изменил длину описания. Отрицательная — пользователь сокращает описания;
  положительная — пользователь делает их подробнее.
- priority: ошибка = priority_пользователя − priority_модели. Отрицательная —
  пользователь повышает важность (сдвигает приоритет к 1); положительная —
  понижает важность (сдвигает приоритет к 4).

Чем больше модуль суммарной ошибки, тем сильнее предпочтение. Используй
градации в зависимости от модуля: 1 — «чуть более», 2 — «умеренно более»,
3 — «очень»/«огромные». Например: «пользователь любит чуть более подробные
описания», «пользователь любит очень подробные описания», «пользователь
любит огромные описания».

Правила ответа:
1. Верни только текст блока предпочтений на русском языке, без JSON,
   markdown-ограждений и пояснений.
2. Первая строка: «Персональные предпочтения пользователя:».
3. Дальше 1–5 коротких пунктов с конкретными указаниями для модели.
4. Пиши как чистое предпочтение пользователя, а не как инструкцию к себе:
   «пользователь любит чуть более подробные описания», «пользователь любит
   очень подробные описания», «пользователь любит огромные описания». Не
   пиши инструкции вида «Старайся ...».
5. Сохрани прежние предпочтения, если новые данные им не противоречат.
6. Не повторяй базовый промпт, его правила и JSON-схему.
7. Не включай критерии, которые не превысили порог, и не добавляй
   предпочтения вне накопленного сигнала.
"""


class FeedbackSettingsStorage(Protocol):
    """Минимальное key-value-хранилище для персональных настроек."""

    def get_setting(self, key: str, default: str = "") -> str:
        ...

    def set_setting(self, key: str, value: str) -> None:
        ...


def _format_signed(value: int) -> str:
    return f"{value:+d}"


def _direction_phrase(criterion: str, total: int) -> str:
    if criterion == CRITERION_DURATION:
        if total < 0:
            return "пользователь хочет более короткие оценки времени (модель завышает длительность)"
        return "пользователь хочет более длинные оценки времени (модель занижает длительность)"
    if criterion == CRITERION_DESCRIPTION:
        if total < 0:
            return "пользователь хочет более краткие описания (модель пишет слишком подробно)"
        return "пользователь хочет более подробные описания (модель пишет слишком кратко)"
    if total < 0:
        return "пользователь повышает важность задач (модель недооценивает приоритет)"
    return "пользователь понижает важность задач (модель переоценивает приоритет)"


class TaskDraftFeedbackService:
    """
    Считает ошибки модели по пачке черновиков и адаптирует персональный
    блок системного промпта.

    Алгоритм ошибки по одному черновику:
    - duration: знак = в какую сторону пользователь изменил время;
      модуль = целая часть отношения большего значения к меньшему.
      Пример: 90 → 45 даёт -2, 180 → 120 даёт -1, 150 → 75 даёт -2.
    - description: то же самое, но сравниваются длины описаний в символах.
      Если одна из сторон пустая, ошибка ограничивается ±3.
    - priority: обычная разница priority_пользователя − priority_модели
      (приоритеты 1..4, поэтому разница уже лежит в [-3, 3]).

    Ошибки суммируются по пользователю. Когда |сумма| по критерию становится
    строго больше `strong_signal_threshold`, локальная LLM получает
    накопленный сигнал и текущий блок предпочтений, после чего возвращает
    обновлённый блок. Базовый промпт при этом не изменяется: он всегда
    остаётся `SYSTEM_PROMPT`, а блок предпочтений просто дописывается в конец.
    """

    def __init__(
        self,
        client: LlmChatClient,
        *,
        base_system_prompt: str = SYSTEM_PROMPT,
        strong_signal_threshold: int = STRONG_SIGNAL_THRESHOLD,
        adaptation_max_tokens: int = ADAPTATION_MAX_TOKENS,
        adaptation_temperature: float = ADAPTATION_TEMPERATURE,
        storage: FeedbackSettingsStorage | None = None,
    ) -> None:
        self._client = client
        self._base_system_prompt = base_system_prompt
        self._strong_signal_threshold = strong_signal_threshold
        self._adaptation_max_tokens = adaptation_max_tokens
        self._adaptation_temperature = adaptation_temperature
        self._storage = storage

        # user_id -> актуальный блок персональных предпочтений.
        self._preferences: dict[str, str] = {}
        # user_id -> накопленные суммы ошибок по критериям.
        self._accumulated: dict[str, dict[str, int]] = {}
        self._loaded_users: set[str] = set()

    def get_system_prompt(self, user_id: str | None, now: datetime) -> str:
        """
        Возвращает базовый промпт, к которому при наличии дописан
        персональный блок предпочтений. Базовая часть не меняется.
        """
        base = self._format_base(now)
        if not user_id:
            return base
        preferences = self._get_preferences(user_id)
        if not preferences:
            return base
        return f"{base}\n\n{preferences}"

    def get_preferences(self, user_id: str) -> str | None:
        """Возвращает текущий персональный блок пользователя (если есть)."""
        return self._get_preferences(user_id)

    def record_batch(
        self,
        *,
        user_id: str,
        items: list[TaskDraftFeedbackItem],
        now: datetime,
    ) -> TaskDraftFeedback:
        """
        Обрабатывает всю пачку добавленных задач за один вызов.

        Сначала считаются ошибки по каждому черновику, затем их сумма
        добавляется к накопленной сумме пользователя. Если по какому-то
        критерию |сумма| > порога, вызывается локальная LLM для обновления
        блока предпочтений. После успешной калибровки сбрасываются только
        те критерии, по которым сработал порог; остальные продолжают
        накапливаться.
        """
        if not items:
            raise ValueError("Нужна хотя бы одна пара черновиков для обратной связи.")

        item_results: list[TaskDraftFeedbackItemResult] = []
        batch_totals: dict[str, int] = {}
        for item in items:
            errors = self._compute_errors(item.llm_draft, item.user_draft)
            item_results.append(
                TaskDraftFeedbackItemResult(
                    task_title=item.task_title,
                    criteria=errors,
                )
            )
            for criterion, error in errors.items():
                batch_totals[criterion] = batch_totals.get(criterion, 0) + error

        totals = self._get_accumulated(user_id)
        for criterion, error in batch_totals.items():
            totals[criterion] = totals.get(criterion, 0) + error
        self._save_accumulated(user_id, totals)

        exceeded_criteria = sorted(
            criterion
            for criterion, total in totals.items()
            if abs(total) > self._strong_signal_threshold
        )

        calibrated = False
        calibration_error: str | None = None
        preferences = self._get_preferences(user_id)

        if exceeded_criteria:
            try:
                updated_preferences = self._adapt_preferences(
                    user_id=user_id,
                    exceeded_criteria=exceeded_criteria,
                    totals=totals,
                    batch_totals=batch_totals,
                    items=items,
                    now=now,
                    current_preferences=preferences,
                )
            except (LlmUnavailableError, LlmClientError) as exc:
                calibration_error = str(exc)
                logger.warning(
                    "Не удалось перекалибровать промпт для user_id=%s: %s",
                    user_id,
                    exc,
                )
            except ValueError as exc:
                calibration_error = str(exc)
                logger.warning(
                    "Локальная модель вернула непригодный блок предпочтений "
                    "для user_id=%s: %s",
                    user_id,
                    exc,
                )
            else:
                self._save_preferences(user_id, updated_preferences)
                preferences = updated_preferences
                for criterion in exceeded_criteria:
                    totals[criterion] = 0
                self._save_accumulated(user_id, totals)
                calibrated = True

        return TaskDraftFeedback(
            user_id=user_id,
            items=item_results,
            batch_totals=batch_totals,
            accumulated_totals={
                criterion: total for criterion, total in totals.items() if total
            },
            exceeded_criteria=exceeded_criteria,
            calibrated=calibrated,
            preferences=preferences,
            calibration_error=calibration_error,
            created_at=now,
        )

    def _compute_errors(
        self,
        llm_draft: TaskDraft,
        user_draft: TaskDraft,
    ) -> dict[str, int]:
        """
        Сравнивает черновик пользователя с черновиком модели.

        Возвращает только ненулевые ошибки, чтобы ответ не разрастался.
        """
        errors: dict[str, int] = {}

        llm_minutes = llm_draft.estimated_minutes
        user_minutes = user_draft.estimated_minutes
        if user_minutes != llm_minutes:
            errors[CRITERION_DURATION] = self._ratio_error(
                user_minutes, llm_minutes
            )

        llm_description = (llm_draft.description or "").strip()
        user_description = (user_draft.description or "").strip()
        if user_description != llm_description:
            errors[CRITERION_DESCRIPTION] = self._ratio_error(
                len(user_description), len(llm_description)
            )

        if user_draft.priority != llm_draft.priority:
            # Приоритет — порядковая шкала 1..4, поэтому здесь естественна
            # обычная разница, а не отношение.
            errors[CRITERION_PRIORITY] = max(
                MIN_ERROR_BOUND,
                min(MAX_ERROR_BOUND, user_draft.priority - llm_draft.priority),
            )

        return {
            criterion: error for criterion, error in errors.items() if error != 0
        }

    @staticmethod
    def _ratio_error(user_value: int, llm_value: int) -> int:
        """
        Ошибка «во сколько раз»: знак показывает, больше ли значение
        пользователя, а модуль — целую часть отношения большего к меньшему.

        Примеры: 90 → 45 = -2; 180 → 120 = -1 (1.5 → 1); 150 → 75 = -2.
        Результат ограничен диапазоном [-3, 3]. Если одна из сторон равна
        нулю (например, пустое описание), ошибка сразу упирается в ±3.
        """
        if user_value == llm_value:
            return 0

        sign = 1 if user_value > llm_value else -1
        larger = max(user_value, llm_value)
        smaller = min(user_value, llm_value)

        if smaller <= 0:
            magnitude = MAX_ERROR_BOUND
        else:
            # Целая часть, а не округление: 1.5× даёт 1, 2× даёт 2.
            magnitude = int(larger / smaller)

        magnitude = max(1, min(MAX_ERROR_BOUND, magnitude))
        return sign * magnitude

    def _adapt_preferences(
        self,
        *,
        user_id: str,
        exceeded_criteria: list[str],
        totals: dict[str, int],
        batch_totals: dict[str, int],
        items: list[TaskDraftFeedbackItem],
        now: datetime,
        current_preferences: str | None,
    ) -> str:
        """
        Просит локальную LLM обновить только блок персональных предпочтений.
        Базовый промпт передаётся как контекст, но не подлежит изменению.
        """
        del user_id  # параметр оставлен для единообразия и будущего логирования

        signal_lines = []
        for criterion in exceeded_criteria:
            total = totals.get(criterion, 0)
            batch_total = batch_totals.get(criterion, 0)
            signal_lines.append(
                f"- {criterion}: суммарная ошибка {_format_signed(total)} "
                f"(порог {self._strong_signal_threshold}); вклад последней "
                f"пачки {_format_signed(batch_total)}. "
                f"{_direction_phrase(criterion, total)}."
            )

        examples = self._describe_batch(items)
        base_prompt = self._format_base(now)
        current_block = current_preferences or "(пока пусто)"

        exceeded_names = (
            ", ".join(exceeded_criteria) if exceeded_criteria else "ничего"
        )
        user_prompt = (
            "Базовый системный промпт (только для контекста, менять его нельзя):\n"
            "<<<\n"
            f"{base_prompt}\n"
            ">>>\n\n"
            "Текущий блок персональных предпочтений:\n"
            "<<<\n"
            f"{current_block}\n"
            ">>>\n\n"
            "Накопленная обратная связь по пользователю:\n"
            + "\n".join(signal_lines)
            + "\n\nКритерии, превысившие порог (|сумма| > "
            f"{self._strong_signal_threshold}): {exceeded_names}. "
            "Обновляй только эти критерии в блоке предпочтений; приоритет и "
            "остальные критерии в этот раунд не включай.\n\n"
            "Изменения в последней пачке задач:\n"
            + examples
            + "\n\nВерни обновлённый блок «Персональные предпочтения пользователя:»."
        )

        response = self._client.chat(
            [
                {"role": "system", "content": ADAPTATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self._adaptation_max_tokens,
            temperature=self._adaptation_temperature,
            # Нужен свободный текст: это не JSON-схема, а блок промпта.
            response_format=None,
        )
        return self._sanitize_preferences(response)

    @staticmethod
    def _describe_batch(items: list[TaskDraftFeedbackItem]) -> str:
        lines: list[str] = []
        for index, item in enumerate(items[:MAX_EXAMPLES_IN_PROMPT], start=1):
            llm_draft = item.llm_draft
            user_draft = item.user_draft
            changes: list[str] = []

            if llm_draft.estimated_minutes != user_draft.estimated_minutes:
                changes.append(
                    "estimated_minutes "
                    f"{llm_draft.estimated_minutes} → {user_draft.estimated_minutes}"
                )

            llm_description = (llm_draft.description or "").strip()
            user_description = (user_draft.description or "").strip()
            if llm_description != user_description:
                changes.append(
                    "длина описания "
                    f"{len(llm_description)} → {len(user_description)} символов"
                )

            if llm_draft.priority != user_draft.priority:
                changes.append(
                    f"priority {llm_draft.priority} → {user_draft.priority}"
                )

            if changes:
                lines.append(
                    f"{index}. «{item.task_title}»: " + "; ".join(changes) + "."
                )

        if len(items) > MAX_EXAMPLES_IN_PROMPT:
            lines.append(
                f"... ещё {len(items) - MAX_EXAMPLES_IN_PROMPT} задач(и) без "
                "подробностей."
            )
        return "\n".join(lines) if lines else "Изменений в полях не было."

    @staticmethod
    def _sanitize_preferences(raw: str) -> str:
        """
        Приводит ответ модели к чистому блоку предпочтений.

        Модель иногда добавляет markdown-ограждения, JSON-обёртку или
        повторяет базовый промпт. Всё это отбрасывается; если после очистки
        остался не блок предпочтений, выбрасывается ValueError, и сервис
        сохраняет предыдущую настройку.
        """
        text = (raw or "").strip()
        if not text:
            raise ValueError("Локальная модель вернула пустой блок предпочтений.")

        text = re.sub(
            r"^```(?:markdown|text)?\s*", "", text, flags=re.IGNORECASE
        )
        text = re.sub(r"\s*```$", "", text).strip()

        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(payload, dict):
                    for key in ("preferences", "preferences_block", "text", "content"):
                        value = payload.get(key)
                        if isinstance(value, str) and value.strip():
                            text = value.strip()
                            break

        # Модель может выделить заголовок markdown-звёздочками или решётками.
        text = re.sub(r"^[#*\s]+", "", text)

        marker = PREFERENCES_HEADER.rstrip(":")
        marker_index = text.lower().find(marker.lower())
        if marker_index > 0:
            text = text[marker_index:].strip()

        if not text.lower().startswith(marker.lower()):
            text = f"{PREFERENCES_HEADER}\n{text}"

        # Защита от эха базового промпта: такой ответ нельзя записывать
        # в персональный блок.
        if "Верни ТОЛЬКО один JSON" in text or "tasks: массив задач" in text:
            raise ValueError(
                "Модель вернула базовый промпт вместо блока предпочтений."
            )

        _, _, rest = text.partition("\n")
        text = PREFERENCES_HEADER
        if rest.strip():
            text += "\n" + rest.strip()

        if len(text) > MAX_PREFERENCES_CHARS:
            text = text[:MAX_PREFERENCES_CHARS].rstrip()
        return text

    def _format_base(self, now: datetime) -> str:
        """Форматирует базовый промпт с текущими датой и временем."""
        offset = now.strftime("%z") or "+0000"
        offset = f"{offset[:3]}:{offset[3:]}"
        values = {
            "date": now.strftime("%Y-%m-%d"),
            "weekday": RU_WEEKDAYS[now.weekday()],
            "time": now.strftime("%H:%M"),
            "offset": offset,
        }
        try:
            return self._base_system_prompt.format(**values)
        except (KeyError, IndexError, ValueError):
            return (
                self._base_system_prompt.replace("{date}", values["date"])
                .replace("{weekday}", values["weekday"])
                .replace("{time}", values["time"])
                .replace("{offset}", values["offset"])
            )

    def _ensure_loaded(self, user_id: str) -> None:
        if user_id in self._loaded_users:
            return
        self._loaded_users.add(user_id)
        if self._storage is None:
            return
        try:
            preferences = self._storage.get_setting(
                f"{PREFERENCES_STORAGE_PREFIX}{user_id}", ""
            )
            if preferences:
                self._preferences[user_id] = preferences

            raw_totals = self._storage.get_setting(
                f"{ACCUMULATED_STORAGE_PREFIX}{user_id}", ""
            )
            if raw_totals:
                payload = json.loads(raw_totals)
                if isinstance(payload, dict):
                    self._accumulated[user_id] = {
                        str(criterion): int(total)
                        for criterion, total in payload.items()
                        if isinstance(total, (int, float))
                    }
        except Exception as exc:  # pragma: no cover - защита от сбоев хранилища
            logger.warning(
                "Не удалось загрузить персональные настройки для user_id=%s: %s",
                user_id,
                exc,
            )

    def _get_preferences(self, user_id: str) -> str | None:
        self._ensure_loaded(user_id)
        return self._preferences.get(user_id)

    def _save_preferences(self, user_id: str, preferences: str) -> None:
        self._ensure_loaded(user_id)
        self._preferences[user_id] = preferences
        if self._storage is None:
            return
        try:
            self._storage.set_setting(
                f"{PREFERENCES_STORAGE_PREFIX}{user_id}", preferences
            )
        except Exception as exc:  # pragma: no cover - защита от сбоев хранилища
            logger.warning(
                "Не удалось сохранить персональные настройки для user_id=%s: %s",
                user_id,
                exc,
            )

    def _get_accumulated(self, user_id: str) -> dict[str, int]:
        self._ensure_loaded(user_id)
        return self._accumulated.setdefault(user_id, {})

    def _save_accumulated(self, user_id: str, totals: dict[str, int]) -> None:
        self._ensure_loaded(user_id)
        self._accumulated[user_id] = dict(totals)
        if self._storage is None:
            return
        try:
            self._storage.set_setting(
                f"{ACCUMULATED_STORAGE_PREFIX}{user_id}",
                json.dumps(totals, ensure_ascii=False),
            )
        except Exception as exc:  # pragma: no cover - защита от сбоев хранилища
            logger.warning(
                "Не удалось сохранить накопленную обратную связь для user_id=%s: %s",
                user_id,
                exc,
            )
