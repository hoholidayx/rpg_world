"""Incremental, credential-safe artifacts for Story acceptance runs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from tests.story_acceptance.codex_review import (
    QUEUE_FILENAME,
    TEMPLATE_FILENAME,
    build_review_queue,
    build_review_template,
    sha256_file,
)
from tests.story_acceptance.models import AcceptanceStatus


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|bearer|access[_-]?token|secret|password)",
    re.IGNORECASE,
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]{12,}"),
    re.compile(
        r"(?i)((?:x-)?api[_-]?key|access[_-]?token|secret|password)"
        r"(\s*[:=]\s*)[^\s,;\]}]+"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


@dataclass(frozen=True)
class AcceptanceCheck:
    id: str
    category: str
    status: AcceptanceStatus
    summary: str
    evidence: tuple[str, ...] = ()
    flow_id: str | None = None
    step_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AcceptanceReport:
    pack_id: str
    source_revision: str
    source_digest: str
    suite: str
    checks: list[AcceptanceCheck] = field(default_factory=list)

    def add(
        self,
        *,
        check_id: str,
        category: str,
        status: AcceptanceStatus | str,
        summary: str,
        evidence: Iterable[str] = (),
        flow_id: str | None = None,
        step_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> AcceptanceCheck:
        check = AcceptanceCheck(
            id=str(check_id),
            category=str(category),
            status=AcceptanceStatus(status),
            summary=str(summary),
            evidence=tuple(str(item) for item in evidence),
            flow_id=flow_id,
            step_id=step_id,
            details=dict(details or {}),
        )
        self.checks.append(check)
        return check

    @property
    def overall_status(self) -> AcceptanceStatus:
        statuses = {item.status for item in self.checks}
        if AcceptanceStatus.INFRASTRUCTURE_ERROR in statuses:
            return AcceptanceStatus.INFRASTRUCTURE_ERROR
        if AcceptanceStatus.FAIL in statuses:
            return AcceptanceStatus.FAIL
        if AcceptanceStatus.NEEDS_REVIEW in statuses:
            return AcceptanceStatus.NEEDS_REVIEW
        if statuses and statuses <= {AcceptanceStatus.NOT_APPLICABLE}:
            return AcceptanceStatus.NOT_APPLICABLE
        return AcceptanceStatus.PASS

    @property
    def hard_failures(self) -> list[AcceptanceCheck]:
        return [
            item
            for item in self.checks
            if item.status
            in {AcceptanceStatus.FAIL, AcceptanceStatus.INFRASTRUCTURE_ERROR}
        ]

    @property
    def review_items(self) -> list[AcceptanceCheck]:
        return [
            item
            for item in self.checks
            if item.status is AcceptanceStatus.NEEDS_REVIEW
        ]

    def as_dict(self) -> dict[str, Any]:
        counts = {
            status.value: sum(item.status is status for item in self.checks)
            for status in AcceptanceStatus
        }
        return {
            "schemaVersion": "story-acceptance-report/1.0",
            "packId": self.pack_id,
            "sourceRevision": self.source_revision,
            "sourceDigest": self.source_digest,
            "suite": self.suite,
            "overallStatus": self.overall_status.value,
            "counts": counts,
            "checks": [
                {
                    "id": item.id,
                    "category": item.category,
                    "status": item.status.value,
                    "summary": item.summary,
                    "evidence": list(item.evidence),
                    "flowId": item.flow_id,
                    "stepId": item.step_id,
                    "details": _jsonable(item.details),
                }
                for item in self.checks
            ],
        }

    def as_markdown(self) -> str:
        lines = [
            f"# Story acceptance：{self.pack_id}",
            "",
            f"- Revision：`{self.source_revision}`",
            f"- Suite：`{self.suite}`",
            f"- 总结论：`{self.overall_status.value}`",
            "",
            "## 检查结果",
            "",
            "| 状态 | 分类 | 检查 | 结论 |",
            "|---|---|---|---|",
        ]
        for item in self.checks:
            summary = item.summary.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| `{item.status.value}` | {item.category} | `{item.id}` | {summary} |"
            )
        review = self.review_items
        if review:
            lines.extend(["", "## 需要人工复核", ""])
            for item in review:
                lines.append(f"### {item.id}")
                lines.append("")
                lines.append(item.summary)
                if item.evidence:
                    lines.extend(["", "证据：", ""])
                    lines.extend(f"- {value}" for value in item.evidence)
                lines.append("")
        failures = self.hard_failures
        if failures:
            lines.extend(["", "## 硬失败", ""])
            for item in failures:
                lines.append(f"- `{item.id}`：{item.summary}")
        return "\n".join(lines).rstrip() + "\n"


class AcceptanceRunWriter:
    """Write replayable artifacts while a live run is still in progress."""

    def __init__(
        self,
        *,
        report_root: str | Path,
        pack_id: str,
        run_metadata: Mapping[str, Any],
    ) -> None:
        root = Path(report_root).expanduser().resolve()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{timestamp}-{uuid4().hex[:8]}"
        self.run_dir = root / _safe_segment(pack_id) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self._call_cursor = 0
        self._run_metadata = {
            "schemaVersion": "story-acceptance-run/1.0",
            "runId": self.run_id,
            "startedAt": datetime.now(UTC).isoformat(),
            **dict(run_metadata),
        }
        self._write_json("run.json", self._run_metadata)

    def append_step(self, value: Mapping[str, Any]) -> None:
        self._append_jsonl("steps.jsonl", value)

    def write_json_artifact(self, name: str, value: Any) -> Path:
        """Write an additional redacted JSON artifact inside this run."""

        normalized = str(name).strip()
        if (
            not normalized
            or Path(normalized).name != normalized
            or not normalized.endswith(".json")
        ):
            raise ValueError("artifact name must be a plain .json filename")
        self._write_json(normalized, value)
        return self.run_dir / normalized

    def flush_calls(self, calls: list[Any]) -> None:
        for index, call in enumerate(calls[self._call_cursor :], start=self._call_cursor):
            payload = asdict(call) if is_dataclass(call) else _jsonable(call)
            self._append_jsonl(
                "calls.jsonl",
                {"index": index, **dict(payload)},
            )
        self._call_cursor = len(calls)

    def finalize(
        self,
        report: AcceptanceReport,
        *,
        calls: list[Any],
        final_metadata: Mapping[str, Any] | None = None,
        semantic_review_items: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.flush_calls(calls)
        queue = build_review_queue(
            run_id=self.run_id,
            pack_id=report.pack_id,
            source_revision=report.source_revision,
            source_digest=report.source_digest,
            items=semantic_review_items,
        )
        self._write_json(QUEUE_FILENAME, queue)
        written_queue = json.loads(
            (self.run_dir / QUEUE_FILENAME).read_text(encoding="utf-8")
        )
        queue_sha256 = sha256_file(self.run_dir / QUEUE_FILENAME)
        self._write_json(
            TEMPLATE_FILENAME,
            build_review_template(
                written_queue,
                queue_sha256=queue_sha256,
            ),
        )
        finished = {
            **self._run_metadata,
            **dict(final_metadata or {}),
            "finishedAt": datetime.now(UTC).isoformat(),
            "overallStatus": report.overall_status.value,
            "semanticReview": {
                "status": (
                    "codex_review_required"
                    if semantic_review_items
                    else "not_required"
                ),
                "itemCount": len(semantic_review_items),
                "queue": QUEUE_FILENAME,
                "queueSha256": queue_sha256,
                "template": TEMPLATE_FILENAME,
            },
        }
        self._write_json("run.json", finished)
        self._write_json("report.json", report.as_dict())
        (self.run_dir / "report.md").write_text(
            report.as_markdown(),
            encoding="utf-8",
        )

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

    def _append_jsonl(self, name: str, value: Any) -> None:
        with (self.run_dir / name).open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    redact_for_log(_jsonable(value)),
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()


def redact_for_log(value: Any, *, key: str = "") -> Any:
    """Recursively redact credential-shaped values while keeping story text."""

    normalized_key = str(key).replace("_", "").replace("-", "").casefold()
    if normalized_key in {"reasoningcontent", "thinkingcontent"}:
        return "<private-reasoning-omitted>"
    if _SENSITIVE_KEY.search(str(key)):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_for_log(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_for_log(item) for item in value]
    if isinstance(value, tuple):
        return [redact_for_log(item) for item in value]
    if isinstance(value, str):
        result = value
        for pattern in _SECRET_TEXT_PATTERNS:
            result = pattern.sub(
                lambda match: (
                    (match.group(1) if match.lastindex else "") + "<redacted>"
                ),
                result,
            )
        return result
    return value


def summarize_live_calls(calls: Iterable[Any]) -> dict[str, Any]:
    """Aggregate observable usage and latency without Provider internals."""

    totals = {
        "callCount": 0,
        "promptTokens": 0,
        "completionTokens": 0,
        "totalTokens": 0,
        "cachedTokens": 0,
        "durationMs": 0.0,
        "errorCount": 0,
    }
    by_biz: dict[str, dict[str, Any]] = {}
    providers: set[tuple[str, str, str]] = set()
    for call in calls:
        biz_key = str(getattr(call, "biz_key", "") or "unknown")
        bucket = by_biz.setdefault(
            biz_key,
            {
                "callCount": 0,
                "promptTokens": 0,
                "completionTokens": 0,
                "totalTokens": 0,
                "cachedTokens": 0,
                "durationMs": 0.0,
                "errorCount": 0,
            },
        )
        duration = float(getattr(call, "duration_ms", 0.0) or 0.0)
        error = bool(getattr(call, "error_type", None))
        usage_values = _call_usage_values(getattr(call, "response", None))
        for target in (totals, bucket):
            target["callCount"] += 1
            target["durationMs"] += duration
            target["errorCount"] += int(error)
            for key_name, value in usage_values.items():
                target[key_name] += value
        providers.add((
            biz_key,
            str(getattr(call, "provider_key", "") or ""),
            str(getattr(call, "configured_model", "") or ""),
        ))
    for target in (totals, *by_biz.values()):
        target["durationMs"] = round(float(target["durationMs"]), 3)
    return {
        **totals,
        "byBiz": dict(sorted(by_biz.items())),
        "providers": [
            {"bizKey": biz, "provider": provider, "model": model}
            for biz, provider, model in sorted(providers)
        ],
    }


def _call_usage_values(response: Any) -> dict[str, int]:
    values = {
        "promptTokens": 0,
        "completionTokens": 0,
        "totalTokens": 0,
        "cachedTokens": 0,
    }
    if not isinstance(response, Mapping):
        return values
    usages: list[Mapping[str, Any]] = []
    usage = response.get("usage")
    if isinstance(usage, Mapping):
        usages.append(usage)
    chunks = response.get("chunks")
    if isinstance(chunks, list):
        # Streaming Providers can repeat cumulative usage. Only the final
        # usage-bearing chunk represents the completed request.
        chunk_usages = [
            chunk.get("usage")
            for chunk in chunks
            if isinstance(chunk, Mapping)
            and isinstance(chunk.get("usage"), Mapping)
        ]
        if chunk_usages:
            usages.append(chunk_usages[-1])
    for item in usages:
        values["promptTokens"] += int(item.get("prompt_tokens", 0) or 0)
        values["completionTokens"] += int(item.get("completion_tokens", 0) or 0)
        values["totalTokens"] += int(item.get("total_tokens", 0) or 0)
        cached = int(item.get("prompt_cache_hit_tokens", 0) or 0)
        if not cached:
            details = item.get("prompt_tokens_details")
            if isinstance(details, Mapping):
                cached = int(details.get("cached_tokens", 0) or 0)
        values["cachedTokens"] += cached
    return values


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
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _jsonable(model_dump(by_alias=True, exclude_none=True))
    return str(value)


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return normalized[:120] or "story-pack"


__all__ = [
    "AcceptanceCheck",
    "AcceptanceReport",
    "AcceptanceRunWriter",
    "redact_for_log",
    "summarize_live_calls",
]
