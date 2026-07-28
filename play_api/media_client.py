"""Shared Media service client for Play API routers."""

from __future__ import annotations

from media_service.client import MediaClient

_client: MediaClient | None = None


def create_media_client() -> MediaClient:
    """Create the lifespan-owned client, preserving an explicit test override."""

    global _client
    if _client is None:
        _client = MediaClient()
    return _client


def get_media_client() -> MediaClient:
    if _client is None:
        raise RuntimeError("MediaClient is not available outside app lifespan")
    return _client


async def close_media_client(client: MediaClient | None = None) -> None:
    global _client
    target = client if client is not None else _client
    if target is None:
        return
    if _client is target:
        _client = None
    await target.aclose()


__all__ = [
    "close_media_client",
    "create_media_client",
    "get_media_client",
]
