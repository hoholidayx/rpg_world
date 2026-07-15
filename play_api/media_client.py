"""Shared Media service client for Play API routers."""

from __future__ import annotations

from media_service.client import MediaClient

_client: MediaClient | None = None


def get_media_client() -> MediaClient:
    global _client
    if _client is None:
        _client = MediaClient()
    return _client


async def close_media_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
