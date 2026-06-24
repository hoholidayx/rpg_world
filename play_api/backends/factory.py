"""Factory for the configured Play API backend."""

from __future__ import annotations

from play_api.backends.agent import AgentPlayBackend
from play_api.backends.base import PlayBackend
from play_api.backends.mock import MockPlayBackend
from play_api.settings import play_settings


def get_play_backend() -> PlayBackend:
    if play_settings.use_mock_backend():
        return MockPlayBackend()
    return AgentPlayBackend()
