"""Shared Agent service client for Play API routers."""

from __future__ import annotations

from agent_service.client import AgentClient

_client: AgentClient | None = None


def create_agent_client() -> AgentClient:
    """Create the lifespan-owned client, preserving an explicit test override."""

    global _client
    if _client is None:
        _client = AgentClient()
    return _client


def get_agent_client() -> AgentClient:
    if _client is None:
        raise RuntimeError("AgentClient is not available outside app lifespan")
    return _client


async def close_agent_client(client: AgentClient | None = None) -> None:
    global _client
    target = client if client is not None else _client
    if target is None:
        return
    if _client is target:
        _client = None
    await target.aclose()


__all__ = [
    "close_agent_client",
    "create_agent_client",
    "get_agent_client",
]
