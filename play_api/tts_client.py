"""Shared TTS service client for Play API routers."""

from tts_service.client import TTSClient

_client: TTSClient | None = None


def get_tts_client() -> TTSClient:
    global _client
    if _client is None:
        _client = TTSClient()
    return _client


async def close_tts_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
