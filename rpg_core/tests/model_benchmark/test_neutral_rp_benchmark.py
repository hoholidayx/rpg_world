from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from llm_client.types import LLMResponse, LLMUsage
from tests.rp_model_benchmark.evaluation import (
    aggregate_metrics,
    evaluate_case_run,
)
from tests.rp_model_benchmark.loader import (
    RPBenchmarkInputError,
    load_dataset,
    select_cases,
    validate_canonical_dataset,
)
from tests.rp_model_benchmark.models import BenchmarkCategory, BenchmarkToolName
from tests.rp_model_benchmark.prompting import build_round_messages
from tests.rp_model_benchmark.reporting import BenchmarkRunWriter
from tests.rp_model_benchmark.review import finalize_review
from tests.rp_model_benchmark.runner import ProviderCallRecord, run_case
from tests.rp_model_benchmark.tools import BenchmarkToolRuntime


class _ScriptedProvider:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[dict], list[dict] | None]] = []

    def get_default_model(self) -> str:
        return "scripted-rp-model"

    async def chat(self, messages, tools=None):  # noqa: ANN001
        self.calls.append((deepcopy(messages), deepcopy(tools)))
        return self.responses.pop(0)

    async def chat_stream(self, messages, tools=None):  # noqa: ANN001
        raise NotImplementedError


def _case(case_id: str):
    return next(item for item in load_dataset().cases if item.id == case_id)


def test_canonical_dataset_has_frozen_balanced_shape() -> None:
    dataset = load_dataset()

    assert len(dataset.cases) == 48
    assert len(select_cases(dataset, "smoke")) == 12
    assert len(select_cases(dataset, "full")) == 48
    assert {
        category: sum(item.category is category for item in dataset.cases)
        for category in BenchmarkCategory
    } == {category: 6 for category in BenchmarkCategory}


def test_canonical_validator_rejects_distribution_drift() -> None:
    dataset = load_dataset()
    reduced = dataset.model_copy(update={"cases": dataset.cases[:-1]})

    with pytest.raises(RPBenchmarkInputError, match="requires 48 cases"):
        validate_canonical_dataset(reduced)


def test_prompt_uses_production_contract_without_story_pack() -> None:
    case = _case("agency_wait_for_npc")
    runtime = BenchmarkToolRuntime(case)

    messages = build_round_messages(case, runtime, [])
    rendered = "\n".join(str(item["content"]) for item in messages)

    assert "核心 RP 契约" in rendered
    assert "当前玩家扮演角色：江临" in rendered
    assert "runtime_context" in rendered
    assert "Story Pack" not in rendered
    assert "[lorebook]" not in rendered
    assert messages[-1] == {"role": "user", "content": case.user_input}


@pytest.mark.asyncio
async def test_outcome_schema_disappears_after_fixed_result() -> None:
    case = _case("tool_explicit_outcome")
    runtime = BenchmarkToolRuntime(case)

    assert [
        item["function"]["name"] for item in runtime.schemas() or []
    ] == [BenchmarkToolName.OUTCOME.value]
    result = await runtime.execute(
        BenchmarkToolName.OUTCOME.value,
        json.dumps({"reason": "设备能否坚持到发言结束", "actor": "柯言"}, ensure_ascii=False),
    )

    assert '"outcomeCode":"success"' in result
    assert runtime.schemas() is None
    projected = "\n".join(
        str(item["content"])
        for item in build_round_messages(case, runtime, [])
    )
    assert "本轮最终剧情结果" in projected
    assert "不得改判" in projected


@pytest.mark.asyncio
async def test_status_tool_uses_production_schema_and_in_memory_state() -> None:
    case = _case("tool_status_value_update")
    runtime = BenchmarkToolRuntime(case)

    result = await runtime.execute(
        BenchmarkToolName.STATUS_VALUES.value,
        json.dumps({
            "table_id": 1,
            "updates": [{"key": "顶灯", "value": "开启"}],
        }, ensure_ascii=False),
    )

    assert json.loads(result)["ok"] is True
    row = runtime.status.snapshot()[0]["document"]["rows"][0]
    assert row["value"] == "开启"


