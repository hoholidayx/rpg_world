from __future__ import annotations

import json

import httpx
import pytest

from llm_client.client import LLMServiceAuthError, LLMServiceClient


def _handler(request: httpx.Request) -> httpx.Response:
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
                    }
                ],
            },
        )
    if request.url.path.endswith("/chat"):
        return httpx.Response(
            200,
            json={"content": "ok", "toolCalls": None, "finishReason": "stop"},
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
    return httpx.Response(404, json={"detail": {"message": "missing"}})


def test_sync_client_catalog_and_auth_mapping() -> None:
    transport = httpx.MockTransport(_handler)
    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        sync_transport=transport,
        async_transport=transport,
    )
    catalog = client.get_catalog("agent.main")
    assert catalog.default_provider_key == "chat-a"
    assert catalog.option().context_window == 1000
    client.close()

    bad = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="wrong",
        sync_transport=transport,
        async_transport=transport,
    )
    with pytest.raises(LLMServiceAuthError):
        bad.get_catalog("agent.main")
    bad.close()


@pytest.mark.asyncio
async def test_async_client_chat_and_stream() -> None:
    transport = httpx.MockTransport(_handler)
    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        sync_transport=transport,
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
