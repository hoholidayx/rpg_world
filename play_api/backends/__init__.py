"""Backend provider selection for Play API."""

from play_api.backends.factory import (
    close_data_manager_backend,
    get_agent_backend,
    get_data_manager_backend,
)

__all__ = [
    "close_data_manager_backend",
    "get_agent_backend",
    "get_data_manager_backend",
]
