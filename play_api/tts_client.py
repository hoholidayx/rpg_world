"""Shared TTS service client for Play API routers."""

from tts_service.client import TTSClient

_client: TTSClient | None = None


def create_tts_client() -> TTSClient:
    """Create the lifespan-owned client, preserving an explicit test override."""

    global _client
    if _client is None:
        _client = TTSClient()
    return _client


def get_tts_client() -> TTSClient:
    if _client is None:
        raise RuntimeError("TTSClient is not available outside app lifespan")
    return _client


async def close_tts_client(client: TTSClient | None = None) -> None:
    global _client
    target = client if client is not None else _client
    if target is None:
        return
    if _client is target:
        _client = None
    await target.aclose()


__all__ = [
    "close_tts_client",
    "create_tts_client",
    "get_tts_client",
]