@pytest.mark.asyncio
async def test_runner_reprojects_after_tool_and_scores_result() -> None:
    case = _case("tool_explicit_outcome")
    provider = _ScriptedProvider([
        LLMResponse(
            content="",
            tool_calls=[{
                "id": "outcome-1",
                "type": "function",
                "function": {
                    "name": BenchmarkToolName.OUTCOME.value,
                    "arguments": json.dumps({
                        "reason": "设备能否坚持到发言结束",
                        "actor": "柯言",
                    }, ensure_ascii=False),
                },
            }],
            finish_reason="tool_calls",
        ),
        LLMResponse(
            content=(
                "<rp-narration>设备坚持到了发言结束，随后才熄灭。</rp-narration>"
            ),
            tool_calls=None,
            finish_reason="stop",
        ),
    ])
    calls: list[ProviderCallRecord] = []

    result = await run_case(
        provider,  # type: ignore[arg-type]
        provider_key="scripted",
        case=case,
        repeat=1,
        calls=calls,
    )

    assert result.provider_error is None
    assert result.tool_invocations[0]["name"] == BenchmarkToolName.OUTCOME.value
    assert all(item["passed"] for item in result.deterministic_checks)
    assert len(provider.calls) == 2
    assert provider.calls[1][1] is None
    assert "本轮最终剧情结果" in "\n".join(
        str(item["content"]) for item in provider.calls[1][0]
    )


def test_deterministic_evaluator_catches_fact_and_tool_violations() -> None:
    case = _case("fact_blue_cup")
    checks = evaluate_case_run(
        case,
        final_text="<rp-narration>桌上放着红色搪瓷杯。</rp-narration>",
        invocations=[{"name": "invented_tool", "arguments": {}, "result": "x"}],
        provider_error=None,
    )

    failed = {item.id for item in checks if not item.passed}
    assert "required_literal_0" in failed
    assert "forbidden_literal_0" in failed
    assert "no_unavailable_tool" in failed


@pytest.mark.asyncio
async def test_writer_records_cache_and_codex_finalizer_binds_evidence(tmp_path: Path) -> None:
    dataset = load_dataset()
    case = _case("fact_blue_cup")
    provider = _ScriptedProvider([LLMResponse(
        content=(
            "<rp-narration>蓝色搪瓷杯安静地放在桌上，周岚仍在窗边整理登记表。</rp-narration>"
        ),
        tool_calls=None,
        finish_reason="stop",
        usage=LLMUsage(
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            prompt_cache_hit_tokens=80,
        ),
    )])
    calls: list[ProviderCallRecord] = []
    result = await run_case(
        provider,  # type: ignore[arg-type]
        provider_key="scripted",
        case=case,
        repeat=1,
        calls=calls,
    )
    writer = BenchmarkRunWriter(
        report_root=tmp_path,
        dataset=dataset,
        metadata={"suite": "smoke"},
    )
    report = writer.finalize(
        dataset=dataset,
        selected_cases=[case],
        calls=calls,
        case_runs=[result],
    )

    assert report["usage"]["cacheHitRate"] == 0.8
    template = json.loads(
        (writer.run_dir / "codex-review-template.json").read_text(encoding="utf-8")
    )
    template["reviewedAt"] = "2026-08-01T12:00:00+08:00"
    for review in template["reviews"]:
        review["overallReason"] = "输出与权威事实和玩家边界一致。"
        for check in review["checks"]:
            check.update({
                "verdict": "pass",
                "confidence": "high",
                "reason": "输出引用了给定事实且未补写未知归属。",
                "evidence": [{
                    "source": "run",
                    "repeat": 1,
                    "field": "finalText",
                    "quote": "蓝色搪瓷杯",
                }],
            })
    (writer.run_dir / "codex-review.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    final = finalize_review(writer.run_dir)

    assert final["qualityStatus"] == "pass"
    assert final["semanticMetrics"]["scripted"]["passRate"] == 1.0


def test_repeat_metric_uses_tool_and_failure_decisions() -> None:
    base = {
        "providerKey": "p",
        "caseId": "c",
        "category": "tool_following",
        "toolSequence": ["rp_story_outcome"],
        "providerError": None,
        "deterministicChecks": [{"id": "x", "passed": True}],
    }
    metrics = aggregate_metrics([
        {**base, "repeat": 1},
        {**base, "repeat": 2},
    ])

    assert metrics["p"]["repeatDecisionConsistency"] == 1.0
