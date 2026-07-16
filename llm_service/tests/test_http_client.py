from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from llm_client.client import LLMServiceAuthError, LLMServiceClient
from llm_client.manager import LLMClientManager


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/health"):
        return httpx.Response(200, json={"status": "ok", "configLoaded": True})
    if request.headers.get("authorization") != "Bearer token":
        return httpx.Response(
            401,
            json={"detail": {"errorCode": "LLM_AUTH_FAILED", "message": "bad token"}},
        )
    if request.url.path.endswith("/catalog/agent.main"):
        return httpx.Response(
            200,
            json={
                "bizKey": "agent.main",
                "kind": "chat",
                "defaultProviderKey": "chat-a",
                "options": [
                    {
                        "providerKey": "chat-a",
                        "backend": "openai",
                        "model": "model-a",
                        "contextWindow": 1000,
                        "inputModalities": ["text", "image"],
                    }
                ],
            },
        )
    if request.url.path.endswith("/chat"):
        return httpx.Response(
            200,
            json={"content": "ok", "toolCalls": None, "finishReason": "stop"},
        )
    if request.url.path.endswith("/speech/profile/tts.reply"):
        return httpx.Response(
            200,
            json={
                "bizKey": "tts.reply",
                "providerKey": "openai-tts",
                "model": "gpt-4o-mini-tts",
                "voice": "alloy",
                "responseFormat": "mp3",
                "speed": 1.0,
                "cacheRevision": "v1",
                "configFingerprint": "a" * 64,
            },
        )
    if request.url.path.endswith("/speech"):
        return httpx.Response(
            200,
            content=b"ID3audio",
            headers={
                "content-type": "audio/mpeg",
                "x-speech-config-fingerprint": "a" * 64,
            },
        )
    if request.url.path.endswith("/chat/stream"):
        body = (
            "event: chunk\n"
            f"data: {json.dumps({'content': 'a'})}\n\n"
            "event: chunk\n"
            f"data: {json.dumps({'content': 'b', 'finishReason': 'stop'})}\n\n"
            "event: done\n"
            "data: {}\n\n"
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    if request.url.path.endswith("/embeddings"):
        return httpx.Response(200, json={"vectors": [[0.1, 0.2, 0.3]]})
    return httpx.Response(404, json={"detail": {"message": "missing"}})


@pytest.mark.asyncio
async def test_async_client_catalog_and_auth_mapping() -> None:
    transport = httpx.MockTransport(_handler)
    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        async_transport=transport,
    )
    catalog = await client.get_catalog("agent.main")
    assert catalog.default_provider_key == "chat-a"
    assert catalog.option().context_window == 1000
    assert catalog.option().input_modalities == ("text", "image")
    assert catalog.option().supports_input_modality("image") is True
    await client.aclose()

    bad = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="wrong",
        async_transport=transport,
    )
    with pytest.raises(LLMServiceAuthError):
        await bad.get_catalog("agent.main")
    await bad.aclose()


@pytest.mark.asyncio
async def test_async_client_chat_and_stream() -> None:
    transport = httpx.MockTransport(_handler)
    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        async_transport=transport,
    )
    response = await client.chat(
        biz_key="agent.main",
        provider_key=None,
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
    )
    chunks = [
        chunk.content
        async for chunk in client.chat_stream(
            biz_key="agent.main",
            provider_key=None,
            messages=[],
            tools=None,
        )
    ]
    assert response.content == "ok"
    assert chunks == ["a", "b"]
    await client.aclose()


@pytest.mark.asyncio
async def test_async_client_speech_profile_and_audio() -> None:
    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        async_transport=httpx.MockTransport(_handler),
    )

    profile = await client.get_speech_profile("tts.reply")
    audio = await client.speech(
        biz_key="tts.reply",
        provider_key=None,
        text="hello",
    )

    assert profile.voice == "alloy"
    assert profile.config_fingerprint == "a" * 64
    assert audio.content == b"ID3audio"
    assert audio.media_type == "audio/mpeg"
    assert audio.config_fingerprint == profile.config_fingerprint
    await client.aclose()


async def test_health_is_an_unauthenticated_process_probe() -> None:
    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="wrong",
        async_transport=httpx.MockTransport(_handler),
    )

    payload = await client.health()

    assert payload == {"status": "ok", "configLoaded": True}
    await client.aclose()


async def test_slow_catalog_and_embedding_requests_do_not_block_event_loop() -> None:
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return _handler(request)

    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        async_transport=httpx.MockTransport(slow_handler),
    )
    stopped = asyncio.Event()
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while not stopped.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    ticker_task = asyncio.create_task(ticker())
    await asyncio.gather(
        client.get_catalog("agent.main"),
        client.embed(
            biz_key="memory.embed",
            provider_key=None,
            texts=["memory"],
        ),
    )
    stopped.set()
    await ticker_task

    assert ticks >= 5
    await client.aclose()


async def test_client_rejects_cross_event_loop_reuse() -> None:
    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        async_transport=httpx.MockTransport(_handler),
    )
    await client.get_catalog("agent.main")

    def use_from_new_loop() -> None:
        asyncio.run(client.get_catalog("agent.main"))

    with pytest.raises(RuntimeError, match="cannot be reused across event loops"):
        await asyncio.to_thread(use_from_new_loop)

    await client.aclose()


async def test_manager_reconfigure_and_reset_close_previous_async_client() -> None:
    await LLMClientManager.areset()
    first = await LLMClientManager.aconfigure(
        base_url="http://llm-one.test/llm/v1",
        token="one",
        request_timeout_ms=1000,
        stream_timeout_ms=1000,
    )
    first_http = first.client._async  # noqa: SLF001

    second = await LLMClientManager.aconfigure(
        base_url="http://llm-two.test/llm/v1",
        token="two",
        request_timeout_ms=1000,
        stream_timeout_ms=1000,
    )
    second_http = second.client._async  # noqa: SLF001

    assert first_http.is_closed is True
    assert second_http.is_closed is False

    await LLMClientManager.areset()

    assert second_http.is_closed is True
