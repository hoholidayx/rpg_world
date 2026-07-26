"""LLM-backed suitability judgment for soft plot scheduling candidates."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeAlias

from llm_client.keys import AGENT_PLOT_SCHEDULER_BIZ_KEY
from llm_client.types import LLMProvider, LLMResponse
from rpg_core.agent.adjudication import run_adjudication_tool_loop
from rpg_core.agent.telemetry import TurnStats
from rpg_core.agent.tools.lookup import LookupToolSet
from rpg_core.context.models import Message
from rpg_core.rp_modules.plot_scheduler.models import (
    PLOT_SUITABILITY_REASON_MAX_CHARS,
    PlotScheduleCandidate,
    PlotScheduleInjection,
    PlotSuitabilityDecision,
)
from rpg_core.settings import settings

PLOT_SUITABILITY_TOOL_NAME = "plot_schedule_decision"
PLOT_SUITABILITY_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": PLOT_SUITABILITY_TOOL_NAME,
        "description": "判断候选剧情事件此刻是否适合开始。",
        "parameters": {
            "type": "object",
            "properties": {
                "suitable": {
                    "type": "boolean",
                    "description": "当前 Scene、人物位置与状态是否允许事件合理开始。",
                },
                "reason": {
                    "type": "string",
                    "maxLength": PLOT_SUITABILITY_REASON_MAX_CHARS,
                    "description": "简短说明判断所依据的当前事实。",
                },
            },
            "required": ["suitable", "reason"],
            "additionalProperties": False,
        },
    },
}

_ProviderFactory: TypeAlias = Callable[[], Awaitable[LLMProvider]]


class PlotScheduleJudgeResponseError(ValueError):
    """Raised when the judge fails to return its one required tool result."""


class PlotScheduleJudge:
    def __init__(
        self,
        provider_factory: _ProviderFactory | None = None,
        *,
        lookup_tools: LookupToolSet | None = None,
        max_lookup_tool_rounds: int | None = None,
    ) -> None:
        self._provider_factory = provider_factory
        self._lookup_tools = lookup_tools
        self._max_lookup_tool_rounds = (
            max_lookup_tool_rounds
            if max_lookup_tool_rounds is not None
            else settings.adjudication_max_lookup_tool_rounds
        )

    async def judge(
        self,
        messages: list[Message],
        *,
        turn_stats: TurnStats,
    ) -> PlotSuitabilityDecision:
        provider = await self._provider()
        loop_result = await run_adjudication_tool_loop(
            provider=provider,
            messages=messages,
            terminal_schemas=[PLOT_SUITABILITY_SCHEMA],
            source="plot_scheduler",
            lookup_tools=self._lookup_tools,
            max_lookup_tool_rounds=self._max_lookup_tool_rounds,
            turn_stats=turn_stats,
        )
        result = loop_result.response
        if isinstance(result, LLMResponse):
            tool_calls: object = result.tool_calls
        elif isinstance(result, dict):
            tool_calls = result.get("tool_calls")
        else:
            raise PlotScheduleJudgeResponseError(
                "plot scheduler provider returned an unsupported response"
            )
        return self._parse_decision(tool_calls)

    async def _provider(self) -> LLMProvider:
        if self._provider_factory is not None:
            return await self._provider_factory()
        from llm_client.manager import LLMClientManager

        return await LLMClientManager.get().get_provider(
            AGENT_PLOT_SCHEDULER_BIZ_KEY
        )

    @staticmethod
    def _parse_decision(tool_calls: object) -> PlotSuitabilityDecision:
        if not isinstance(tool_calls, list):
            raise PlotScheduleJudgeResponseError(
                "plot scheduler must return a tool call"
            )
        matches: list[dict[str, object]] = []
        for raw_call in tool_calls:
            name, arguments = _normalize_tool_call(raw_call)
            if name == PLOT_SUITABILITY_TOOL_NAME:
                matches.append(arguments)
        if len(matches) != 1:
            raise PlotScheduleJudgeResponseError(
                "plot scheduler must return exactly one plot_schedule_decision"
            )
        arguments = matches[0]
        suitable = arguments.get("suitable")
        reason = arguments.get("reason")
        if not isinstance(suitable, bool):
            raise PlotScheduleJudgeResponseError("suitable must be a boolean")
        if not isinstance(reason, str) or not reason.strip():
            raise PlotScheduleJudgeResponseError("reason must be a non-empty string")
        normalized_reason = reason.strip()
        if len(normalized_reason) > PLOT_SUITABILITY_REASON_MAX_CHARS:
            raise PlotScheduleJudgeResponseError(
                "reason exceeds the plot scheduler length limit"
            )
        return PlotSuitabilityDecision(suitable=suitable, reason=normalized_reason)


def build_plot_judge_prompt(
    candidate: PlotScheduleCandidate,
    *,
    accepted_injections: Sequence[PlotScheduleInjection] = (),
) -> str:
    prior = [
        {
            "source": injection.source_kind,
            "event": injection.event_title,
            "directive": injection.directive,
        }
        for injection in accepted_injections
    ]
    payload = {
        "candidate": {
            "source": candidate.source_kind,
            "container": candidate.container_name,
            "event": candidate.event.title,
            "description": candidate.event.description,
            "suitabilityHint": candidate.event.suitability_hint,
            "scheduledTime": (
                candidate.scheduled_time.format()
                if candidate.scheduled_time is not None
                else None
            ),
            "directive": candidate.event.directive,
        },
        "alreadyAcceptedThisTurn": prior,
    }
    return (
        "你是剧情调度的软约束判定器。只判断候选事件能否从当前 Scene 合理开始，"
        "不得续写、改写或执行剧情。完整考虑当前地点、在场人物、状态表、最近对话和玩家本轮输入；"
        "若关键角色明确在别处、当前行动不可中断、事实条件冲突，判定为不适合。"
        "若本轮已有另一条调度，还必须判断两者能否兼容地同时开始。"
        "不要因为事件戏剧性强或尚未被对话提及就拒绝。必须且只能调用一次 "
        f"{PLOT_SUITABILITY_TOOL_NAME}，不得输出普通正文。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _normalize_tool_call(tool_call: object) -> tuple[str, dict[str, object]]:
    if not isinstance(tool_call, dict):
        return "", {}
    function = tool_call.get("function")
    source = function if isinstance(function, dict) else tool_call
    name = str(source.get("name", "") or "")
    raw_arguments = source.get("arguments", {})
    if isinstance(raw_arguments, dict):
        return name, dict(raw_arguments)
    if not isinstance(raw_arguments, str):
        return name, {}
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return name, {}
    return name, dict(parsed) if isinstance(parsed, dict) else {}
