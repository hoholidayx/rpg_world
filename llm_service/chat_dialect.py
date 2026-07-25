"""Provider-specific Chat Completions request and reasoning adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Protocol

from llm_service.keys import (
    OPENAI_API_DIALECT_DEEPSEEK,
    OPENAI_API_DIALECT_OPENAI,
    REASONING_EFFORTS,
    THINKING_MODE_DISABLED,
    THINKING_MODE_ENABLED,
    THINKING_MODES,
)

_REASONING_CONTENT_FIELD = "reasoning_content"


class _MessageLike(Protocol):
    reasoning_content: object


class ChatCompletionDialect(ABC):
    """Encode one provider dialect without leaking it into business callers."""

    def __init__(
        self,
        *,
        thinking_mode: str,
        reasoning_effort: str | None,
    ) -> None:
        normalized_mode = str(thinking_mode).strip().lower()
        if normalized_mode not in THINKING_MODES:
            raise ValueError(
                "thinking_mode must be one of "
                f"{', '.join(sorted(THINKING_MODES))}; got {thinking_mode!r}"
            )
        normalized_effort = (
            str(reasoning_effort).strip().lower()
            if reasoning_effort is not None
            else None
        )
        if normalized_effort is not None and normalized_effort not in REASONING_EFFORTS:
            raise ValueError(
                "reasoning_effort must be one of "
                f"{', '.join(sorted(REASONING_EFFORTS))}; got {reasoning_effort!r}"
            )
        if normalized_mode == THINKING_MODE_ENABLED and normalized_effort is None:
            raise ValueError("reasoning_effort is required when thinking_mode is enabled")
        if normalized_mode == THINKING_MODE_DISABLED and normalized_effort is not None:
            raise ValueError("reasoning_effort must be omitted when thinking_mode is disabled")
        self._thinking_mode = normalized_mode
        self._reasoning_effort = normalized_effort

    @property
    def thinking_mode(self) -> str:
        return self._thinking_mode

    @property
    def reasoning_effort(self) -> str | None:
        return self._reasoning_effort

    @abstractmethod
    def apply_request(
        self,
        kwargs: dict[str, object],
        messages: Sequence[Mapping[str, object]],
    ) -> None:
        """Mutate request kwargs with dialect-specific messages and parameters."""

    @abstractmethod
    def response_reasoning_content(self, message: _MessageLike) -> str | None:
        """Extract provider-visible reasoning text when this dialect exposes it."""


class OpenAIChatDialect(ChatCompletionDialect):
    """Standard OpenAI Chat Completions dialect."""

    def apply_request(
        self,
        kwargs: dict[str, object],
        messages: Sequence[Mapping[str, object]],
    ) -> None:
        kwargs["messages"] = [
            {
                key: value
                for key, value in message.items()
                if key != _REASONING_CONTENT_FIELD
            }
            for message in messages
        ]
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort

    def response_reasoning_content(self, message: _MessageLike) -> str | None:
        del message
        return None


class DeepSeekChatDialect(ChatCompletionDialect):
    """DeepSeek thinking-mode extensions to OpenAI Chat Completions."""

    def apply_request(
        self,
        kwargs: dict[str, object],
        messages: Sequence[Mapping[str, object]],
    ) -> None:
        kwargs["messages"] = [dict(message) for message in messages]
        kwargs["extra_body"] = {
            "thinking": {
                "type": self.thinking_mode,
            }
        }
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort

    def response_reasoning_content(self, message: _MessageLike) -> str | None:
        value = getattr(message, _REASONING_CONTENT_FIELD, None)
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return value if stripped else None


def build_chat_completion_dialect(
    api_dialect: str,
    *,
    thinking_mode: str,
    reasoning_effort: str | None,
) -> ChatCompletionDialect:
    normalized = str(api_dialect).strip().lower()
    if normalized == OPENAI_API_DIALECT_OPENAI:
        return OpenAIChatDialect(
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
        )
    if normalized == OPENAI_API_DIALECT_DEEPSEEK:
        return DeepSeekChatDialect(
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
        )
    raise ValueError(f"unsupported OpenAI-compatible api_dialect: {api_dialect!r}")
