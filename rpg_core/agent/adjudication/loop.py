"""Bounded non-stream tool loop shared by engine adjudication stages."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from loguru import logger

from llm_client.contracts import require_llm_response
from llm_client.types import LLMProvider, LLMResponse
from rpg_core.agent.telemetry import CallRecord, TurnStats
from rpg_core.agent.tools.lookup import LookupToolSet
from rpg_core.context.fingerprint import (
    build_request_fingerprint,
    request_fingerprint_log_values,
)
from rpg_core.context.models import Message, Role
from rpg_core.settings import settings

_TAG = "[AdjudicationToolLoop]"

_MIXED_TERMINAL_FEEDBACK = json.dumps(
    {
        "ok": False,
        "errorCode": "terminal_tool_mixed_with_lookup",
        "message": (
            "同一响应同时请求了查询工具与终结工具；终结工具未执行。"
            "请先阅读查询结果，再在新的响应中单独作出终结决定。"
        ),
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
_TERMINAL_ONLY_NOTICE = (
    "历史与摘要查询的共享轮次已经用尽。现在必须仅根据已经提供的证据"
    "完成当前阶段；不得再请求查询工具。若阶段需要终结工具，只能在本次"
    "响应中单独调用它。"
)


@dataclass(frozen=True, slots=True)
class AdjudicationLoopResult:
    """Final stage response plus all provider calls made to reach it."""

    response: LLMResponse
    call_records: tuple[CallRecord, ...]
    lookup_rounds: int


@dataclass(frozen=True, slots=True)
class _ToolCall:
    raw: dict[str, object]
    call_id: str
    name: str
    arguments_json: str


async def run_adjudication_tool_loop(
    *,
    provider: LLMProvider,
    messages: list[Message],
    terminal_schemas: list[dict[str, object]],
    source: str,
    lookup_tools: LookupToolSet | None = None,
    max_lookup_tool_rounds: int = 5,
    turn_stats: TurnStats | None = None,
) -> AdjudicationLoopResult:
    """Allow bounded History/Summary lookup, then one terminal-only decision.

    One response containing any number of lookup tool calls consumes one
    lookup round. If a terminal tool is mixed into that response, it receives
    transient rejection feedback and is never executed. Once the lookup budget
    is exhausted, exactly one additional provider request is made with only the
    terminal schemas.
    """

    if (
        isinstance(max_lookup_tool_rounds, bool)
        or not isinstance(max_lookup_tool_rounds, int)
        or max_lookup_tool_rounds <= 0
    ):
        raise ValueError("max_lookup_tool_rounds must be a positive integer")

    terminal_names = _schema_names(terminal_schemas)
    if not terminal_names:
        raise ValueError("at least one terminal adjudication schema is required")
    if lookup_tools is not None and terminal_names & lookup_tools.names:
        raise ValueError("terminal and lookup tool names must not overlap")

    working_messages = list(messages)
    call_records: list[CallRecord] = []
    lookup_rounds = 0
    terminal_notice_added = False

    while True:
        lookup_enabled = (
            lookup_tools is not None
            and lookup_rounds < max_lookup_tool_rounds
        )
        if (
            not lookup_enabled
            and lookup_rounds > 0
            and not terminal_notice_added
        ):
            working_messages.append(Message(Role.SYSTEM, _TERMINAL_ONLY_NOTICE))
            terminal_notice_added = True

        schemas = [
            *(lookup_tools.schemas() if lookup_enabled and lookup_tools else []),
            *terminal_schemas,
        ]
        response, record = await _provider_call(
            provider=provider,
            messages=working_messages,
            schemas=schemas,
            source=source,
        )
        call_records.append(record)
        if turn_stats is not None:
            turn_stats.add_call(record)

        raw_tool_calls = response.tool_calls or []
        if not isinstance(raw_tool_calls, list):
            raise TypeError("LLM tool_calls must be an array or null")
        finish_reason = response.finish_reason
        if finish_reason == "tool_calls" and not raw_tool_calls:
            raise RuntimeError(
                "LLM reported finish_reason=tool_calls but returned no tool-call payload"
            )
        if not raw_tool_calls:
            return AdjudicationLoopResult(
                response=response,
                call_records=tuple(call_records),
                lookup_rounds=lookup_rounds,
            )

        calls = _normalize_tool_calls(
            raw_tool_calls,
            provider_call_index=len(call_records),
        )
        lookup_calls = [
            call
            for call in calls
            if lookup_tools is not None and call.name in lookup_tools.names
        ]
        if not lookup_calls or not lookup_enabled:
            return AdjudicationLoopResult(
                response=response,
                call_records=tuple(call_records),
                lookup_rounds=lookup_rounds,
            )

        lookup_rounds += 1
        working_messages.append(
            Message(
                role=Role.ASSISTANT,
                content=response.content,
                tool_calls=[call.raw for call in calls],
                reasoning_content=response.reasoning_content,
            )
        )
        has_non_lookup_call = len(lookup_calls) != len(calls)
        for call in calls:
            if call in lookup_calls:
                tool_result = await lookup_tools.execute(
                    call.name,
                    call.arguments_json,
                )
                _log_sensitive_lookup_execution(
                    source=source,
                    name=call.name,
                    arguments=call.arguments_json,
                    result=tool_result,
                )
            else:
                tool_result = _MIXED_TERMINAL_FEEDBACK
            working_messages.append(
                Message(
                    role=Role.TOOL,
                    content=str(tool_result),
                    tool_call_id=call.call_id,
                )
            )
        if has_non_lookup_call:
            logger.warning(
                _TAG
                + " mixed lookup/terminal response rejected: source={} tools={}",
                source,
                [call.name for call in calls],
            )


async def _provider_call(
    *,
    provider: LLMProvider,
    messages: list[Message],
    schemas: list[dict[str, object]],
    source: str,
) -> tuple[LLMResponse, CallRecord]:
    if settings.verbose_logging:
        fingerprint = build_request_fingerprint(messages, schemas)
        logger.info(
            _TAG + " request fingerprint: source={} contextHash={} "
            "contextChars={} systemHash={} systemChars={} toolsHash={} "
            "toolsChars={} messages={} roles={} tools={} messageShape={}",
            source,
            *request_fingerprint_log_values(fingerprint),
        )

    started_at = time.monotonic()
    response = require_llm_response(
        await provider.chat(
            [message.to_provider_dict() for message in messages],
            tools=schemas,
        ),
        f"rpg_core.adjudication:{source}",
    )
    duration_ms = (time.monotonic() - started_at) * 1000

    usage = response.usage
    model = response.model or provider.get_default_model()
    record = CallRecord(
        source=source,
        model=model,
        usage=usage,
        duration_ms=duration_ms,
        reasoning_content=response.reasoning_content,
    )
    if settings.verbose_logging:
        logger.info(
            _TAG
            + " provider call completed: source={} duration_ms={:.1f} model={} "
            "finish_reason={} tools={} usage={}",
            source,
            duration_ms,
            model,
            response.finish_reason or "-",
            [
                call.name
                for call in _normalize_tool_calls(
                    response.tool_calls or [],
                    provider_call_index=0,
                )
            ],
            str(usage) if usage is not None else "(no usage)",
        )
    return response, record


def _schema_names(schemas: list[dict[str, object]]) -> frozenset[str]:
    names: set[str] = set()
    for schema in schemas:
        function = schema.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "")
        if name:
            names.add(name)
    return frozenset(names)


def _normalize_tool_calls(
    raw_tool_calls: list[object],
    *,
    provider_call_index: int,
) -> list[_ToolCall]:
    result: list[_ToolCall] = []
    for index, raw_call in enumerate(raw_tool_calls):
        if not isinstance(raw_call, dict):
            raise TypeError("LLM tool_calls must contain objects")
        call = dict(raw_call)
        function = call.get("function")
        source = dict(function) if isinstance(function, dict) else call
        name = str(source.get("name") or "")
        raw_arguments = source.get("arguments", "{}")
        arguments_json = (
            raw_arguments
            if isinstance(raw_arguments, str)
            else json.dumps(
                raw_arguments,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        call_id = str(call.get("id") or "").strip() or (
            f"call_adjudication_{provider_call_index}_{index}"
        )
        call["id"] = call_id
        call["type"] = str(call.get("type") or "function")
        call["function"] = {
            "name": name,
            "arguments": arguments_json,
        }
        result.append(
            _ToolCall(
                raw=call,
                call_id=call_id,
                name=name,
                arguments_json=arguments_json,
            )
        )
    return result
def _log_sensitive_lookup_execution(
    *,
    source: str,
    name: str,
    arguments: str,
    result: str,
) -> None:
    if not settings.verbose_logging:
        return
    logger.info(
        _TAG
        + " lookup tool completed: source={} name={} arguments={} result={}",
        source,
        name,
        f"<redacted chars={len(arguments)}>",
        f"<redacted chars={len(result)}>",
    )
