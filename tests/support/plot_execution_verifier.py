"""Real-LLM semantic verifier used only by opt-in Plot acceptance tests."""

from __future__ import annotations

import json
from dataclasses import dataclass

from llm_client.types import LLMProvider, LLMResponse

PLOT_EXECUTION_VERIFIER_TOOL_NAME = "verify_plot_execution"
PLOT_EXECUTION_VERIFIER_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": PLOT_EXECUTION_VERIFIER_TOOL_NAME,
        "description": "验证一轮 RP 回复是否落实了引擎 Plot 指令及其组合约束。",
        "parameters": {
            "type": "object",
            "properties": {
                "plotExecuted": {
                    "type": "boolean",
                    "description": "回复是否在世界内实际开始或推进全部 Plot 指令，而非仅复述。",
                },
                "outcomeRespected": {
                    "type": "boolean",
                    "description": "有 Outcome 时是否服从其结果；没有 Outcome 时填 true。",
                },
                "statusConsistent": {
                    "type": "boolean",
                    "description": "回复是否与更新后的状态一致；状态未变化且无需变化时填 true。",
                },
                "playerAgencyPreserved": {
                    "type": "boolean",
                    "description": "非 GM turn 是否未代替玩家角色发言、行动、决策或描写心理。",
                },
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "使用中文引号引用原文，避免未转义的英文双引号。",
                    },
                    "maxItems": 8,
                    "description": "从回复或状态中摘录的简短证据。",
                },
                "reason": {
                    "type": "string",
                    "maxLength": 1000,
                    "description": "简洁解释整体判定；使用中文引号，避免英文双引号。",
                },
            },
            "required": [
                "plotExecuted",
                "outcomeRespected",
                "statusConsistent",
                "playerAgencyPreserved",
                "evidence",
                "reason",
            ],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class PlotExecutionVerification:
    plot_executed: bool
    outcome_respected: bool
    status_consistent: bool
    player_agency_preserved: bool
    evidence: tuple[str, ...]
    reason: str


async def verify_plot_execution(
    provider: LLMProvider,
    *,
    user_input: str,
    plot_directives: tuple[str, ...],
    assistant_text: str,
    outcome: dict[str, object] | None,
    status_before: dict[str, dict[str, str]],
    status_after: dict[str, dict[str, str]],
    player_character_name: str,
    message_mode: str = "neutral",
) -> PlotExecutionVerification:
    """Ask a real provider for one strict, evidence-backed verification tool call."""

    payload = {
        "messageMode": message_mode,
        "playerCharacter": player_character_name,
        "userInput": user_input,
        "plotDirectives": list(plot_directives),
        "narrativeOutcome": outcome,
        "statusBefore": status_before,
        "statusAfter": status_after,
        "assistantReply": assistant_text,
    }
    system_prompt = (
        "你是 RP 集成测试的独立验收器，不续写剧情。严格比较 Plot 指令、"
        "Outcome、状态前后值与 assistant 回复。Plot executed 只有在回复把事件"
        "作为世界内事实实际开始或推进时才为 true；仅提及、讨论、承诺稍后执行或"
        "复述后台要求均为 false。Outcome 优先于冲突的 Plot 完成方式。非 GM turn"
        "不得替玩家角色补写台词、主动行动、决定或心理。必须且只能调用一次 "
        f"{PLOT_EXECUTION_VERIFIER_TOOL_NAME}，不得输出普通正文。工具参数必须是"
        "严格合法的 JSON；字符串内使用中文引号，不得写未转义的英文双引号。"
    )
    last_error: AssertionError | None = None
    for attempt in range(2):
        retry_suffix = (
            ""
            if attempt == 0
            else " 上一次验收响应不符合工具协议；本次只修正工具调用格式并重新判定。"
        )
        result = await provider.chat(
            [
                {
                    "role": "system",
                    "content": f"{system_prompt}{retry_suffix}",
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, indent=2),
                },
            ],
            tools=[PLOT_EXECUTION_VERIFIER_SCHEMA],
        )
        try:
            return _verification_from_response(result)
        except AssertionError as exc:
            last_error = exc
    raise AssertionError(
        "Plot verifier failed to return a valid verification tool call twice"
    ) from last_error


def _verification_from_response(result: object) -> PlotExecutionVerification:
    if not isinstance(result, LLMResponse):
        raise AssertionError("Plot verifier provider returned an unsupported response")
    arguments = _single_verification_arguments(result.tool_calls)
    evidence = arguments.get("evidence")
    reason = arguments.get("reason")
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) for item in evidence
    ):
        raise AssertionError("Plot verifier evidence must be a string array")
    if not isinstance(reason, str) or not reason.strip():
        raise AssertionError("Plot verifier reason must be a non-empty string")
    return PlotExecutionVerification(
        plot_executed=_required_bool(arguments, "plotExecuted"),
        outcome_respected=_required_bool(arguments, "outcomeRespected"),
        status_consistent=_required_bool(arguments, "statusConsistent"),
        player_agency_preserved=_required_bool(
            arguments,
            "playerAgencyPreserved",
        ),
        evidence=tuple(item.strip() for item in evidence if item.strip()),
        reason=reason.strip(),
    )


def _single_verification_arguments(
    tool_calls: object,
) -> dict[str, object]:
    if not isinstance(tool_calls, list):
        raise AssertionError("Plot verifier must return a tool call")
    matches: list[dict[str, object]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        source = function if isinstance(function, dict) else tool_call
        if source.get("name") != PLOT_EXECUTION_VERIFIER_TOOL_NAME:
            continue
        raw_arguments = source.get("arguments")
        if isinstance(raw_arguments, str):
            try:
                raw_arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    "Plot verifier returned invalid JSON arguments"
                ) from exc
        if isinstance(raw_arguments, dict):
            matches.append(dict(raw_arguments))
    if len(matches) != 1:
        raise AssertionError(
            "Plot verifier must return exactly one verify_plot_execution call"
        )
    return matches[0]


def _required_bool(arguments: dict[str, object], key: str) -> bool:
    value = arguments.get(key)
    if not isinstance(value, bool):
        raise AssertionError(f"Plot verifier {key} must be a boolean")
    return value
