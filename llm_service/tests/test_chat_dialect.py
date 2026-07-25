from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_service.chat_dialect import (
    DeepSeekChatDialect,
    OpenAIChatDialect,
    build_chat_completion_dialect,
)
from llm_service.keys import (
    OPENAI_API_DIALECT_DEEPSEEK,
    OPENAI_API_DIALECT_OPENAI,
    REASONING_EFFORT_HIGH,
    REASONING_EFFORT_MAX,
    THINKING_MODE_DISABLED,
    THINKING_MODE_ENABLED,
)
from llm_service.openai_provider import OpenAIProvider


def test_deepseek_dialect_encodes_thinking_and_preserves_reasoning_messages() -> None:
    dialect = build_chat_completion_dialect(
        OPENAI_API_DIALECT_DEEPSEEK,
        thinking_mode=THINKING_MODE_ENABLED,
        reasoning_effort=REASONING_EFFORT_MAX,
    )
    kwargs: dict[str, object] = {}
    messages = [
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "先查询状态。",
            "tool_calls": [{"id": "call_1"}],
        }
    ]

    dialect.apply_request(kwargs, messages)

    assert kwargs["messages"] == messages
    assert kwargs["reasoning_effort"] == REASONING_EFFORT_MAX
    assert kwargs["extra_body"] == {"thinking": {"type": THINKING_MODE_ENABLED}}
    assert dialect.response_reasoning_content(
        SimpleNamespace(reasoning_content="思考内容")
    ) == "思考内容"


def test_deepseek_disabled_dialect_sends_explicit_switch_without_effort() -> None:
    dialect = DeepSeekChatDialect(
        thinking_mode=THINKING_MODE_DISABLED,
        reasoning_effort=None,
    )
    kwargs: dict[str, object] = {}

    dialect.apply_request(kwargs, [{"role": "user", "content": "hi"}])

    assert kwargs["extra_body"] == {"thinking": {"type": THINKING_MODE_DISABLED}}
    assert "reasoning_effort" not in kwargs


def test_openai_dialect_strips_deepseek_reasoning_field() -> None:
    dialect = OpenAIChatDialect(
        thinking_mode=THINKING_MODE_ENABLED,
        reasoning_effort=REASONING_EFFORT_HIGH,
    )
    kwargs: dict[str, object] = {}

    dialect.apply_request(
        kwargs,
        [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "deepseek-only",
                "tool_calls": [{"id": "call_1"}],
            }
        ],
    )

    assert kwargs["messages"] == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1"}],
        }
    ]
    assert kwargs["reasoning_effort"] == REASONING_EFFORT_HIGH
    assert "extra_body" not in kwargs
    assert dialect.response_reasoning_content(
        SimpleNamespace(reasoning_content="hidden")
    ) is None


@pytest.mark.parametrize(
    ("api_dialect", "thinking_mode", "reasoning_effort", "message"),
    [
        ("unknown", THINKING_MODE_DISABLED, None, "unsupported"),
        (
            OPENAI_API_DIALECT_OPENAI,
            THINKING_MODE_ENABLED,
            None,
            "is required",
        ),
        (
            OPENAI_API_DIALECT_OPENAI,
            THINKING_MODE_DISABLED,
            REASONING_EFFORT_HIGH,
            "must be omitted",
        ),
    ],
)
def test_dialect_rejects_invalid_configuration(
    api_dialect: str,
    thinking_mode: str,
    reasoning_effort: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_chat_completion_dialect(
            api_dialect,
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
        )


@pytest.mark.asyncio
async def test_openai_provider_applies_deepseek_dialect_to_sdk_request() -> None:
    captured: dict[str, object] = {}
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="完成",
                    reasoning_content="先判断。",
                    tool_calls=None,
                ),
                finish_reason="stop",
            )
        ],
        usage=None,
        model="deepseek-model",
        id="req-1",
        created=1,
    )

    class Completions:
        async def create(self, **kwargs):  # noqa: ANN003, ANN202
            captured.update(kwargs)
            return response

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    provider = OpenAIProvider(
        model="deepseek-model",
        api_dialect=OPENAI_API_DIALECT_DEEPSEEK,
        thinking_mode=THINKING_MODE_ENABLED,
        reasoning_effort=REASONING_EFFORT_MAX,
        client=client,  # type: ignore[arg-type]
    )

    result = await provider.chat(
        [{"role": "user", "content": "行动"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
    )

    assert captured["extra_body"] == {
        "thinking": {"type": THINKING_MODE_ENABLED}
    }
    assert captured["reasoning_effort"] == REASONING_EFFORT_MAX
    assert captured["messages"] == [{"role": "user", "content": "行动"}]
    assert result.reasoning_content == "先判断。"


@pytest.mark.asyncio
async def test_openai_provider_applies_deepseek_dialect_to_stream_request() -> None:
    captured: dict[str, object] = {}

    async def chunks():
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        reasoning_content="流式思考。",
                        tool_calls=None,
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
            model="deepseek-model",
            id="req-stream",
            created=1,
        )

    class Completions:
        async def create(self, **kwargs):  # noqa: ANN003, ANN202
            captured.update(kwargs)
            return chunks()

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions())
    )
    provider = OpenAIProvider(
        model="deepseek-model",
        api_dialect=OPENAI_API_DIALECT_DEEPSEEK,
        thinking_mode=THINKING_MODE_ENABLED,
        reasoning_effort=REASONING_EFFORT_HIGH,
        client=client,  # type: ignore[arg-type]
    )

    result = [
        chunk
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "行动"}]
        )
    ]

    assert captured["stream"] is True
    assert captured["extra_body"] == {
        "thinking": {"type": THINKING_MODE_ENABLED}
    }
    assert captured["reasoning_effort"] == REASONING_EFFORT_HIGH
    assert result[0].reasoning_content == "流式思考。"
