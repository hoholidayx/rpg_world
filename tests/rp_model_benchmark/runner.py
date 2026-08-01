"""Provider-direct execution loop for the neutral RP benchmark."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from llm_client.types import LLMProvider, LLMResponse
from tests.rp_model_benchmark.evaluation import (
    checks_as_dict,
    evaluate_case_run,
)
from tests.rp_model_benchmark.models import RPBenchmarkCase
from tests.rp_model_benchmark.prompting import build_round_messages
from tests.rp_model_benchmark.tools import BenchmarkToolRuntime


@dataclass
class ProviderCallRecord:
    provider_key: str
    model: str
    case_id: str
    repeat: int
    round: int
    messages: list[dict[str, object]]
    tools: list[dict[str, object]] | None
    response: dict[str, object] | None = None
    duration_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class CaseRunResult:
    provider_key: str
    model: str
    case_id: str
    category: str
    repeat: int
    final_text: str
    tool_invocations: list[dict[str, object]]
    status_after: list[dict[str, object]]
    deterministic_checks: list[dict[str, object]]
    provider_error: str | None
    call_start: int
    call_end_exclusive: int
    mixed_text_tool_rounds: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "providerKey": self.provider_key,
            "model": self.model,
            "caseId": self.case_id,
            "category": self.category,
            "repeat": self.repeat,
            "finalText": self.final_text,
            "toolInvocations": self.tool_invocations,
            "toolSequence": [
                str(item.get("name", "")) for item in self.tool_invocations
            ],
            "statusAfter": self.status_after,
            "deterministicChecks": self.deterministic_checks,
            "providerError": self.provider_error,
            "callRange": {
                "start": self.call_start,
                "endExclusive": self.call_end_exclusive,
            },
            "mixedTextToolRounds": self.mixed_text_tool_rounds,
        }


async def run_case(
    provider: LLMProvider,
    *,
    provider_key: str,
    case: RPBenchmarkCase,
    repeat: int,
    calls: list[ProviderCallRecord],
    max_rounds: int = 4,
) -> CaseRunResult:
    runtime = BenchmarkToolRuntime(case)
    transcript: list[dict[str, object]] = []
    final_text = ""
    provider_error: str | None = None
    mixed_rounds = 0
    call_start = len(calls)

    for round_index in range(max_rounds):
        messages = build_round_messages(case, runtime, transcript)
        schemas = runtime.schemas()
        record = ProviderCallRecord(
            provider_key=provider_key,
            model=provider.get_default_model(),
            case_id=case.id,
            repeat=repeat,
            round=round_index,
            messages=messages,
            tools=schemas,
        )
        calls.append(record)
        started = time.perf_counter()
        try:
            response = await provider.chat(messages, tools=schemas)
        except Exception as exc:
            record.duration_ms = (time.perf_counter() - started) * 1000
            record.error_type = type(exc).__name__
            record.error_message = str(exc)
            provider_error = f"{type(exc).__name__}: {exc}"
            break
        record.duration_ms = (time.perf_counter() - started) * 1000
        record.response = _response_dict(response)
        raw_tool_calls = response.tool_calls or []
        if not raw_tool_calls:
            final_text = str(response.content or "")
            break
        if str(response.content or "").strip():
            mixed_rounds += 1
        transcript.append({
            "role": "assistant",
            "content": str(response.content or ""),
            "tool_calls": raw_tool_calls,
        })
        for index, raw_call in enumerate(raw_tool_calls):
            call_id, name, arguments = _decode_tool_call(raw_call, round_index, index)
            result = await runtime.execute(name, arguments)
            transcript.append({
                "role": "tool",
                "content": result,
                "tool_call_id": call_id,
            })
    else:
        provider_error = f"tool loop exceeded max_rounds={max_rounds}"

    checks = evaluate_case_run(
        case,
        final_text=final_text,
        invocations=runtime.state.invocations,
        provider_error=provider_error,
    )
    return CaseRunResult(
        provider_key=provider_key,
        model=provider.get_default_model(),
        case_id=case.id,
        category=case.category.value,
        repeat=repeat,
        final_text=final_text,
        tool_invocations=list(runtime.state.invocations),
        status_after=runtime.status.snapshot(),
        deterministic_checks=checks_as_dict(checks),
        provider_error=provider_error,
        call_start=call_start,
        call_end_exclusive=len(calls),
        mixed_text_tool_rounds=mixed_rounds,
    )


def _decode_tool_call(
    raw: Mapping[str, object],
    round_index: int,
    index: int,
) -> tuple[str, str, str]:
    function = raw.get("function")
    source = function if isinstance(function, Mapping) else raw
    name = str(source.get("name", ""))
    raw_arguments = source.get("arguments", "{}")
    arguments = (
        raw_arguments
        if isinstance(raw_arguments, str)
        else json.dumps(raw_arguments, ensure_ascii=False)
    )
    return (
        str(raw.get("id") or f"benchmark_{round_index}_{index}"),
        name,
        arguments,
    )


def _response_dict(response: LLMResponse) -> dict[str, object]:
    return {
        "content": str(response.content or ""),
        "toolCalls": response.tool_calls,
        "finishReason": response.finish_reason,
        "usage": asdict(response.usage) if response.usage is not None else None,
        "model": response.model,
        "requestId": response.request_id,
        "created": response.created,
    }


__all__ = ["CaseRunResult", "ProviderCallRecord", "run_case"]
