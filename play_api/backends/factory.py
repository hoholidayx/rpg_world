"""Factory for Play API backend providers."""

from __future__ import annotations

from play_api.backends.agent import AgentBackend
from play_api.backends.data_manager import DataManagerBackend


def get_agent_backend() -> AgentBackend:
    return AgentBackend()


def get_data_manager_backend() -> DataManagerBackend:
    return DataManagerBackend()
