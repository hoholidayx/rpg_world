"""Independent real-LLM verifier for opt-in Agent turn acceptance tests."""

from __future__ import annotations

import json
from dataclasses import dataclass

from llm_client.types import LLMProvider, LLMResponse

TURN_EXECUTION_VERIFIER_TOOL_NAME = "verify_turn_execution"
TURN_EXECUTION_VERIFIER_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": TURN_EXECUTION_VERIFIER_TOOL_NAME,
        "description": "验证 RP 回复是否落实用户意图，并服从本轮裁定与已提交状态。",
        "parameters": {
            "type": "object",
            "properties": {
                "userIntentAddressed": {
                    "type": "boolean",
                    "description": "回复是否实际处理了用户本轮行动或要求，而非回避或只讨论规则。",
                },
                "outcomeRespected": {
                    "type": "boolean",
                    "description": "有 Outcome 时是否严格服从；没有 Outcome 时填 true。",
                },
                "stateConsistent": {
                    "type": "boolean",
                    "description": "回复是否与本轮提交后的 Scene 和普通状态一致且不矛盾。",
                },
                "playerAgencyPreserved": {
                    "type": "boolean",
                    "description": "非 GM turn 是否未替玩家补写未声明的台词、行动、决定或心理。",
                },
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "引用回复、Outcome 或状态中的简短证据。",
                    },
                    "maxItems": 8,
                },
                "reason": {
                    "type": "string",
                    "maxLength": 1000,
                    "description": "简洁解释整体判定。",
                },
            },
            "required": [
                "userIntentAddressed",
                "outcomeRespected",
                "stateConsistent",
                "playerAgencyPreserved",
                "evidence",
                "reason",
            ],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class TurnExecutionVerification:
    user_intent_addressed: bool
    outcome_respected: bool
    state_consistent: bool
    player_agency_preserved: bool
    evidence: tuple[str, ...]
    reason: str


async def verify_turn_execution(
    provider: LLMProvider,
    *,
    user_input: str,
    assistant_text: str,
    outcome: dict[str, object] | None,
    status_before: dict[str, dict[str, str]],
    status_after: dict[str, dict[str, str]],
    player_character_name: str,
    message_mode: str,
) -> TurnExecutionVerification:
    """Compare a committed turn and its final narrative using a fresh LLM call."""

    payload = {
        "messageMode": message_mode,
        "playerCharacter": player_character_name,
        "userInput": user_input,
        "narrativeOutcome": outcome,
        "statusBefore": status_before,
        "statusAfter": status_after,
        "assistantReply": assistant_text,
    }
    system_prompt = (
        "你是 RP 集成测试的独立验收器，不续写剧情。严格比较用户输入、Narrative "
        "Outcome、状态提交前后值与 assistant 回复。用户已经明确写出的行动不算越权；"
        "但非 GM turn 不得由 assistant 补写玩家未声明的台词、主动行动、决定或心理。"
        "状态无需在正文逐字段复述，但正文不得与已提交状态矛盾。必须且只能调用一次 "
        f"{TURN_EXECUTION_VERIFIER_TOOL_NAME}，不得输出普通正文。工具参数必须是严格"
        "合法的 JSON；字符串内优先使用中文引号。"
    )
    last_error: AssertionError | None = None
    for attempt in range(2):
        retry_suffix = (
            ""
            if attempt == 0
            else " 上一次响应不符合工具协议；本次只修正调用格式并重新判定。"
        )
        response = await provider.chat(
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
            tools=[TURN_EXECUTION_VERIFIER_SCHEMA],
        )
        try:
            return _verification_from_response(response)
        except AssertionError as exc:
            last_error = exc
    raise AssertionError(
        "Turn verifier failed to return a valid verification tool call twice"
    ) from last_error


def _verification_from_response(result: object) -> TurnExecutionVerification:
    if not isinstance(result, LLMResponse):
        raise AssertionError("Turn verifier provider returned an unsupported response")
    arguments = _single_arguments(result.tool_calls)
    evidence = arguments.get("evidence")
    reason = arguments.get("reason")
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) for item in evidence
    ):
        raise AssertionError("Turn verifier evidence must be a string array")
    if not isinstance(reason, str) or not reason.strip():
        raise AssertionError("Turn verifier reason must be a non-empty string")
    return TurnExecutionVerification(
        user_intent_addressed=_required_bool(arguments, "userIntentAddressed"),
        outcome_respected=_required_bool(arguments, "outcomeRespected"),
        state_consistent=_required_bool(arguments, "stateConsistent"),
        player_agency_preserved=_required_bool(
            arguments,
            "playerAgencyPreserved",
        ),
        evidence=tuple(item.strip() for item in evidence if item.strip()),
        reason=reason.strip(),
    )


def _single_arguments(tool_calls: object) -> dict[str, object]:
    if not isinstance(tool_calls, list):
        raise AssertionError("Turn verifier must return a tool call")
    matches: list[dict[str, object]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        source = function if isinstance(function, dict) else tool_call
        if source.get("name") != TURN_EXECUTION_VERIFIER_TOOL_NAME:
            continue
        raw_arguments = source.get("arguments")
        if isinstance(raw_arguments, str):
            try:
                raw_arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    "Turn verifier returned invalid JSON arguments"
                ) from exc
        if isinstance(raw_arguments, dict):
            matches.append(dict(raw_arguments))
    if len(matches) != 1:
        raise AssertionError(
            "Turn verifier must return exactly one verify_turn_execution call"
        )
    return matches[0]


def _required_bool(arguments: dict[str, object], key: str) -> bool:
    value = arguments.get(key)
    if not isinstance(value, bool):
        raise AssertionError(f"Turn verifier {key} must be a boolean")
    return value


__all__ = [
    "TURN_EXECUTION_VERIFIER_SCHEMA",
    "TURN_EXECUTION_VERIFIER_TOOL_NAME",
    "TurnExecutionVerification",
    "verify_turn_execution",
]
