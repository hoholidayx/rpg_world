from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.story_acceptance.codex_review import (
    CodexReviewError,
    FINAL_REPORT_JSON,
    QUEUE_FILENAME,
    REVIEW_FILENAME,
    TEMPLATE_FILENAME,
    finalize_run,
    main,
)
from tests.story_acceptance.models import AcceptanceStatus
from tests.story_acceptance.reporting import AcceptanceReport, AcceptanceRunWriter


def _make_run(
    tmp_path: Path,
    *,
    deterministic_status: AcceptanceStatus = AcceptanceStatus.PASS,
    rubric: tuple[str, ...] = ("不得替玩家角色新增决定。",),
) -> Path:
    writer = AcceptanceRunWriter(
        report_root=tmp_path,
        pack_id="pack",
        run_metadata={
            "packId": "pack",
            "sourceRevision": "r000001",
            "sourceDigest": "a" * 64,
        },
    )
    writer.append_step({
        "flowId": "flow",
        "stepId": "step",
        "input": "我只观察眼前的情况。",
        "assistant": "门厅里只有雨声，没有替你作出任何决定。",
    })
    report = AcceptanceReport(
        pack_id="pack",
        source_revision="r000001",
        source_digest="a" * 64,
        suite="full",
    )
    report.add(
        check_id="deterministic",
        category="runtime",
        status=deterministic_status,
        summary="确定性检查",
    )
    report.add(
        check_id="flow.flow.step.semantic",
        category="semantic",
        status=AcceptanceStatus.NEEDS_REVIEW,
        summary="等待 Codex",
        flow_id="flow",
        step_id="step",
        details={"reviewQueueItem": True},
    )
    writer.finalize(
        report,
        calls=[],
        semantic_review_items=[{
            "checkId": "flow.flow.step.semantic",
            "flowId": "flow",
            "stepId": "step",
            "rubric": list(rubric),
            "assistantText": "门厅里只有雨声，没有替你作出任何决定。",
            "providerCallRange": {"start": 0, "endExclusive": 0},
        }],
    )
    return writer.run_dir


def _complete_review(
    run_dir: Path,
    *,
    verdict: str = "pass",
    confidence: str = "high",
    provider_refusal: bool = False,
    quote: str = "没有替你作出任何决定",
) -> dict:
    review = json.loads((run_dir / TEMPLATE_FILENAME).read_text(encoding="utf-8"))
    review["reviewedAt"] = "2026-08-01T00:00:00+00:00"
    for item in review["reviews"]:
        item["providerRefusal"] = provider_refusal
        item["overallReason"] = "根据步骤正文逐条核对。"
        for check in item["checks"]:
            check["verdict"] = verdict
            check["confidence"] = confidence
            check["reason"] = "正文保留了玩家能动性。"
            check["evidence"] = [{
                "artifact": "steps.jsonl",
                "flowId": "flow",
                "stepId": "step",
                "field": "assistant",
                "quote": quote,
            }]
    (run_dir / REVIEW_FILENAME).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return review


def test_pending_queue_cannot_be_finalized_without_codex_artifact(
    tmp_path: Path,
) -> None:
    run_dir = _make_run(tmp_path)

    assert (run_dir / QUEUE_FILENAME).is_file()
    assert (run_dir / TEMPLATE_FILENAME).is_file()
    raw_report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert raw_report["overallStatus"] == "needs_review"
    with pytest.raises(CodexReviewError, match="codex-review.json"):
        finalize_run(run_dir)


def test_medium_or_high_pass_writes_final_report_and_preserves_raw_report(
    tmp_path: Path,
) -> None:
    run_dir = _make_run(tmp_path)
    raw_before = (run_dir / "report.json").read_bytes()
    _complete_review(run_dir, confidence="medium")

    status, report = finalize_run(run_dir)

    assert status == "pass"
    assert report["overallStatus"] == "pass"
    assert report["counts"]["pass"] == 2
    assert (run_dir / FINAL_REPORT_JSON).is_file()
    assert (run_dir / "final-report.md").is_file()
    assert (run_dir / "report.json").read_bytes() == raw_before


@pytest.mark.parametrize(
    ("verdict", "confidence", "provider_refusal", "expected"),
    [
        ("fail", "high", False, "fail"),
        ("fail", "medium", False, "needs_review"),
        ("pass", "low", False, "needs_review"),
        ("pass", "high", True, "needs_review"),
        ("needs_review", "high", False, "needs_review"),
    ],
)
def test_review_tri_state_aggregation(
    tmp_path: Path,
    verdict: str,
    confidence: str,
    provider_refusal: bool,
    expected: str,
) -> None:
    run_dir = _make_run(tmp_path)
    _complete_review(
        run_dir,
        verdict=verdict,
        confidence=confidence,
        provider_refusal=provider_refusal,
    )

    status, _report = finalize_run(run_dir)

    assert status == expected


def test_deterministic_failure_cannot_be_overridden_by_codex(
    tmp_path: Path,
) -> None:
    run_dir = _make_run(
        tmp_path,
        deterministic_status=AcceptanceStatus.FAIL,
    )
    _complete_review(run_dir)

    status, report = finalize_run(run_dir)

    assert status == "fail"
    deterministic = next(
        item for item in report["checks"] if item["id"] == "deterministic"
    )
    assert deterministic["status"] == "fail"


def test_review_binding_and_evidence_quote_are_verified(
    tmp_path: Path,
) -> None:
    run_dir = _make_run(tmp_path)
    review = _complete_review(run_dir, quote="不存在的证据")

    with pytest.raises(CodexReviewError, match="quote is absent"):
        finalize_run(run_dir)

    review["binding"]["queueSha256"] = "0" * 64
    (run_dir / REVIEW_FILENAME).write_text(
        json.dumps(review, ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(CodexReviewError, match="binding"):
        finalize_run(run_dir)


def test_each_original_rubric_occurrence_must_appear_once(
    tmp_path: Path,
) -> None:
    run_dir = _make_run(
        tmp_path,
        rubric=("同一原文", "同一原文"),
    )
    review = _complete_review(run_dir)
    review["reviews"][0]["checks"].pop()
    (run_dir / REVIEW_FILENAME).write_text(
        json.dumps(review, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(CodexReviewError, match="each original rubric"):
        finalize_run(run_dir)


def test_cli_returns_zero_only_for_final_pass(tmp_path: Path) -> None:
    passing = _make_run(tmp_path / "pass")
    _complete_review(passing)
    pending = _make_run(tmp_path / "pending")
    _complete_review(pending, confidence="low")

    assert main(["finalize", "--run-dir", str(passing)]) == 0
    assert main(["finalize", "--run-dir", str(pending)]) == 1
