from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from llm_client.types import LLMResponse
from rpg_data import models
from rpg_media.background_agent import LLMMediaBackgroundAgent
from rpg_media.types import MediaBackgroundSourceSnapshot


def _source() -> MediaBackgroundSourceSnapshot:
    message = models.MediaSourceMessage(
        id=1,
        version=1,
        role=models.MESSAGE_ROLE_ASSISTANT,
        content="众人从城门走入月光森林。",
        turn_id=3,
        seq_in_turn=1,
    )
    return MediaBackgroundSourceSnapshot(
        session_id="session1",
        workspace_id="demo_workspace",
        story_id=1,
        target_turn_id=3,
        scene_attrs={"地点": "月光森林", "时间": "夜晚"},
        turns=(models.MediaSourceTurn(turn_id=3, messages=(message,)),),
        current_asset_id=None,
        current_title="",
        last_decision="",
        last_reason="",
        fingerprint="a" * 64,
        snapshot_json="{}",
    )


class _Provider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict]] = []

    async def chat(self, messages, tools=None):  # noqa: ANN001, ANN201
        self.messages.append(list(messages))
        return self.responses.pop(0)


def _tool_call(name: str, arguments: str) -> dict[str, object]:
    return {
        "id": f"call-{name}",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


@pytest.mark.asyncio
async def test_background_agent_searches_story_then_selects_returned_asset() -> None:
    provider = _Provider([
        LLMResponse(
            content="",
            tool_calls=[_tool_call(
                "search_story_backgrounds",
                '{"query":"月光森林 夜晚","tags":["森林","夜晚"]}',
            )],
            finish_reason="tool_calls",
        ),
        LLMResponse(
            content="",
            tool_calls=[_tool_call(
                "switch_background",
                '{"assetId":"asset-forest","reason":"地点已明确切换到森林"}',
            )],
            finish_reason="tool_calls",
        ),
    ])
    data = Mock()
    data.search_library_assets.return_value = [
        SimpleNamespace(
            asset=SimpleNamespace(id="asset-forest"),
            blob=SimpleNamespace(id="blob-forest"),
            item=SimpleNamespace(
                title="月光森林",
                description="夜晚的森林",
                is_default=False,
            ),
            tags=("森林", "夜晚"),
        )
    ]
    agent = LLMMediaBackgroundAgent(data, provider=provider)

    decision = await agent.decide(_source())

    assert decision.decision == "switch"
    assert decision.asset_id == "asset-forest"
    data.search_library_assets.assert_called_once_with(
        workspace_id="demo_workspace",
        scope=models.MEDIA_LIBRARY_SCOPE_STORY,
        story_id=1,
        query="月光森林 夜晚",
        tags=("森林", "夜晚"),
        limit=20,
    )
    assert provider.messages[1][-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_background_agent_does_not_offer_assets_with_missing_files() -> None:
    provider = _Provider([
        LLMResponse(
            content="",
            tool_calls=[_tool_call(
                "search_story_backgrounds",
                '{"query":"森林","tags":[]}',
            )],
            finish_reason="tool_calls",
        ),
        LLMResponse(
            content="",
            tool_calls=[_tool_call(
                "switch_background",
                '{"assetId":"asset-existing","reason":"匹配当前森林场景"}',
            )],
            finish_reason="tool_calls",
        ),
    ])
    data = Mock()
    data.search_library_assets.return_value = [
        SimpleNamespace(
            asset=SimpleNamespace(id="asset-missing"),
            blob=SimpleNamespace(id="blob-missing"),
            item=SimpleNamespace(title="Missing", description="missing", is_default=False),
            tags=("森林",),
        ),
        SimpleNamespace(
            asset=SimpleNamespace(id="asset-existing"),
            blob=SimpleNamespace(id="blob-existing"),
            item=SimpleNamespace(title="Existing", description="existing", is_default=False),
            tags=("森林",),
        ),
    ]
    agent = LLMMediaBackgroundAgent(
        data,
        provider=provider,
        asset_exists=lambda blob: blob.id == "blob-existing",
    )

    decision = await agent.decide(_source())

    assert decision.asset_id == "asset-existing"
    tool_payload = provider.messages[1][-1]["content"]
    assert "asset-existing" in tool_payload
    assert "asset-missing" not in tool_payload


@pytest.mark.asyncio
async def test_background_agent_rejects_unsearched_asset() -> None:
    provider = _Provider([
        LLMResponse(
            content="",
            tool_calls=[_tool_call(
                "switch_background",
                '{"assetId":"hallucinated","reason":"change"}',
            )],
            finish_reason="tool_calls",
        )
    ])
    agent = LLMMediaBackgroundAgent(Mock(), provider=provider)

    with pytest.raises(ValueError, match="not returned by search"):
        await agent.decide(_source())
