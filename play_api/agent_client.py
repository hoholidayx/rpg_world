"""Shared Agent service client for Play API routers."""

from __future__ import annotations

from agent_service.client import AgentClient

_client: AgentClient | None = None


def get_agent_client() -> AgentClient:
    global _client
    if _client is None:
        _client = AgentClient()
    return _client
