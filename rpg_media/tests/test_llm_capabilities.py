from __future__ import annotations

import base64

import pytest

from llm_client.client import LLMServiceRemoteError
from llm_client.types import LLMResponse
from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.brief import LLMVisualBriefPlanner
from rpg_media.errors import (
    MediaImageAnalysisFailedError,
    MediaImageAnalysisUnsupportedError,
    MediaVisualBriefFailedError,
)
from rpg_media.image_store import inspect_image_bytes
from rpg_media.metadata import LLMImageMetadataAnalyzer
from rpg_media.source import build_source_snapshot

PNG = b"\x89PNG\r\n\x1a\nmetadata"


class _JSONProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list[dict] | None = None

    async def chat(self, messages, tools=None):  # noqa: ANN001, ANN201
        self.messages = messages
        return LLMResponse(
            content=self.content,
            tool_calls=None,
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_image_metadata_analyzer_uses_validated_data_url_and_typed_result() -> None:
    provider = _JSONProvider(
        '```json\n{"title":"月光森林","description":"月光照亮林间石门。",'
        '"tags":["森林","夜晚","森林"]}\n```'
    )
    analyzer = LLMImageMetadataAnalyzer(provider=provider)  # type: ignore[arg-type]

    result = await analyzer.analyze(inspect_image_bytes(PNG))

    assert result.title == "月光森林"
    assert result.description == "月光照亮林间石门。"
    assert result.tags == ("森林", "夜晚")
    assert provider.messages is not None
    user_content = provider.messages[1]["content"]
    image_url = user_content[1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")
    assert base64.b64decode(image_url.split(",", 1)[1]) == PNG


@pytest.mark.asyncio
async def test_image_metadata_analyzer_maps_modality_and_invalid_output_errors() -> None:
    class UnsupportedProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001, ANN201
            raise LLMServiceRemoteError(
                "no image support",
                error_code="LLM_INPUT_MODALITY_UNSUPPORTED",
                status_code=422,
            )

    with pytest.raises(MediaImageAnalysisUnsupportedError):
        await LLMImageMetadataAnalyzer(UnsupportedProvider()).analyze(  # type: ignore[arg-type]
            inspect_image_bytes(PNG)
        )

    with pytest.raises(MediaImageAnalysisFailedError):
        await LLMImageMetadataAnalyzer(_JSONProvider("not-json")).analyze(  # type: ignore[arg-type]
            inspect_image_bytes(PNG)
        )


@pytest.mark.asyncio
async def test_llm_visual_brief_planner_uses_snapshot_and_rejects_invalid_output(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "brief-llm.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="brief")
    assert session is not None
    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "Alice 推开覆雪的石门。",
        turn_id=1,
        seq_in_turn=1,
    )
    source = build_source_snapshot(
        gateway.media,
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )
    provider = _JSONProvider(
        '{"sceneDescription":"覆雪石门被推开","subjects":["Alice"],'
        '"environment":"雪夜森林","action":"推开石门","composition":"广角",'
        '"moodLighting":"冷色月光","style":"电影概念艺术",'
        '"negativeConstraints":"文字、水印","aspectRatio":"16:9"}'
    )

    brief = await LLMVisualBriefPlanner(provider=provider).plan(source)  # type: ignore[arg-type]

    assert brief.scene_description == "覆雪石门被推开"
    assert brief.subjects == ("Alice",)
    assert provider.messages is not None
    assert provider.messages[1]["content"] == source.snapshot_json

    with pytest.raises(MediaVisualBriefFailedError):
        await LLMVisualBriefPlanner(_JSONProvider('{"sceneDescription":"x","aspectRatio":"2:1"}')).plan(  # type: ignore[arg-type]
            source
        )
