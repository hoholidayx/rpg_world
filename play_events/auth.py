"""Shared authentication defaults for the internal Play event ingress."""

from __future__ import annotations

import os

DEFAULT_PLAY_EVENT_TOKEN_ENV = "RPG_WORLD_PLAY_EVENT_TOKEN"
DEFAULT_PLAY_EVENT_TOKEN = "rpg-world-local-event-token"


def resolve_play_event_token(
    token_env: str = DEFAULT_PLAY_EVENT_TOKEN_ENV,
) -> str:
    """Resolve the producer/consumer token with a local-development fallback."""

    return (os.environ.get(token_env) or "").strip() or DEFAULT_PLAY_EVENT_TOKEN


def uses_default_play_event_token(
    token_env: str = DEFAULT_PLAY_EVENT_TOKEN_ENV,
) -> bool:
    return not (os.environ.get(token_env) or "").strip()
