"""Backend provider selection for Play API."""

from play_api.backends.factory import get_agent_backend, get_data_manager_backend

__all__ = ["get_agent_backend", "get_data_manager_backend"]
