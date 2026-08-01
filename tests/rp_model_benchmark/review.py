"""Evidence-bound Codex review and final RP benchmark report."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from tests.rp_model_benchmark.reporting import (
    QUEUE_FILENAME,
    QUEUE_SCHEMA_VERSION,
    REVIEW_SCHEMA_VERSION,
)


REVIEW_FILENAME = "codex-review.json"
FINAL_REPORT_JSON = "final-report.json"
FINAL_REPORT_MARKDOWN = "final-report.md"
FINAL_SCHEMA_VERSION = "rp-model-benchmark-final-report/1.0"
_VERDICTS = frozenset({"pass", "fail", "needs_review"})
_CONFIDENCES = frozenset({"low", "medium", "high"})


class RPBenchmarkReviewError(ValueError):
    """A review does not bind to the captured benchmark evidence."""


def finalize_review(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).expanduser().resolve()
    run = _load_json(root / "run.json")
    raw = _load_json(root / "report.json")
    queue = _load_json(root / QUEUE_FILENAME)
    review = _load_json(root / REVIEW_FILENAME)
    queue_sha = hashlib.sha256((root / QUEUE_FILENAME).read_bytes()).hexdigest()
    _validate_identity(run, raw, queue)
    _validate_binding(review, queue, queue_sha)
    semantic = _validate_reviews(queue, review)
    final = {
        "schemaVersion": FINAL_SCHEMA_VERSION,
        "runId": run["runId"],
        "datasetId": run["datasetId"],
        "suite": run.get("suite"),
        "qualityGate": "informational_only",
        "qualityStatus": _quality_status(semantic, raw.get("providerErrors", [])),
        "counts": Counter(item["status"] for item in semantic),
        "usage": raw.get("usage", {}),
        "deterministicMetrics": raw.get("metrics", {}),
        "semanticMetrics": _semantic_metrics(semantic),
        "reviewBinding": {
            "reviewer": "codex",
            "reviewedAt": review["reviewedAt"],
            "queueSha256": queue_sha,
            "reviewArtifact": REVIEW_FILENAME,
        },
        "semanticResults": semantic,
        "providerErrors": raw.get("providerErrors", []),
    }
    final["counts"] = dict(final["counts"])
    _write_json(root / FINAL_REPORT_JSON, final)
    (root / FINAL_REPORT_MARKDOWN).write_text(
        _render_markdown(final),
        encoding="utf-8",
    )
    return final


def _validate_identity(
    run: Mapping[str, Any],
    raw: Mapping[str, Any],
    queue: Mapping[str, Any],
) -> None:
    if queue.get("schemaVersion") != QUEUE_SCHEMA_VERSION:
        raise RPBenchmarkReviewError("unsupported review queue schema")
    for key in ("runId", "datasetId"):
        if queue.get(key) != run.get(key) or raw.get(key) != run.get(key):
            raise RPBenchmarkReviewError(f"{key} does not match captured run")
    items = queue.get("items")
    if not isinstance(items, list) or not items:
        raise RPBenchmarkReviewError("review queue must contain items")
    ids = [item.get("checkId") if isinstance(item, Mapping) else None for item in items]
    if any(not isinstance(value, str) or not value for value in ids):
        raise RPBenchmarkReviewError("queue contains an invalid checkId")
    if len(ids) != len(set(ids)):
        raise RPBenchmarkReviewError("queue checkId values must be unique")


def _validate_binding(
    review: Mapping[str, Any],
    queue: Mapping[str, Any],
    queue_sha: str,
) -> None:
    if review.get("schemaVersion") != REVIEW_SCHEMA_VERSION:
        raise RPBenchmarkReviewError("unsupported Codex review schema")
    if review.get("reviewer") != "codex":
        raise RPBenchmarkReviewError("reviewer must be codex")
    reviewed_at = review.get("reviewedAt")
    if not isinstance(reviewed_at, str) or reviewed_at.startswith("__"):
        raise RPBenchmarkReviewError("reviewedAt is incomplete")
    try:
        datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RPBenchmarkReviewError("reviewedAt must be ISO-8601") from exc
    expected = {
        "runId": queue["runId"],
        "datasetId": queue["datasetId"],
        "queueSha256": queue_sha,
    }
    if review.get("binding") != expected:
        raise RPBenchmarkReviewError("review binding does not match queue bytes")


def _validate_reviews(
    queue: Mapping[str, Any],
    review: Mapping[str, Any],
) -> list[dict[str, Any]]:
    queue_items = {item["checkId"]: item for item in queue["items"]}
    raw_reviews = review.get("reviews")
    if not isinstance(raw_reviews, list):
        raise RPBenchmarkReviewError("reviews must be an array")
    review_ids = [
        item.get("checkId") if isinstance(item, Mapping) else None
        for item in raw_reviews
    ]
    if Counter(review_ids) != Counter(queue_items.keys()):
        raise RPBenchmarkReviewError("review must cover every item exactly once")
    results: list[dict[str, Any]] = []
    for raw in raw_reviews:
        if not isinstance(raw, Mapping):
            raise RPBenchmarkReviewError("review item must be an object")
        queue_item = queue_items[str(raw["checkId"])]
        for key in ("providerKey", "caseId"):
            if raw.get(key) != queue_item.get(key):
                raise RPBenchmarkReviewError(f"review {key} does not match queue")
        refusal = raw.get("providerRefusal")
        if not isinstance(refusal, bool):
            raise RPBenchmarkReviewError("providerRefusal must be boolean")
        overall_reason = raw.get("overallReason")
        if not isinstance(overall_reason, str) or not overall_reason.strip() or overall_reason.startswith("__"):
            raise RPBenchmarkReviewError("overallReason is required")
        checks = _validate_rule_checks(queue_item, raw.get("checks"))
        status = _review_status(refusal, checks)
        results.append({
            "checkId": queue_item["checkId"],
            "providerKey": queue_item["providerKey"],
            "model": queue_item["model"],
            "caseId": queue_item["caseId"],
            "category": queue_item["category"],
            "status": status,
            "providerRefusal": refusal,
            "overallReason": overall_reason.strip(),
            "checks": checks,
        })
    return sorted(results, key=lambda item: item["checkId"])


def _validate_rule_checks(
    queue_item: Mapping[str, Any],
    raw_checks: Any,
) -> list[dict[str, Any]]:
    rubric = queue_item.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        raise RPBenchmarkReviewError("queue item has no semantic rubric")
    if not isinstance(raw_checks, list) or not all(isinstance(item, Mapping) for item in raw_checks):
        raise RPBenchmarkReviewError("checks must be an object array")
    indexes = [item.get("ruleIndex") for item in raw_checks]
    if Counter(indexes) != Counter(range(len(rubric))):
        raise RPBenchmarkReviewError("checks must cover each rubric exactly once")
    normalized: list[dict[str, Any]] = []
    for raw in sorted(raw_checks, key=lambda item: int(item["ruleIndex"])):
        index = int(raw["ruleIndex"])
        if raw.get("rule") != rubric[index]:
            raise RPBenchmarkReviewError("review rewrites the original rubric")
        verdict = raw.get("verdict")
        confidence = raw.get("confidence")
        reason = raw.get("reason")
        if verdict not in _VERDICTS or confidence not in _CONFIDENCES:
            raise RPBenchmarkReviewError("review verdict or confidence is invalid")
        if not isinstance(reason, str) or not reason.strip() or reason.startswith("__"):
            raise RPBenchmarkReviewError("review reason is required")
        evidence = raw.get("evidence")
        if not isinstance(evidence, list):
            raise RPBenchmarkReviewError("evidence must be an array")
        validated = [
            _validate_evidence(queue_item, item)
            for item in evidence
        ]
        if verdict in {"pass", "fail"} and not validated:
            raise RPBenchmarkReviewError("pass/fail requires quoted evidence")
        normalized.append({
            "ruleIndex": index,
            "rule": rubric[index],
            "verdict": verdict,
            "confidence": confidence,
            "reason": reason.strip(),
            "evidence": validated,
        })
    return normalized


def _validate_evidence(
    queue_item: Mapping[str, Any],
    raw: Any,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RPBenchmarkReviewError("evidence must be an object")
    source = raw.get("source")
    field = raw.get("field")
    quote = raw.get("quote")
    if source not in {"case", "run"}:
        raise RPBenchmarkReviewError("evidence source must be case or run")
    if not isinstance(field, str) or not field or not isinstance(quote, str) or not quote:
        raise RPBenchmarkReviewError("evidence field and quote are required")
    if source == "case":
        value: Any = queue_item.get("case")
    else:
        repeat = raw.get("repeat")
        if not isinstance(repeat, int):
            raise RPBenchmarkReviewError("run evidence requires repeat")
        value = next(
            (item for item in queue_item.get("runs", []) if item.get("repeat") == repeat),
            None,
        )
        if value is None:
            raise RPBenchmarkReviewError(f"no captured run for repeat {repeat}")
    resolved = _resolve_field(value, field)
    rendered = resolved if isinstance(resolved, str) else json.dumps(
        resolved,
        ensure_ascii=False,
        sort_keys=True,
    )
    if quote not in rendered:
        raise RPBenchmarkReviewError("evidence quote is absent from captured field")
    return dict(raw)


def _resolve_field(value: Any, field: str) -> Any:
    current = value
    for segment in field.split("."):
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            raise RPBenchmarkReviewError(f"evidence field does not exist: {field}")
    return current


def _review_status(refusal: bool, checks: Sequence[Mapping[str, Any]]) -> str:
    if refusal:
        return "needs_review"
    if any(item["verdict"] == "fail" and item["confidence"] == "high" for item in checks):
        return "fail"
    if all(
        item["verdict"] == "pass" and item["confidence"] in {"medium", "high"}
        for item in checks
    ):
        return "pass"
    return "needs_review"


def _quality_status(
    semantic: Sequence[Mapping[str, Any]],
    provider_errors: Sequence[object],
) -> str:
    if provider_errors:
        return "infrastructure_error"
    statuses = {item["status"] for item in semantic}
    if "needs_review" in statuses:
        return "needs_review"
    if "fail" in statuses:
        return "completed_with_findings"
    return "pass"


def _semantic_metrics(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_provider: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        by_provider[str(item["providerKey"])].append(item)
    result: dict[str, Any] = {}
    for provider, values in sorted(by_provider.items()):
        categories: dict[str, dict[str, int | float]] = {}
        for category in sorted({str(item["category"]) for item in values}):
            categories[category] = _status_metrics(
                [item for item in values if item["category"] == category]
            )
        result[provider] = {
            **_status_metrics(values),
            "categories": categories,
        }
    return result


def _status_metrics(values: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    total = len(values)
    passed = sum(item["status"] == "pass" for item in values)
    failed = sum(item["status"] == "fail" for item in values)
    review = sum(item["status"] == "needs_review" for item in values)
    return {
        "caseCount": total,
        "pass": passed,
        "fail": failed,
        "needsReview": review,
        "passRate": round(passed / total, 6) if total else 0.0,
    }


def _render_markdown(report: Mapping[str, Any]) -> str:
    usage = report.get("usage", {})
    lines = [
        f"# 中立 RP 模型评测最终报告：{report['datasetId']}",
        "",
        f"- Run：`{report['runId']}`",
        f"- Suite：`{report.get('suite')}`",
        f"- 质量状态：`{report['qualityStatus']}`（仅报告，不作为 CI 门禁）",
        f"- 调用：{usage.get('callCount', 0)}，Tokens：{usage.get('totalTokens', 0)}",
        f"- Prompt cache 命中率：{100 * float(usage.get('cacheHitRate', 0)):.2f}%",
        "",
        "## Provider 对比",
        "",
        "| Provider | 语义通过 | 语义失败 | 待复核 | 通过率 | 确定性运行通过率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    deterministic = report.get("deterministicMetrics", {})
    for provider, metrics in report.get("semanticMetrics", {}).items():
        det = deterministic.get(provider, {})
        lines.append(
            f"| `{provider}` | {metrics['pass']} | {metrics['fail']} | "
            f"{metrics['needsReview']} | {100 * metrics['passRate']:.2f}% | "
            f"{100 * float(det.get('deterministicPassRate', 0)):.2f}% |"
        )
    lines.extend(["", "## Codex 语义结论", ""])
    for item in report.get("semanticResults", []):
        lines.append(
            f"- `{item['providerKey']}/{item['caseId']}`："
            f"`{item['status']}` — {item['overallReason']}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RPBenchmarkReviewError(f"required artifact missing: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RPBenchmarkReviewError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise RPBenchmarkReviewError(f"artifact must be an object: {path.name}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


__all__ = [
    "FINAL_REPORT_JSON",
    "FINAL_REPORT_MARKDOWN",
    "REVIEW_FILENAME",
    "RPBenchmarkReviewError",
    "finalize_review",
]
