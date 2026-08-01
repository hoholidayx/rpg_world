from __future__ import annotations

import json
from pathlib import Path

from tests.story_acceptance.models import AcceptanceStatus
from tests.story_acceptance.reporting import (
    AcceptanceReport,
    AcceptanceRunWriter,
    redact_for_log,
    summarize_live_calls,
)
from tests.support.live_agent import RecordedLiveCall, strip_private_reasoning


def _report() -> AcceptanceReport:
    return AcceptanceReport(
        pack_id="pack",
        source_revision="r000001",
        source_digest="a" * 64,
        suite="smoke",
    )


def test_report_status_precedence_and_review_items() -> None:
    report = _report()
    report.add(
        check_id="pass",
        category="test",
        status=AcceptanceStatus.PASS,
        summary="ok",
    )
    report.add(
        check_id="review",
        category="semantic",
        status=AcceptanceStatus.NEEDS_REVIEW,
        summary="review",
    )
    assert report.overall_status is AcceptanceStatus.NEEDS_REVIEW
    assert [item.id for item in report.review_items] == ["review"]

    report.add(
        check_id="failure",
        category="test",
        status=AcceptanceStatus.FAIL,
        summary="failed",
    )
    assert report.overall_status is AcceptanceStatus.FAIL


def test_recursive_redaction_covers_exception_text() -> None:
    value = redact_for_log({
        "Authorization": "Bearer should-not-survive",
        "error": "request failed; x-api-key=super-secret-value; sk-abcdefghijklmnop",
        "nested": [{"access_token": "also-secret"}],
    })

    rendered = json.dumps(value)
    assert "should-not-survive" not in rendered
    assert "super-secret-value" not in rendered
    assert "abcdefghijklmnop" not in rendered
    assert "also-secret" not in rendered
    assert rendered.count("<redacted>") >= 4


def test_private_reasoning_is_omitted_from_capture_and_log_redaction() -> None:
    value = {
        "messages": [{
            "role": "assistant",
            "content": "observable",
            "reasoning_content": "private chain of thought",
            "nested": {"thinkingContent": "also private"},
        }]
    }

    captured = strip_private_reasoning(value)
    logged = redact_for_log(value)

    assert captured == {
        "messages": [{
            "role": "assistant",
            "content": "observable",
            "nested": {},
        }]
    }
    rendered = json.dumps(logged)
    assert "private chain of thought" not in rendered
    assert "also private" not in rendered
    assert "observable" in rendered


def test_writer_and_usage_summary(tmp_path: Path) -> None:
    calls = [
        RecordedLiveCall(
            biz_key="agent.main",
            messages=[{"role": "user", "content": "hello"}],
            tools=None,
            provider_key="remote",
            configured_model="model",
            response={
                "content": "ok",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                    "prompt_cache_hit_tokens": 4,
                },
            },
            duration_ms=12.5,
        )
    ]
    summary = summarize_live_calls(calls)
    assert summary["callCount"] == 1
    assert summary["totalTokens"] == 13
    assert summary["cachedTokens"] == 4
    assert summary["byBiz"]["agent.main"]["durationMs"] == 12.5

    writer = AcceptanceRunWriter(
        report_root=tmp_path,
        pack_id="pack",
        run_metadata={"apiKey": "must-be-redacted"},
    )
    writer.append_step({"id": "step"})
    writer.write_json_artifact("effective-profile.json", {"secret": "value"})
    report = _report()
    writer.finalize(report, calls=calls, final_metadata={"usage": summary})

    assert (writer.run_dir / "calls.jsonl").is_file()
    assert (writer.run_dir / "steps.jsonl").is_file()
    assert (writer.run_dir / "report.md").is_file()
    run = json.loads((writer.run_dir / "run.json").read_text())
    assert run["apiKey"] == "<redacted>"


def test_writer_rejects_artifact_path_escape(tmp_path: Path) -> None:
    writer = AcceptanceRunWriter(
        report_root=tmp_path,
        pack_id="pack",
        run_metadata={},
    )
    try:
        writer.write_json_artifact("../outside.json", {})
    except ValueError:
        pass
    else:
        raise AssertionError("path escape should be rejected")
