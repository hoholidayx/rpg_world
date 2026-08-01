"""Offline Codex semantic review binding and final report generation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


QUEUE_SCHEMA_VERSION = "story-acceptance-codex-review-queue/1.0"
REVIEW_SCHEMA_VERSION = "story-acceptance-codex-review/1.0"
FINAL_REPORT_SCHEMA_VERSION = "story-acceptance-final-report/1.0"
QUEUE_FILENAME = "semantic-review-queue.json"
TEMPLATE_FILENAME = "codex-review-template.json"
REVIEW_FILENAME = "codex-review.json"
FINAL_REPORT_JSON = "final-report.json"
FINAL_REPORT_MARKDOWN = "final-report.md"

_VERDICTS = frozenset({"pass", "fail", "needs_review"})
_CONFIDENCES = frozenset({"low", "medium", "high"})
_EVIDENCE_ARTIFACTS = frozenset({
    "steps.jsonl",
    "calls.jsonl",
    QUEUE_FILENAME,
})


class CodexReviewError(ValueError):
    """Review artifact or evidence does not match the captured run."""


def build_review_queue(
    *,
    run_id: str,
    pack_id: str,
    source_revision: str,
    source_digest: str,
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the immutable evidence queue written beside the raw report."""

    normalized_items = [dict(item) for item in items]
    check_ids = [str(item.get("checkId", "")) for item in normalized_items]
    if any(not check_id for check_id in check_ids):
        raise CodexReviewError("semantic review queue items require checkId")
    if len(check_ids) != len(set(check_ids)):
        raise CodexReviewError("semantic review queue checkId values must be unique")
    for item in normalized_items:
        rubric = item.get("rubric")
        if not isinstance(rubric, list) or not rubric or not all(
            isinstance(rule, str) and rule.strip() for rule in rubric
        ):
            raise CodexReviewError(
                f"semantic review item {item['checkId']!r} requires rubric strings"
            )
    return {
        "schemaVersion": QUEUE_SCHEMA_VERSION,
        "runId": str(run_id),
        "packId": str(pack_id),
        "sourceRevision": str(source_revision),
        "sourceDigest": str(source_digest),
        "items": normalized_items,
    }


def build_review_template(
    queue: Mapping[str, Any],
    *,
    queue_sha256: str,
) -> dict[str, Any]:
    """Create a deliberately incomplete artifact for Codex to fill."""

    return {
        "schemaVersion": REVIEW_SCHEMA_VERSION,
        "reviewer": "codex",
        "reviewedAt": "__REQUIRED_ISO8601__",
        "binding": {
            "runId": queue["runId"],
            "packId": queue["packId"],
            "sourceRevision": queue["sourceRevision"],
            "sourceDigest": queue["sourceDigest"],
            "queueSha256": queue_sha256,
        },
        "reviews": [
            {
                "checkId": item["checkId"],
                "flowId": item["flowId"],
                "stepId": item["stepId"],
                "providerRefusal": False,
                "overallReason": "__REQUIRED__",
                "checks": [
                    {
                        "ruleIndex": index,
                        "rule": rule,
                        "verdict": "__REQUIRED__",
                        "confidence": "__REQUIRED__",
                        "reason": "__REQUIRED__",
                        "evidence": [],
                    }
                    for index, rule in enumerate(item["rubric"])
                ],
            }
            for item in queue["items"]
        ],
    }


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finalize_run(run_dir: str | Path) -> tuple[str, dict[str, Any]]:
    """Validate Codex review evidence and write immutable final reports."""

    root = Path(run_dir).expanduser().resolve()
    run = _load_json(root / "run.json")
    raw_report = _load_json(root / "report.json")
    queue = _load_json(root / QUEUE_FILENAME)
    review = _load_json(root / REVIEW_FILENAME)
    queue_sha256 = sha256_file(root / QUEUE_FILENAME)

    _validate_queue_identity(queue, run, raw_report)
    _validate_review_binding(review, queue, queue_sha256)
    reviewed_checks = _validate_reviews(
        root=root,
        queue=queue,
        review=review,
    )
    final_checks = _merge_final_checks(
        raw_report=raw_report,
        reviewed_checks=reviewed_checks,
    )
    counts = _status_counts(final_checks)
    overall = _overall_status(final_checks)
    final_report = {
        "schemaVersion": FINAL_REPORT_SCHEMA_VERSION,
        "runId": queue["runId"],
        "packId": queue["packId"],
        "sourceRevision": queue["sourceRevision"],
        "sourceDigest": queue["sourceDigest"],
        "suite": raw_report.get("suite"),
        "overallStatus": overall,
        "counts": counts,
        "reviewBinding": {
            "reviewer": review["reviewer"],
            "reviewedAt": review["reviewedAt"],
            "queueSha256": queue_sha256,
            "reviewArtifact": REVIEW_FILENAME,
            "rawReport": "report.json",
        },
        "checks": final_checks,
    }
    _write_json(root / FINAL_REPORT_JSON, final_report)
    (root / FINAL_REPORT_MARKDOWN).write_text(
        _final_markdown(final_report),
        encoding="utf-8",
    )
    return overall, final_report


