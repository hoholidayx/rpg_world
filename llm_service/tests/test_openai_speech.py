from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_service.openai_speech import OpenAISpeechProvider, SpeechProfile


@pytest.mark.asyncio
async def test_openai_speech_provider_uses_typed_profile() -> None:
    calls: list[dict[str, object]] = []

    class Speech:
        async def create(self, **kwargs):  # noqa: ANN003, ANN201
            calls.append(kwargs)
            return SimpleNamespace(content=b"ID3audio")

    client = SimpleNamespace(audio=SimpleNamespace(speech=Speech()))
    profile = SpeechProfile(
        provider_key="openai-tts",
        model="gpt-4o-mini-tts",
        voice="alloy",
        response_format="mp3",
        speed=1.0,
        cache_revision="v1",
        config_fingerprint="f" * 64,
    )
    provider = OpenAISpeechProvider(client=client, profile=profile)  # type: ignore[arg-type]

    audio = await provider.synthesize("你好")

    assert audio == b"ID3audio"
    assert calls == [
        {
            "model": "gpt-4o-mini-tts",
            "voice": "alloy",
            "input": "你好",
            "response_format": "mp3",
            "speed": 1.0,
        }
    ]
