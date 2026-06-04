"""Token counter abstraction and implementations for LLM context estimation.

Defines a ``TokenCounter`` ABC that all tokenizers must implement.
Two built-in implementations:

- ``TiktokenTokenCounter`` — uses ``tiktoken`` with ``cl100k_base`` encoding.
- ``DeepSeekTokenCounter`` — wraps a user-provided encode function for deepseek's tokenizer.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Callable


class TokenCounter(ABC):
    """Abstract token counter for LLM context estimation."""

    @abstractmethod
    def count(self, text: str) -> int:
        """Count tokens in a single text string."""
        pass

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens in a list of message dicts."""
        total = 0
        for msg in messages:
            for key in ("content", "name", "tool_call_id"):
                val = msg.get(key)
                if isinstance(val, str):
                    total += self.count(val)
            if msg.get("tool_calls"):
                total += self.count(json.dumps(msg["tool_calls"], ensure_ascii=False))
        return total

    def count_text_blocks(self, texts: list[str]) -> int:
        """Convenience: count tokens across a list of strings."""
        return sum(self.count(t) for t in texts)


class TiktokenTokenCounter(TokenCounter):
    """Token counter using tiktoken ``cl100k_base`` encoding.

    This is a reasonable fallback for most models (GPT-4o, DeepSeek V3,
    and many OpenAI-compatible APIs).
    """

    def __init__(self) -> None:
        import tiktoken

        self._enc = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        return len(self._enc.encode(text))


class DeepSeekTokenCounter(TokenCounter):
    """Token counter using deepseek's tokenizer.

    Expects a user-provided *encode_fn* that takes a text string and
    returns a list of token IDs.  The token count is ``len(token_ids)``.

    Usage::

        from your_tokenizer_module import encode

        counter = DeepSeekTokenCounter(encode_fn=encode)
        agent = RPGGameAgent(token_counter=counter)
    """

    def __init__(
        self,
        encode_fn: Callable[[str], list[int]] | None = None,
    ) -> None:
        self._encode = encode_fn

    def count(self, text: str) -> int:
        if self._encode:
            return len(self._encode(text))
        # Rough character-based fallback when no encode function is provided
        return len(text) // 4
