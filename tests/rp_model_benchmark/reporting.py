"""Credential-safe artifacts and raw reports for RP model benchmark runs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from tests.rp_model_benchmark.evaluation import aggregate_metrics
from tests.rp_model_benchmark.models import RPBenchmarkCase, RPBenchmarkDataset
from tests.rp_model_benchmark.runner import CaseRunResult, ProviderCallRecord
from tests.story_acceptance.reporting import redact_for_log


QUEUE_SCHEMA_VERSION = "rp-model-benchmark-review-queue/1.0"
REVIEW_SCHEMA_VERSION = "rp-model-benchmark-codex-review/1.0"
QUEUE_FILENAME = "semantic-review-queue.json"
TEMPLATE_FILENAME = "codex-review-template.json"


class BenchmarkRunWriter:
    def __init__(
        self,
        *,
        report_root: str | Path,
        dataset: RPBenchmarkDataset,
        metadata: Mapping[str, Any],
    ) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{timestamp}-{uuid4().hex[:8]}"
        self.run_dir = (
            Path(report_root).expanduser().resolve()
            / _safe_segment(dataset.dataset_id)
            / self.run_id
        )
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self._metadata = {
            "schemaVersion": "rp-model-benchmark-run/1.0",
            "runId": self.run_id,
            "datasetId": dataset.dataset_id,
            "startedAt": datetime.now(UTC).isoformat(),
            **dict(metadata),
        }
        self._write_json("run.json", self._metadata)

    def finalize(
        self,
        *,
        dataset: RPBenchmarkDataset,
        selected_cases: Sequence[RPBenchmarkCase],
        calls: Sequence[ProviderCallRecord],
        case_runs: Sequence[CaseRunResult],
    ) -> dict[str, Any]:
        call_values = [
            {"index": index, **asdict(call)}
            for index, call in enumerate(calls)
        ]
        run_values = [item.as_dict() for item in case_runs]
        self._write_jsonl("calls.jsonl", call_values)
        self._write_jsonl("cases.jsonl", run_values)
        queue = _review_queue(
            run_id=self.run_id,
            dataset=dataset,
            selected_cases=selected_cases,
            case_runs=case_runs,
        )
        self._write_json(QUEUE_FILENAME, queue)
        queue_sha = _sha256(self.run_dir / QUEUE_FILENAME)
        self._write_json(
            TEMPLATE_FILENAME,
            _review_template(queue, queue_sha),
        )
        usage = summarize_calls(calls)
        metrics = aggregate_metrics(run_values)
        provider_errors = [
            f"{item.provider_key}/{item.case_id}/repeat-{item.repeat}: {item.provider_error}"
            for item in case_runs
            if item.provider_error
        ]
        report = {
            "schemaVersion": "rp-model-benchmark-report/1.0",
            "runId": self.run_id,
            "datasetId": dataset.dataset_id,
            "suite": self._metadata.get("suite"),
            "qualityStatus": "codex_review_required",
            "qualityGate": "informational_only",
            "providerErrors": provider_errors,
            "usage": usage,
            "metrics": metrics,
            "semanticReview": {
                "itemCount": len(queue["items"]),
                "queue": QUEUE_FILENAME,
                "queueSha256": queue_sha,
                "template": TEMPLATE_FILENAME,
            },
            "caseRuns": run_values,
        }
        self._write_json("report.json", report)
        (self.run_dir / "report.md").write_text(
            _raw_markdown(report),
            encoding="utf-8",
        )
        finished = {
            **self._metadata,
            "finishedAt": datetime.now(UTC).isoformat(),
            "usage": usage,
            "providerErrorCount": len(provider_errors),
            "report": "report.json",
            "semanticReview": report["semanticReview"],
        }
        self._write_json("run.json", finished)
        return report

    def _write_json(self, name: str, value: Any) -> None:
        target = self.run_dir / name
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                redact_for_log(_jsonable(value)),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

    def _write_jsonl(self, name: str, values: Iterable[Any]) -> None:
        target = self.run_dir / name
        with target.open("w", encoding="utf-8") as handle:
            for value in values:
                handle.write(json.dumps(
                    redact_for_log(_jsonable(value)),
                    ensure_ascii=False,
                    sort_keys=True,
                ) + "\n")


def summarize_calls(calls: Sequence[ProviderCallRecord]) -> dict[str, Any]:
    total = _usage_bucket()
    by_provider: dict[str, dict[str, Any]] = {}
    for call in calls:
        bucket = by_provider.setdefault(call.provider_key, _usage_bucket())
        usage = _response_usage(call.response)
        for target in (total, bucket):
            target["callCount"] += 1
            target["durationMs"] += call.duration_ms
            target["errorCount"] += int(call.error_type is not None)
            for key, value in usage.items():
                target[key] += value
    for target in (total, *by_provider.values()):
        prompt = int(target["promptTokens"])
        target["uncachedPromptTokens"] = max(
            0,
            prompt - int(target["cachedTokens"]),
        )
        target["cacheHitRate"] = round(
            int(target["cachedTokens"]) / prompt,
            6,
        ) if prompt else 0.0
        target["durationMs"] = round(float(target["durationMs"]), 3)
    return {**total, "byProvider": dict(sorted(by_provider.items()))}


def _usage_bucket() -> dict[str, int | float]:
    return {
        "callCount": 0,
        "promptTokens": 0,
        "completionTokens": 0,
        "totalTokens": 0,
        "cachedTokens": 0,
        "durationMs": 0.0,
        "errorCount": 0,
    }


def _response_usage(response: Mapping[str, object] | None) -> dict[str, int]:
    result = {
        "promptTokens": 0,
        "completionTokens": 0,
        "totalTokens": 0,
        "cachedTokens": 0,
    }
    if not isinstance(response, Mapping):
        return result
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return result
    result["promptTokens"] = int(usage.get("prompt_tokens", 0) or 0)
    result["completionTokens"] = int(usage.get("completion_tokens", 0) or 0)
    result["totalTokens"] = int(usage.get("total_tokens", 0) or 0)
    cached = int(usage.get("prompt_cache_hit_tokens", 0) or 0)
    if not cached:
        details = usage.get("prompt_tokens_details")
        if isinstance(details, Mapping):
            cached = int(details.get("cached_tokens", 0) or 0)
    result["cachedTokens"] = cached
    return result


def _review_queue(
    *,
    run_id: str,
    dataset: RPBenchmarkDataset,
    selected_cases: Sequence[RPBenchmarkCase],
    case_runs: Sequence[CaseRunResult],
) -> dict[str, Any]:
    cases_by_id = {item.id: item for item in selected_cases}
    groups: dict[tuple[str, str], list[CaseRunResult]] = {}
    for result in case_runs:
        groups.setdefault((result.provider_key, result.case_id), []).append(result)
    items: list[dict[str, Any]] = []
    for (provider_key, case_id), runs in sorted(groups.items()):
        case = cases_by_id[case_id]
        items.append({
            "checkId": f"{provider_key}.{case_id}.semantic",
            "providerKey": provider_key,
            "model": runs[0].model,
            "caseId": case_id,
            "category": case.category.value,
            "case": case.model_dump(by_alias=True, exclude_none=True),
            "rubric": list(case.semantic_rubric),
            "runs": [item.as_dict() for item in sorted(runs, key=lambda value: value.repeat)],
        })
    return {
        "schemaVersion": QUEUE_SCHEMA_VERSION,
        "runId": run_id,
        "datasetId": dataset.dataset_id,
        "items": items,
    }


def _review_template(queue: Mapping[str, Any], queue_sha: str) -> dict[str, Any]:
    return {
        "schemaVersion": REVIEW_SCHEMA_VERSION,
        "reviewer": "codex",
        "reviewedAt": "__REQUIRED_ISO8601__",
        "binding": {
            "runId": queue["runId"],
            "datasetId": queue["datasetId"],
            "queueSha256": queue_sha,
        },
        "reviews": [
            {
                "checkId": item["checkId"],
                "providerKey": item["providerKey"],
                "caseId": item["caseId"],
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


def _raw_markdown(report: Mapping[str, Any]) -> str:
    usage = report["usage"]
    lines = [
        f"# 中立 RP 模型评测：{report['datasetId']}",
        "",
        f"- Run：`{report['runId']}`",
        f"- Suite：`{report['suite']}`",
        "- 质量门禁：仅报告",
        f"- 调用：{usage['callCount']}，Tokens：{usage['totalTokens']}",
        f"- Prompt cache：{usage['cachedTokens']} / {usage['promptTokens']} "
        f"(`{100 * usage['cacheHitRate']:.2f}%`)",
        "- 语义结论：等待 Codex 证据审阅",
        "",
        "## Provider 指标",
        "",
        "| Provider | 运行 | 确定性通过率 | 重复决策一致率 | 错误 |",
        "|---|---:|---:|---:|---:|",
    ]
    for provider, metrics in report["metrics"].items():
        lines.append(
            f"| `{provider}` | {metrics['runCount']} | "
            f"{100 * metrics['deterministicPassRate']:.2f}% | "
            f"{100 * metrics['repeatDecisionConsistency']:.2f}% | "
            f"{metrics['providerErrors']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return normalized[:120] or "rp-model"


__all__ = [
    "BenchmarkRunWriter",
    "QUEUE_FILENAME",
    "QUEUE_SCHEMA_VERSION",
    "REVIEW_SCHEMA_VERSION",
    "TEMPLATE_FILENAME",
    "summarize_calls",
]
