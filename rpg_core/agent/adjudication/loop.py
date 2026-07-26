"""Bounded non-stream tool loop shared by engine adjudication stages."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TypeAlias

from loguru import logger

from llm_client.types import LLMProvider, LLMResponse, LLMUsage
from rpg_core.agent.telemetry import CallRecord, TurnStats
from rpg_core.agent.tools.history import HistoryToolSet
from rpg_core.context.fingerprint import (
    build_request_fingerprint,
    request_fingerprint_log_values,
)
from rpg_core.context.models import Message, Role
from rpg_core.settings import settings

_TAG = "[AdjudicationToolLoop]"
_LLMChatResult: TypeAlias = LLMResponse | dict[str, object]

_MIXED_TERMINAL_FEEDBACK = json.dumps(
    {
        "ok": False,
        "errorCode": "terminal_tool_mixed_with_history",
        "message": (
            "同一响应同时请求了历史查询与终结工具；终结工具未执行。"
            "请先阅读历史工具结果，再在新的响应中单独作出终结决定。"
        ),
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
_TERMINAL_ONLY_NOTICE = (
    "历史查询轮次已经用尽。现在必须仅根据已经提供的证据完成当前阶段；"
    "不得再请求历史工具。若阶段需要终结工具，只能在本次响应中单独调用它。"
)


@dataclass(frozen=True, slots=True)
class AdjudicationLoopResult:
    """Final stage response plus all provider calls made to reach it."""

    response: _LLMChatResult
    call_records: tuple[CallRecord, ...]
    history_rounds: int


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
    history_tools: HistoryToolSet | None = None,
    max_history_tool_rounds: int = 5,
    turn_stats: TurnStats | None = None,
) -> AdjudicationLoopResult:
    """Allow bounded history lookup, followed by one terminal-only decision.

    One response containing any number of history tool calls consumes one
    lookup round. If a terminal tool is mixed into that response, it receives
    transient rejection feedback and is never executed. Once the lookup budget
    is exhausted, exactly one additional provider request is made with only the
    terminal schemas.
    """

    if (
        isinstance(max_history_tool_rounds, bool)
        or not isinstance(max_history_tool_rounds, int)
        or max_history_tool_rounds <= 0
    ):
        raise ValueError("max_history_tool_rounds must be a positive integer")

    terminal_names = _schema_names(terminal_schemas)
    if not terminal_names:
        raise ValueError("at least one terminal adjudication schema is required")
    if history_tools is not None and terminal_names & history_tools.names:
        raise ValueError("terminal and history tool names must not overlap")

    working_messages = list(messages)
    call_records: list[CallRecord] = []
    history_rounds = 0
    terminal_notice_added = False

    while True:
        history_enabled = (
            history_tools is not None
            and history_rounds < max_history_tool_rounds
        )
        if (
            not history_enabled
            and history_rounds > 0
            and not terminal_notice_added
        ):
            working_messages.append(Message(Role.SYSTEM, _TERMINAL_ONLY_NOTICE))
            terminal_notice_added = True

        schemas = [
            *(history_tools.schemas() if history_enabled and history_tools else []),
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

        raw_tool_calls = _response_tool_calls(response)
        finish_reason = _response_finish_reason(response)
        if finish_reason == "tool_calls" and not raw_tool_calls:
            raise RuntimeError(
                "LLM reported finish_reason=tool_calls but returned no tool-call payload"
            )
        if not raw_tool_calls:
            return AdjudicationLoopResult(
                response=response,
                call_records=tuple(call_records),
                history_rounds=history_rounds,
            )

        calls = _normalize_tool_calls(
            raw_tool_calls,
            provider_call_index=len(call_records),
        )
        history_calls = [
            call
            for call in calls
            if history_tools is not None and call.name in history_tools.names
        ]
        if not history_calls or not history_enabled:
            return AdjudicationLoopResult(
                response=response,
                call_records=tuple(call_records),
                history_rounds=history_rounds,
            )

        history_rounds += 1
        working_messages.append(
            Message(
                role=Role.ASSISTANT,
                content=_response_content(response),
                tool_calls=[call.raw for call in calls],
                reasoning_content=_response_reasoning_content(response),
            )
        )
        has_non_history_call = len(history_calls) != len(calls)
        for call in calls:
            if call in history_calls:
                tool_result = await history_tools.execute(
                    call.name,
                    call.arguments_json,
                )
                _log_sensitive_history_execution(
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
        if has_non_history_call:
            logger.warning(
                _TAG
                + " mixed history/terminal response rejected: source={} tools={}",
                source,
                [call.name for call in calls],
            )


async def _provider_call(
    *,
    provider: LLMProvider,
    messages: list[Message],
    schemas: list[dict[str, object]],
    source: str,
) -> tuple[_LLMChatResult, CallRecord]:
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
    response = await provider.chat(
        [message.to_provider_dict() for message in messages],
        tools=schemas,
    )
    duration_ms = (time.monotonic() - started_at) * 1000
    if not isinstance(response, (LLMResponse, dict)):
        raise TypeError(
            "LLM provider chat() must return LLMResponse or a mapping test double"
        )

    usage = _response_usage(response)
    get_default_model = getattr(provider, "get_default_model", None)
    default_model = (
        str(get_default_model())
        if callable(get_default_model)
        else "unknown"
    )
    model = _response_model(response) or default_model
    record = CallRecord(
        source=source,
        model=model,
        usage=usage,
        duration_ms=duration_ms,
        reasoning_content=_response_reasoning_content(response),
    )
    if settings.verbose_logging:
        logger.info(
            _TAG
            + " provider call completed: source={} duration_ms={:.1f} model={} "
            "finish_reason={} tools={} usage={}",
            source,
            duration_ms,
            model,
            _response_finish_reason(response) or "-",
            [
                call.name
                for call in _normalize_tool_calls(
                    _response_tool_calls(response),
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


def _response_tool_calls(response: _LLMChatResult) -> list[object]:
    raw = (
        response.tool_calls
        if isinstance(response, LLMResponse)
        else response.get("tool_calls")
    )
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError("LLM tool_calls must be an array or null")
    return list(raw)


def _response_content(response: _LLMChatResult) -> str:
    value = (
        response.content
        if isinstance(response, LLMResponse)
        else response.get("content")
    )
    return str(value or "")


def _response_reasoning_content(response: _LLMChatResult) -> str | None:
    value = (
        response.reasoning_content
        if isinstance(response, LLMResponse)
        else response.get("reasoning_content")
    )
    return value if isinstance(value, str) and value.strip() else None


def _response_finish_reason(response: _LLMChatResult) -> str | None:
    value = (
        response.finish_reason
        if isinstance(response, LLMResponse)
        else response.get("finish_reason")
    )
    return str(value) if value not in (None, "") else None


def _response_model(response: _LLMChatResult) -> str:
    value = (
        response.model
        if isinstance(response, LLMResponse)
        else response.get("model")
    )
    return str(value or "")


def _response_usage(response: _LLMChatResult) -> LLMUsage | None:
    value = (
        response.usage
        if isinstance(response, LLMResponse)
        else response.get("usage")
    )
    return value if isinstance(value, LLMUsage) else None


def _log_sensitive_history_execution(
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
        + " history tool completed: source={} name={} arguments={} result={}",
        source,
        name,
        f"<redacted chars={len(arguments)}>",
        f"<redacted chars={len(result)}>",
    )