def _validate_queue_identity(
    queue: Mapping[str, Any],
    run: Mapping[str, Any],
    raw_report: Mapping[str, Any],
) -> None:
    if queue.get("schemaVersion") != QUEUE_SCHEMA_VERSION:
        raise CodexReviewError("unsupported semantic review queue schema")
    expected = {
        "runId": run.get("runId"),
        "packId": raw_report.get("packId"),
        "sourceRevision": raw_report.get("sourceRevision"),
        "sourceDigest": raw_report.get("sourceDigest"),
    }
    for key, value in expected.items():
        if queue.get(key) != value:
            raise CodexReviewError(
                f"semantic review queue {key} does not match captured run"
            )
    items = queue.get("items")
    if not isinstance(items, list):
        raise CodexReviewError("semantic review queue items must be an array")
    check_ids: list[str | None] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise CodexReviewError("semantic review queue item must be an object")
        check_id = item.get("checkId")
        flow_id = item.get("flowId")
        step_id = item.get("stepId")
        rubric = item.get("rubric")
        call_range = item.get("providerCallRange")
        if not isinstance(flow_id, str) or not flow_id:
            raise CodexReviewError("semantic review queue item requires flowId")
        if not isinstance(step_id, str) or not step_id:
            raise CodexReviewError("semantic review queue item requires stepId")
        if not isinstance(rubric, list) or not rubric or not all(
            isinstance(rule, str) and rule.strip() for rule in rubric
        ):
            raise CodexReviewError("semantic review queue item requires rubric")
        if not isinstance(call_range, Mapping):
            raise CodexReviewError(
                "semantic review queue item requires providerCallRange"
            )
        start = call_range.get("start")
        end = call_range.get("endExclusive")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end < start
        ):
            raise CodexReviewError(
                "semantic review queue providerCallRange is invalid"
            )
        check_ids.append(check_id if isinstance(check_id, str) else None)
    if any(not isinstance(value, str) or not value for value in check_ids):
        raise CodexReviewError("semantic review queue contains invalid checkId")
    if len(check_ids) != len(set(check_ids)):
        raise CodexReviewError("semantic review queue contains duplicate checkId")


def _validate_review_binding(
    review: Mapping[str, Any],
    queue: Mapping[str, Any],
    queue_sha256: str,
) -> None:
    if review.get("schemaVersion") != REVIEW_SCHEMA_VERSION:
        raise CodexReviewError("unsupported Codex review schema")
    if review.get("reviewer") != "codex":
        raise CodexReviewError("semantic review artifact reviewer must be codex")
    reviewed_at = review.get("reviewedAt")
    if not isinstance(reviewed_at, str) or reviewed_at.startswith("__"):
        raise CodexReviewError("Codex review reviewedAt must be completed")
    try:
        datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CodexReviewError("Codex review reviewedAt must be ISO-8601") from exc
    binding = review.get("binding")
    if not isinstance(binding, Mapping):
        raise CodexReviewError("Codex review binding is required")
    expected = {
        "runId": queue["runId"],
        "packId": queue["packId"],
        "sourceRevision": queue["sourceRevision"],
        "sourceDigest": queue["sourceDigest"],
        "queueSha256": queue_sha256,
    }
    if dict(binding) != expected:
        raise CodexReviewError("Codex review binding does not match queue bytes")


