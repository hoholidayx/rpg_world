from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from llm_client.client import (
    LLM_PROVIDER_CONTRACT_ERROR,
    LLMProviderContractError,
    LLMServiceClient,
)
from llm_client.contracts import require_llm_response
from llm_client.types import LLMResponse
from llm_service import main as service_main
from tests.support.scripted_llm import InvalidChatResponseProvider


def test_require_llm_response_accepts_the_canonical_type() -> None:
    response = LLMResponse(
        content="ok",
        tool_calls=None,
        finish_reason="stop",
    )

    assert require_llm_response(response, "contract-test") is response


@pytest.mark.parametrize(
    ("value", "actual_type"),
    [
        ({"secret": "must-not-leak"}, "builtins.dict"),
        (
            SimpleNamespace(secret="must-not-leak"),
            "types.SimpleNamespace",
        ),
        (None, "builtins.NoneType"),
    ],
)
def test_require_llm_response_rejects_invalid_types_without_content(
    value: object,
    actual_type: str,
) -> None:
    with pytest.raises(LLMProviderContractError) as raised:
        require_llm_response(value, "guard-negative-test")

    assert raised.value.source == "guard-negative-test"
    assert raised.value.actual_type == actual_type
    assert "guard-negative-test" in str(raised.value)
    assert actual_type in str(raised.value)
    assert "must-not-leak" not in str(raised.value)


def test_llm_service_serializes_chat_and_pointwise_contract_errors(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_WORLD_LLM_SERVICE_TOKEN", "test-token")
    provider = InvalidChatResponseProvider(
        {"secret": "provider-payload-must-not-leak"}
    )

    class FakeManager:
        def get_provider(self, _biz_key, *, provider_key=None):  # noqa: ANN001, ANN201
            del provider_key
            return provider

    monkeypatch.setattr(
        service_main.LLMManager,
        "get",
        classmethod(lambda cls: FakeManager()),
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(service_main.app) as client:
        chat = client.post(
            "/llm/v1/chat",
            headers=headers,
            json={
                "bizKey": "agent.main",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        rerank = client.post(
            "/llm/v1/rerank",
            headers=headers,
            json={
                "bizKey": "memory.rerank",
                "query": "query",
                "documents": ["candidate"],
            },
        )

    assert chat.status_code == 502
    assert chat.json()["detail"]["errorCode"] == LLM_PROVIDER_CONTRACT_ERROR
    assert "llm_service.chat:agent.main" in chat.json()["detail"]["message"]
    assert "provider-payload-must-not-leak" not in chat.text
    assert rerank.status_code == 502
    assert rerank.json()["detail"]["errorCode"] == LLM_PROVIDER_CONTRACT_ERROR
    assert "llm_service.pointwise" in rerank.json()["detail"]["message"]
    assert "provider-payload-must-not-leak" not in rerank.text


@pytest.mark.asyncio
async def test_http_client_restores_contract_error_for_json_and_sse() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "errorCode": LLM_PROVIDER_CONTRACT_ERROR,
            "message": (
                "LLM provider contract violation: "
                "source=llm_service.chat:agent.main, actual_type=builtins.dict"
            ),
            "requestId": "request-contract",
        }
        if request.url.path.endswith("/chat/stream"):
            return httpx.Response(
                200,
                text=(
                    "event: error\n"
                    f"data: {json.dumps(payload)}\n\n"
                ),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(502, json={"detail": payload})

    client = LLMServiceClient(
        base_url="http://llm.test/llm/v1",
        token="token",
        async_transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMProviderContractError) as chat_error:
        await client.chat(
            biz_key="agent.main",
            provider_key=None,
            messages=[],
            tools=None,
        )
    assert chat_error.value.status_code == 502
    assert chat_error.value.request_id == "request-contract"

    with pytest.raises(LLMProviderContractError) as stream_error:
        async for _chunk in client.chat_stream(
            biz_key="agent.main",
            provider_key=None,
            messages=[],
            tools=None,
        ):
            pass
    assert stream_error.value.request_id == "request-contract"
    await client.aclose()
