"""Shared loop-owned Dream service client for Play API routers."""

from __future__ import annotations

from dream_service.client import DreamClient

_client: DreamClient | None = None


def create_dream_client() -> DreamClient:
    """Create the lifespan-owned client, preserving an explicit test override."""

    global _client
    if _client is None:
        _client = DreamClient()
    return _client


def get_dream_client() -> DreamClient:
    if _client is None:
        raise RuntimeError("DreamClient is not available outside app lifespan")
    return _client


async def close_dream_client(client: DreamClient | None = None) -> None:
    global _client
    target = client if client is not None else _client
    if target is None:
        return
    if _client is target:
        _client = None
    await target.aclose()


__all__ = [
    "close_dream_client",
    "create_dream_client",
    "get_dream_client",
]