def _validate_reviews(
    *,
    root: Path,
    queue: Mapping[str, Any],
    review: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    queue_items = {
        item["checkId"]: item
        for item in queue["items"]
    }
    raw_reviews = review.get("reviews")
    if not isinstance(raw_reviews, list):
        raise CodexReviewError("Codex review reviews must be an array")
    review_ids = [
        item.get("checkId") if isinstance(item, Mapping) else None
        for item in raw_reviews
    ]
    if Counter(review_ids) != Counter(queue_items.keys()):
        raise CodexReviewError(
            "Codex review must cover every queued check exactly once"
        )

    artifacts = _load_evidence_artifacts(root)
    results: dict[str, dict[str, Any]] = {}
    for raw_review in raw_reviews:
        if not isinstance(raw_review, Mapping):
            raise CodexReviewError("Codex review item must be an object")
        check_id = str(raw_review["checkId"])
        queue_item = queue_items[check_id]
        for key in ("flowId", "stepId"):
            if raw_review.get(key) != queue_item.get(key):
                raise CodexReviewError(
                    f"Codex review {check_id} {key} does not match queue"
                )
        provider_refusal = raw_review.get("providerRefusal")
        if not isinstance(provider_refusal, bool):
            raise CodexReviewError(
                f"Codex review {check_id} providerRefusal must be boolean"
            )
        overall_reason = raw_review.get("overallReason")
        if (
            not isinstance(overall_reason, str)
            or not overall_reason.strip()
            or overall_reason.startswith("__")
        ):
            raise CodexReviewError(
                f"Codex review {check_id} overallReason is required"
            )
        checks = _validate_rule_checks(
            queue_item=queue_item,
            raw_checks=raw_review.get("checks"),
            artifacts=artifacts,
        )
        status = _review_status(
            provider_refusal=provider_refusal,
            checks=checks,
        )
        results[check_id] = {
            "id": check_id,
            "category": "semantic",
            "status": status,
            "summary": _review_summary(status, provider_refusal),
            "evidence": [
                _evidence_label(evidence)
                for check in checks
                for evidence in check["evidence"]
            ],
            "flowId": queue_item["flowId"],
            "stepId": queue_item["stepId"],
            "details": {
                "reviewer": "codex",
                "providerRefusal": provider_refusal,
                "overallReason": overall_reason.strip(),
                "checks": checks,
            },
        }
    return results


def _validate_rule_checks(
    *,
    queue_item: Mapping[str, Any],
    raw_checks: Any,
    artifacts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rubric = queue_item.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        raise CodexReviewError(
            f"semantic review queue item {queue_item.get('checkId')} has no rubric"
        )
    if not isinstance(raw_checks, list):
        raise CodexReviewError("Codex review checks must be an array")
    if not all(isinstance(check, Mapping) for check in raw_checks):
        raise CodexReviewError("Codex review rule check must be an object")
    indexes = [check.get("ruleIndex") for check in raw_checks]
    if not all(isinstance(index, int) for index in indexes):
        raise CodexReviewError("Codex review ruleIndex must be an integer")
    if Counter(indexes) != Counter(range(len(rubric))):
        raise CodexReviewError(
            "Codex review must cover each original rubric occurrence exactly once"
        )
    normalized: list[dict[str, Any]] = []
    for raw in sorted(raw_checks, key=lambda value: int(value["ruleIndex"])):
        index = int(raw["ruleIndex"])
        if raw.get("rule") != rubric[index]:
            raise CodexReviewError(
                f"Codex review ruleIndex {index} rewrites the original rubric"
            )
        verdict = raw.get("verdict")
        confidence = raw.get("confidence")
        reason = raw.get("reason")
        if verdict not in _VERDICTS:
            raise CodexReviewError("Codex review verdict is incomplete or invalid")
        if confidence not in _CONFIDENCES:
            raise CodexReviewError("Codex review confidence is incomplete or invalid")
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or reason.startswith("__")
        ):
            raise CodexReviewError("Codex review rule reason is required")
        evidence = raw.get("evidence")
        if not isinstance(evidence, list):
            raise CodexReviewError("Codex review evidence must be an array")
        normalized_evidence = [
            _validate_evidence(
                evidence_item=item,
                queue_item=queue_item,
                artifacts=artifacts,
            )
            for item in evidence
        ]
        if verdict in {"pass", "fail"} and not normalized_evidence:
            raise CodexReviewError(
                "Codex pass/fail requires at least one validated evidence quote"
            )
        normalized.append({
            "ruleIndex": index,
            "rule": rubric[index],
            "verdict": verdict,
            "confidence": confidence,
            "reason": reason.strip(),
            "evidence": normalized_evidence,
        })
    return normalized


def _validate_evidence(
    *,
    evidence_item: Any,
    queue_item: Mapping[str, Any],
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(evidence_item, Mapping):
        raise CodexReviewError("Codex evidence must be an object")
    artifact = evidence_item.get("artifact")
    field = evidence_item.get("field")
    quote = evidence_item.get("quote")
    if artifact not in _EVIDENCE_ARTIFACTS:
        raise CodexReviewError(f"unsupported Codex evidence artifact: {artifact!r}")
    if not isinstance(field, str) or not field.strip():
        raise CodexReviewError("Codex evidence field is required")
    if not isinstance(quote, str) or not quote.strip():
        raise CodexReviewError("Codex evidence quote is required")

    normalized = dict(evidence_item)
    if artifact == "calls.jsonl":
        call_index = evidence_item.get("callIndex")
        if not isinstance(call_index, int):
            raise CodexReviewError("calls.jsonl evidence requires callIndex")
        call_range = queue_item.get("providerCallRange")
        if not isinstance(call_range, Mapping) or not (
            int(call_range.get("start", -1))
            <= call_index
            < int(call_range.get("endExclusive", -1))
        ):
            raise CodexReviewError(
                "Codex call evidence is outside the queued step call range"
            )
        source = artifacts[artifact].get(call_index)
        if source is None:
            raise CodexReviewError(f"calls.jsonl has no call index {call_index}")
    elif artifact == "steps.jsonl":
        _validate_step_locator(evidence_item, queue_item)
        key = (queue_item["flowId"], queue_item["stepId"])
        source = artifacts[artifact].get(key)
        if source is None:
            raise CodexReviewError(f"steps.jsonl has no step {key!r}")
    else:
        _validate_step_locator(evidence_item, queue_item)
        source = queue_item

    value = _resolve_field(source, field)
    rendered = value if isinstance(value, str) else json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )
    if quote not in rendered:
        raise CodexReviewError(
            f"Codex evidence quote is absent from {artifact}:{field}"
        )
    return normalized


def _validate_step_locator(
    evidence: Mapping[str, Any],
    queue_item: Mapping[str, Any],
) -> None:
    if (
        evidence.get("flowId") != queue_item.get("flowId")
        or evidence.get("stepId") != queue_item.get("stepId")
    ):
        raise CodexReviewError(
            "step evidence flowId/stepId does not match queued item"
        )


def _load_evidence_artifacts(root: Path) -> dict[str, Any]:
    steps: dict[tuple[str, str], dict[str, Any]] = {}
    for item in _load_jsonl(root / "steps.jsonl"):
        key = (item.get("flowId"), item.get("stepId"))
        if all(isinstance(value, str) for value in key):
            steps[key] = item
    calls = {
        int(item["index"]): item
        for item in _load_jsonl(root / "calls.jsonl")
        if isinstance(item.get("index"), int)
    }
    return {
        "steps.jsonl": steps,
        "calls.jsonl": calls,
        QUEUE_FILENAME: _load_json(root / QUEUE_FILENAME),
    }


def _resolve_field(source: Any, field: str) -> Any:
    current = source
    for segment in field.split("."):
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
            continue
        if isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if 0 <= index < len(current):
                current = current[index]
                continue
        raise CodexReviewError(f"Codex evidence field does not exist: {field!r}")
    return current


def _review_status(
    *,
    provider_refusal: bool,
    checks: Sequence[Mapping[str, Any]],
) -> str:
    if provider_refusal:
        return "needs_review"
    if any(
        item["verdict"] == "fail" and item["confidence"] == "high"
        for item in checks
    ):
        return "fail"
    if all(
        item["verdict"] == "pass"
        and item["confidence"] in {"medium", "high"}
        for item in checks
    ):
        return "pass"
    return "needs_review"


def _review_summary(status: str, provider_refusal: bool) -> str:
    if provider_refusal:
        return "Codex 识别被测 Provider 拒答，保留人工复核"
    if status == "pass":
        return "Codex 依据运行证据判定语义规则通过"
    if status == "fail":
        return "Codex 依据运行证据判定存在高置信语义违例"
    return "Codex 证据不足、置信度不足或结论不确定，保留人工复核"


def _merge_final_checks(
    *,
    raw_report: Mapping[str, Any],
    reviewed_checks: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    raw_checks = raw_report.get("checks")
    if not isinstance(raw_checks, list):
        raise CodexReviewError("raw report checks must be an array")
    raw_id_values = [
        item.get("id")
        for item in raw_checks
        if isinstance(item, Mapping)
    ]
    if len(raw_id_values) != len(raw_checks) or any(
        not isinstance(check_id, str) or not check_id
        for check_id in raw_id_values
    ):
        raise CodexReviewError("raw report contains an invalid check")
    if len(raw_id_values) != len(set(raw_id_values)):
        raise CodexReviewError("raw report contains duplicate check ids")
    raw_ids = set(raw_id_values)
    missing = sorted(set(reviewed_checks).difference(raw_ids))
    if missing:
        raise CodexReviewError(
            f"queued semantic checks are absent from raw report: {missing}"
        )
    result: list[dict[str, Any]] = []
    for item in raw_checks:
        if not isinstance(item, Mapping):
            raise CodexReviewError("raw report check must be an object")
        check_id = item.get("id")
        replacement = reviewed_checks.get(str(check_id))
        result.append(dict(replacement) if replacement is not None else dict(item))
    return result


def _overall_status(checks: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in checks}
    if "infrastructure_error" in statuses:
        return "infrastructure_error"
    if "fail" in statuses:
        return "fail"
    if "needs_review" in statuses:
        return "needs_review"
    if statuses and statuses <= {"not_applicable"}:
        return "not_applicable"
    return "pass"


def _status_counts(checks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    values = (
        "pass",
        "fail",
        "needs_review",
        "not_applicable",
        "infrastructure_error",
    )
    return {
        status: sum(str(item.get("status")) == status for item in checks)
        for status in values
    }


def _evidence_label(evidence: Mapping[str, Any]) -> str:
    locator = (
        f"callIndex={evidence['callIndex']}"
        if "callIndex" in evidence
        else f"flow={evidence.get('flowId')},step={evidence.get('stepId')}"
    )
    return (
        f"{evidence['artifact']}:{locator}:{evidence['field']} — "
        f"{evidence['quote']}"
    )


def _final_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Story acceptance 最终报告：{report['packId']}",
        "",
        f"- Run：`{report['runId']}`",
        f"- Revision：`{report['sourceRevision']}`",
        f"- Suite：`{report.get('suite')}`",
        f"- 最终结论：`{report['overallStatus']}`",
        f"- 语义审阅者：`{report['reviewBinding']['reviewer']}`",
        "",
        "## 检查结果",
        "",
        "| 状态 | 分类 | 检查 | 结论 |",
        "|---|---|---|---|",
    ]
    for item in report["checks"]:
        summary = str(item.get("summary", "")).replace("|", "\\|").replace(
            "\n", " "
        )
        lines.append(
            f"| `{item.get('status')}` | {item.get('category')} | "
            f"`{item.get('id')}` | {summary} |"
        )
    review_items = [
        item
        for item in report["checks"]
        if item.get("category") == "semantic"
    ]
    if review_items:
        lines.extend(["", "## Codex 语义审阅", ""])
        for item in review_items:
            details = item.get("details") or {}
            lines.extend([
                f"### {item['id']}",
                "",
                f"- 结论：`{item['status']}`",
                f"- 理由：{details.get('overallReason', '')}",
            ])
            for check in details.get("checks", []):
                lines.append(
                    f"- Rubric {check['ruleIndex']}：`{check['verdict']}` / "
                    f"`{check['confidence']}` — {check['reason']}"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CodexReviewError(f"required artifact is missing: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodexReviewError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise CodexReviewError(f"JSON artifact must be an object: {path.name}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexReviewError(
                f"invalid JSONL artifact: {path.name}:{line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise CodexReviewError(
                f"JSONL row must be an object: {path.name}:{line_number}"
            )
        result.append(value)
    return result


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Finalize a Story acceptance run from a Codex review artifact."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--run-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "finalize":
        raise AssertionError(f"unexpected command: {args.command}")
    try:
        status, _report = finalize_run(args.run_dir)
    except CodexReviewError as exc:
        print(f"Codex review finalization failed: {exc}", file=sys.stderr)
        return 2
    report_path = Path(args.run_dir).expanduser().resolve() / FINAL_REPORT_MARKDOWN
    print(f"Final Story acceptance status: {status}")
    print(f"Final report: {report_path}")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CodexReviewError",
    "FINAL_REPORT_JSON",
    "FINAL_REPORT_MARKDOWN",
    "QUEUE_FILENAME",
    "QUEUE_SCHEMA_VERSION",
    "REVIEW_FILENAME",
    "REVIEW_SCHEMA_VERSION",
    "TEMPLATE_FILENAME",
    "build_review_queue",
    "build_review_template",
    "finalize_run",
    "main",
    "sha256_file",
]
