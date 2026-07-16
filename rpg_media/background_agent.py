"""Provider-neutral media agent for conservative background selection."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from llm_client.keys import MEDIA_SCENE_BACKGROUND_MATCH_BIZ_KEY
from llm_client.manager import LLMClientManager
from llm_client.types import LLMProvider
from rpg_data import models
from rpg_data.services.media import MediaDataService
from rpg_media.types import MediaBackgroundDecision, MediaBackgroundSourceSnapshot


class BackgroundMatcher(Protocol):
    async def decide(
        self,
        source: MediaBackgroundSourceSnapshot,
    ) -> MediaBackgroundDecision: ...


class LLMMediaBackgroundAgent:
    def __init__(
        self,
        data: MediaDataService,
        *,
        provider: LLMProvider | None = None,
        asset_exists: Callable[[models.MediaBlob], bool] | None = None,
        max_rounds: int = 4,
    ) -> None:
        self._data = data
        self._provider = provider
        self._asset_exists = asset_exists or (lambda _blob: True)
        self._max_rounds = max(1, int(max_rounds))

    async def decide(
        self,
        source: MediaBackgroundSourceSnapshot,
    ) -> MediaBackgroundDecision:
        provider = self._provider or await LLMClientManager.get().get_provider(
            MEDIA_SCENE_BACKGROUND_MATCH_BIZ_KEY
        )
        messages: list[dict] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _source_prompt(source)},
        ]
        candidate_asset_ids: set[str] = set()
        for _ in range(self._max_rounds):
            result = await provider.chat(messages, tools=_TOOL_SCHEMAS)
            calls = result.tool_calls or []
            if not calls:
                raise ValueError("media background agent returned no tool decision")
            messages.append({
                "role": "assistant",
                "content": result.content or "",
                "tool_calls": calls,
            })
            for call in calls:
                call_id, name, arguments = _parse_tool_call(call)
                if name == "keep_background":
                    return MediaBackgroundDecision(
                        decision="keep",
                        reason=_required_text(arguments, "reason"),
                    )
                if name == "switch_background":
                    asset_id = _required_text(arguments, "assetId")
                    if asset_id not in candidate_asset_ids:
                        raise ValueError(
                            "media background agent selected an asset that was not returned by search"
                        )
                    return MediaBackgroundDecision(
                        decision="switch",
                        asset_id=asset_id,
                        reason=_required_text(arguments, "reason"),
                    )
                if name not in {
                    "search_story_backgrounds",
                    "search_workspace_fallbacks",
                }:
                    raise ValueError(f"unknown media background tool: {name}")
                scope = (
                    models.MEDIA_LIBRARY_SCOPE_STORY
                    if name == "search_story_backgrounds"
                    else models.MEDIA_LIBRARY_SCOPE_WORKSPACE_FALLBACK
                )
                tags_raw = arguments.get("tags", [])
                if not isinstance(tags_raw, list):
                    raise ValueError("media background search tags must be an array")
                bundles = [
                    bundle
                    for bundle in self._data.search_library_assets(
                        workspace_id=source.workspace_id,
                        scope=scope,
                        story_id=(
                            source.story_id
                            if scope == models.MEDIA_LIBRARY_SCOPE_STORY
                            else None
                        ),
                        query=str(arguments.get("query", "")),
                        tags=tuple(str(tag) for tag in tags_raw),
                        limit=20,
                    )
                    if self._asset_exists(bundle.blob)
                ]
                tool_payload = [
                    {
                        "assetId": bundle.asset.id,
                        "title": bundle.item.title,
                        "description": bundle.item.description,
                        "tags": list(bundle.tags),
                        "default": bundle.item.is_default,
                    }
                    for bundle in bundles
                ]
                candidate_asset_ids.update(
                    bundle.asset.id
                    for bundle in bundles
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(tool_payload, ensure_ascii=False),
                })
        raise ValueError("media background agent exceeded the tool round limit")


_SYSTEM_PROMPT = """
你是独立的 RP 场景背景匹配 Agent，只负责从离线环境图库选择 Session Room 背景。
默认保持当前背景。只有地点、主要时段或长期环境阶段明确变化，而且候选明显更合适时才切换。
天气细节、人物情绪、短暂动作和普通对话不得触发换图。图片只表达环境，不匹配人物。
先搜索 Story 背景；Story 没有合适候选时才搜索 Workspace 通用兜底。
最终必须调用 keep_background 或 switch_background，不得只输出正文。
""".strip()


def _source_prompt(source: MediaBackgroundSourceSnapshot) -> str:
    turns = [
        {
            "turnId": turn.turn_id,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in turn.messages
            ],
        }
        for turn in source.turns
    ]
    return json.dumps(
        {
            "scene": dict(source.scene_attrs),
            "recentTurns": turns,
            "currentBackground": {
                "assetId": source.current_asset_id,
                "title": source.current_title,
            },
            "lastDecision": source.last_decision,
            "lastReason": source.last_reason,
        },
        ensure_ascii=False,
    )


def _parse_tool_call(call: object) -> tuple[str, str, dict[str, object]]:
    if not isinstance(call, dict):
        raise ValueError("media background tool call must be an object")
    function = call.get("function")
    if not isinstance(function, dict):
        raise ValueError("media background tool call is missing function")
    name = str(function.get("name", "")).strip()
    raw_arguments = function.get("arguments", {})
    if isinstance(raw_arguments, str):
        parsed = json.loads(raw_arguments or "{}")
    else:
        parsed = raw_arguments
    if not isinstance(parsed, dict):
        raise ValueError("media background tool arguments must be an object")
    return str(call.get("id", "")), name, dict(parsed)


def _required_text(arguments: dict[str, object], key: str) -> str:
    value = str(arguments.get(key, "")).strip()
    if not value:
        raise ValueError(f"media background tool requires {key}")
    return value


_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_story_backgrounds",
            "description": "Search backgrounds prepared specifically for the current Story.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query", "tags"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_workspace_fallbacks",
            "description": "Search generic fallback backgrounds in the current Workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["query", "tags"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "keep_background",
            "description": "Keep the current background when continuity is preferable.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_background",
            "description": "Switch to one asset returned by a search tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assetId": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["assetId", "reason"],
                "additionalProperties": False,
            },
        },
    },
]
