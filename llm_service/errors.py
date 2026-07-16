"""Stable LLM-service errors that need distinct wire codes."""

from __future__ import annotations


class LLMInputModalityUnsupportedError(ValueError):
    def __init__(self, modality: str, provider_key: str) -> None:
        self.modality = str(modality)
        self.provider_key = str(provider_key)
        super().__init__(
            f"LLM provider {self.provider_key!r} does not support {self.modality!r} input"
        )
