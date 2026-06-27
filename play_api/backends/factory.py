"""Factory for Play API backend providers."""

from __future__ import annotations

from play_api.backends.agent import AgentBackend
from play_api.backends.data_manager import DataManagerBackend
from rpg_data.services import reset_data_service_gateways
from rpg_data.settings import get_database_path

_data_manager_backend: DataManagerBackend | None = None


def get_agent_backend() -> AgentBackend:
    return AgentBackend()


def get_data_manager_backend() -> DataManagerBackend:
    global _data_manager_backend

    database_path = get_database_path()
    if (
        _data_manager_backend is None
        or _data_manager_backend.database_path != database_path
    ):
        if _data_manager_backend is not None:
            _data_manager_backend.close()
        _data_manager_backend = DataManagerBackend(database_path)
    return _data_manager_backend


def close_data_manager_backend() -> None:
    global _data_manager_backend

    if _data_manager_backend is not None:
        _data_manager_backend.close()
        _data_manager_backend = None
    reset_data_service_gateways()
