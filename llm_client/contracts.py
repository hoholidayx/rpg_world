"""Runtime validation for provider-neutral LLM response contracts."""

from __future__ import annotations

from llm_client.client import LLMProviderContractError
from llm_client.types import LLMResponse


def require_llm_response(value: object, source: str) -> LLMResponse:
    """Return *value* as ``LLMResponse`` or raise a content-safe contract error."""
    if isinstance(value, LLMResponse):
        return value
    value_type = type(value)
    actual_type = f"{value_type.__module__}.{value_type.__qualname__}"
    normalized_source = str(source).strip() or "<unknown>"
    raise LLMProviderContractError(
        "LLM provider contract violation: "
        f"source={normalized_source}, actual_type={actual_type}",
        source=normalized_source,
        actual_type=actual_type,
    )
