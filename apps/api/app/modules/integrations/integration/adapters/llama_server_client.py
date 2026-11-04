from __future__ import annotations

from typing import Any, Callable, Protocol

import requests
from requests.exceptions import Timeout


class LlmClientError(RuntimeError):
    """llama-server вернул некорректный ответ или отказал в запросе."""


class LlmUnavailableError(LlmClientError):
    """llama-server недоступен (не запущен, таймаут, сеть)."""


class LlmChatClient(Protocol):
    """Минимальный интерфейс чат-клиента — удобно подменять в тестах."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        ...


class LlamaServerChatClient:
    """
    Клиент OpenAI-совместимого API llama-server.

    llama-server запускается отдельно, например:
        llama-server -m Qwen3.5-4B-Q4_K_M.gguf --mmproj mmproj-F16.gguf --jinja
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        model: str = "qwen3.5-4b",
        api_key: str = "",
        timeout_seconds: int = 120,
        disable_thinking: bool = True,
        request_fn: Callable[..., Any] = requests.post,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._disable_thinking = disable_thinking
        self._request_fn = request_fn

    @property
    def endpoint(self) -> str:
        """Собирает /v1/chat/completions, не дублируя /v1 в базовом URL."""
        if self._base_url.endswith("/v1"):
            return f"{self._base_url}/chat/completions"
        return f"{self._base_url}/v1/chat/completions"

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            # Грамматика llama-server не даёт модели вернуть markdown вокруг JSON.
            "response_format": {"type": "json_object"},
        }

        if self._disable_thinking:
            # Qwen3/3.5 без этого может потратить весь ответ на reasoning.
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = self._request_fn(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except Timeout as exc:
            raise LlmUnavailableError(
                "Локальная модель не ответила вовремя (таймаут запроса). "
                "Возможно, файл слишком большой для контекста модели или видеокарта "
                "загружена. Увеличьте LOCAL_LLM_TIMEOUT_SECONDS или загрузите "
                "меньший файл."
            ) from exc
        except requests.RequestException as exc:
            raise LlmUnavailableError(
                "Локальная модель недоступна. Запустите llama-server и проверьте "
                "LOCAL_LLM_BASE_URL."
            ) from exc

        status_code = int(getattr(response, "status_code", 0))
        if status_code >= 500:
            raise LlmUnavailableError(
                f"llama-server временно недоступен (HTTP {status_code})."
            )

        if status_code != 200:
            details = getattr(response, "text", "")
            details = str(details)[:300]
            raise LlmClientError(
                f"llama-server отклонил запрос (HTTP {status_code}): {details}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LlmClientError("llama-server вернул ответ не в формате JSON.") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmClientError(
                "В ответе llama-server нет choices[0].message.content."
            ) from exc

        # Некоторые сборки возвращают content списком частей.
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )

        if not isinstance(content, str) or not content.strip():
            raise LlmClientError("Локальная модель вернула пустой ответ.")

        return content
