"""Shared loop-owned Dream service client for Play API routers."""

from __future__ import annotations

from dream_service.client import DreamClient

_client: DreamClient | None = None


def get_dream_client() -> DreamClient:
    global _client
    if _client is None:
        _client = DreamClient()
    return _client


async def close_dream_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
