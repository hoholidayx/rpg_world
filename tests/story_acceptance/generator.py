"""Independent natural-flow generation for Story Packs without a sidecar."""

from __future__ import annotations

import json
from typing import Any

from llm_client.types import LLMProvider, LLMResponse
from pydantic import ValidationError

from tests.story_acceptance.loader import LoadedStoryPack
from tests.story_acceptance.models import (
    StoryAcceptanceFlow,
    StoryAcceptanceStep,
)


STORY_FLOW_GENERATOR_TOOL_NAME = "propose_story_acceptance_flow"
STORY_FLOW_GENERATOR_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": STORY_FLOW_GENERATOR_TOOL_NAME,
        "description": (
            "根据 Story 定义提出自然的玩家输入；这些输入随后原样发送给 RPG Agent。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$",
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["neutral", "ic", "ooc", "gm"],
                            },
                            "input": {"type": "string", "minLength": 1},
                            "semanticRubric": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 4,
                            },
                        },
                        "required": ["id", "mode", "input", "semanticRubric"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["title", "steps"],
            "additionalProperties": False,
        },
    },
}


async def generate_natural_acceptance_flow(
    provider: LLMProvider,
    *,
    loaded: LoadedStoryPack,
) -> StoryAcceptanceFlow:
    """Generate a portable full-suite flow without telling the RPG Agent about tools."""

    pack = loaded.pack
    source = {
        "story": {
            "title": pack.story.title,
            "summary": pack.story.summary,
            "storyPrompt": pack.story.story_prompt,
        },
        "scene": [
            item.model_dump(by_alias=True)
            for item in pack.resources.status_tables
            if item.status_kind == "scene"
        ],
        "normalStatusTables": [
            {
                "stableId": item.stable_id,
                "name": item.name,
                "description": item.description,
                "rows": [row.model_dump(by_alias=True) for row in item.rows],
            }
            for item in pack.resources.status_tables
            if item.status_kind == "normal"
        ],
        "plotEvents": [
            {
                "stableId": item.stable_id,
                "title": item.title,
                "description": item.description,
                "suitabilityHint": item.suitability_hint,
                "scheduledTime": item.scheduled_time,
            }
            for item in pack.resources.plot_schedule.events
        ],
    }
    prompt = (
        "你是独立的 Story Pack 验收用例设计器。根据给定 Story、当前 Scene、"
        "状态表 description/row rule 与事件适宜性，提出 1—3 个能够检验故事运行"
        "语义的自然玩家输入。输入会原样发送给 RPG Agent，所以必须像真实玩家的"
        "剧情行动、GM 事实或 OOC 规划请求；不得出现工具名、schema、测试术语，"
        "不得要求模型调用函数或复述内部接口。不要预设随机交涉已经成功。"
        "优先选择当前 Scene 下合理、可观察、能由持久状态验证的动作；若不存在"
        "开放动态表，不要强行要求创建字段。每个 semanticRubric 只写故事语义，"
        "不要写实现细节。必须且只能调用一次 propose_story_acceptance_flow。"
    )
    last_error: Exception | None = None
    for attempt in range(2):
        response = await provider.chat(
            [
                {
                    "role": "system",
                    "content": prompt + (
                        " 上次格式无效，本次只修正协议。" if attempt else ""
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(source, ensure_ascii=False, indent=2),
                },
            ],
            tools=[STORY_FLOW_GENERATOR_SCHEMA],
        )
        try:
            arguments = _arguments(response)
            steps = [
                StoryAcceptanceStep.model_validate(item)
                for item in arguments["steps"]
            ]
            return StoryAcceptanceFlow(
                id="generated_story_actions",
                title=str(arguments["title"]),
                kind="generated",
                suites=["full"],
                steps=steps,
            )
        except (
            AssertionError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValidationError,
        ) as exc:
            last_error = exc
    raise AssertionError(
        "natural Story acceptance flow generator returned invalid data twice"
    ) from last_error


def _arguments(response: object) -> dict[str, Any]:
    if not isinstance(response, LLMResponse) or not isinstance(
        response.tool_calls, list
    ):
        raise AssertionError("flow generator did not return a tool call")
    matches: list[dict[str, Any]] = []
    for raw in response.tool_calls:
        if not isinstance(raw, dict):
            continue
        function = raw.get("function")
        source = function if isinstance(function, dict) else raw
        if source.get("name") != STORY_FLOW_GENERATOR_TOOL_NAME:
            continue
        arguments = source.get("arguments")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if isinstance(arguments, dict):
            matches.append(dict(arguments))
    if len(matches) != 1 or not isinstance(matches[0].get("steps"), list):
        raise AssertionError("flow generator must return one valid flow")
    return matches[0]


__all__ = [
    "STORY_FLOW_GENERATOR_SCHEMA",
    "STORY_FLOW_GENERATOR_TOOL_NAME",
    "generate_natural_acceptance_flow",
]
