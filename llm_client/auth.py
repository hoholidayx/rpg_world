"""Shared authentication defaults for the standalone LLM service."""

from __future__ import annotations

import os

DEFAULT_LLM_SERVICE_TOKEN_ENV = "RPG_WORLD_LLM_SERVICE_TOKEN"
DEFAULT_LLM_SERVICE_TOKEN = "rpg-world-local-token"


def resolve_llm_service_token(
    token_env: str = DEFAULT_LLM_SERVICE_TOKEN_ENV,
) -> str:
    """Resolve the configured token, falling back to the shared local token."""

    return (os.environ.get(token_env) or "").strip() or DEFAULT_LLM_SERVICE_TOKEN


def uses_default_llm_service_token(
    token_env: str = DEFAULT_LLM_SERVICE_TOKEN_ENV,
) -> bool:
    """Return whether token resolution will use the built-in local default."""

    return not (os.environ.get(token_env) or "").strip()
