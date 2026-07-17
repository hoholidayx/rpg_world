"""Markdown reporting and append-only tracked benchmark history."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from rp_memory.benchmark.locomo import MANIFEST as LOCOMO_MANIFEST
from rp_memory.benchmark.models import (
    BenchmarkEnvironment,
    BenchmarkPathResult,
    CapabilityProbe,
    CaseResult,
    DatasetResult,
    SuiteResult,
)


HISTORY_HEADER = """# RP Memory Recall Benchmark History

This append-only summary records explicit `--record` runs. The suite is
informational and does not block changes yet. Full per-case diagnostics stay
in the ignored local `data/benchmarks/results/` report named by each entry.

Scores from hybrid fusion and reranking are query-local ordering signals, not
probabilities and not comparable across independent queries.
"""


def new_run_identity() -> tuple[str, str]:
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    return run_id, now.isoformat().replace("+00:00", "Z")


def capture_environment(
    *,
    run_id: str,
    started_at_utc: str,
    command: str,
    repo_root: Path,
    paths: dict[str, Path],
) -> BenchmarkEnvironment:
    revision = _git(repo_root, "rev-parse", "HEAD") or "unavailable"
    status = _git(repo_root, "status", "--porcelain")
    status_lines = [line for line in status.splitlines() if line.strip()]
    try:
        jieba_version = importlib.metadata.version("jieba")
    except importlib.metadata.PackageNotFoundError:
        jieba_version = "unavailable"
    return BenchmarkEnvironment(
        run_id=run_id,
        started_at_utc=started_at_utc,
        command=command,
        repo_root=str(repo_root.resolve()),
        git_revision=revision,
        git_dirty=bool(status_lines),
        git_status_summary="; ".join(status_lines[:40]) or "clean",
        python_version=" ".join(sys.version.split()),
        sqlite_version=sqlite3.sqlite_version,
        jieba_version=jieba_version,
        platform=platform.platform(),
        paths=tuple(
            (name, str(path.resolve()))
            for name, path in sorted(paths.items())
        ),
        profile=os.environ.get("RPG_WORLD_PROFILE", "local"),
        llm_service_url=_safe_service_url(
            os.environ.get(
                "RPG_WORLD_LLM_SERVICE_URL",
                "http://127.0.0.1:8012/llm/v1",
            )
        ),
    )


def render_full_report(suite: SuiteResult) -> str:
    env = suite.environment
    lines = [
        "# RP Memory Recall Benchmark Report",
        "",
        f"- Run ID: `{env.run_id}`",
        f"- Started (UTC): `{env.started_at_utc}`",
        f"- Finished (UTC): `{suite.finished_at_utc}`",
        f"- Successful: `{str(suite.successful).lower()}`",
        "- Gate: informational only; metrics are recorded but do not block changes.",
        "- Cost warning: configured Provider paths can call remote services, incur fees, and be non-deterministic.",
        "- Score warning: hybrid/final scores are query-local ordering signals, not probabilities.",
        "",
        "## Environment",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Command | `{_cell(env.command)}` |",
        f"| Repository | `{_cell(env.repo_root)}` |",
        f"| Git revision | `{_cell(env.git_revision)}` |",
        f"| Git dirty | `{str(env.git_dirty).lower()}` |",
        f"| Git status | `{_cell(env.git_status_summary)}` |",
        f"| Python | `{_cell(env.python_version)}` |",
        f"| SQLite | `{_cell(env.sqlite_version)}` |",
        f"| jieba | `{_cell(env.jieba_version)}` |",
        f"| Platform | `{_cell(env.platform)}` |",
        f"| RPG profile | `{_cell(env.profile or '-')}` |",
        f"| LLM service | `{_cell(env.llm_service_url or '-')}` |",
        "",
        "## Paths",
        "",
        "| Purpose | Absolute path |",
        "|---|---|",
    ]
    lines.extend(f"| `{_cell(name)}` | `{_cell(path)}` |" for name, path in env.paths)
    lines.extend(_dataset_provenance(env))
    lines.extend(_capability_section(suite))
    lines.extend(_metrics_section(suite.paths))
    lines.extend(_path_details(suite.paths))
    if suite.errors:
        lines.extend(("", "## Suite errors", ""))
        lines.extend(f"- `{_cell(error)}`" for error in suite.errors)
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, content)


def append_history(
    suite: SuiteResult,
    *,
    history_path: Path,
    local_report_path: Path,
) -> bool:
    if not suite.successful:
        raise ValueError("only a successful benchmark suite may be recorded")
    marker = f"<!-- run-id:{suite.environment.run_id} -->"
    current = history_path.read_text(encoding="utf-8") if history_path.exists() else HISTORY_HEADER
    if marker in current:
        return False
    section = render_history_section(suite, local_report_path=local_report_path)
    normalized = current.rstrip() + "\n\n" + section.rstrip() + "\n"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(history_path, normalized)
    return True


def render_history_section(suite: SuiteResult, *, local_report_path: Path) -> str:
    env = suite.environment
    lines = [
        f"<!-- run-id:{env.run_id} -->",
        f"## {env.started_at_utc} — `{env.run_id}`",
        "",
        f"- Revision: `{env.git_revision}` (dirty: `{str(env.git_dirty).lower()}`)",
        f"- Command: `{env.command}`",
        f"- Full local report: `{local_report_path.resolve()}`",
        "- Gate: informational only.",
        "- Configured Provider results may have cost and non-determinism.",
        "",
    ]
    lines.extend(_compact_capability_table(suite))
    lines.extend(_metrics_table(suite.paths))
    lines.extend(_planner_activity(suite.paths))
    gold_issues = _gold_issue_summary(suite.paths)
    if gold_issues:
        lines.extend(("", "RP Gold failures/contamination:", ""))
        lines.extend(f"- `{path_id}`: {', '.join(ids)}" for path_id, ids in gold_issues)
    return "\n".join(lines)


def _dataset_provenance(env: BenchmarkEnvironment) -> list[str]:
    paths = dict(env.paths)
    gold_status = "unknown"
    gold_path = paths.get("rp_gold", "")
    if gold_path:
        try:
            import json

            payload = json.loads(Path(gold_path).read_text(encoding="utf-8"))
            gold_status = str(payload.get("review_status", "unknown"))
        except Exception:
            gold_status = "unreadable"
    manifest = asdict(LOCOMO_MANIFEST)
    return [
        "",
        "## Dataset provenance",
        "",
        "| Dataset | Frozen source | Integrity / review | License |",
        "|---|---|---|---|",
        (
            f"| LoCoMo | commit `{manifest['commit']}`; `{_cell(manifest['source_url'])}` | "
            f"size `{manifest['size']}`; SHA-256 `{manifest['sha256']}` | "
            f"[{manifest['license']}]({manifest['license_url']}) |"
        ),
        f"| RP Gold Seed | checked-in `{_cell(gold_path)}` | `{_cell(gold_status)}` | project-maintained |",
    ]


def _capability_section(suite: SuiteResult) -> list[str]:
    matrix = suite.capability_matrix
    lines = [
        "",
        "## Capability matrix",
        "",
        f"Service probe: `{matrix.service_status.value}` — {_cell(matrix.service_reason)}",
        "",
        "| Capability | Status | Biz | Provider | Backend | Model | Dimension | Default | Reason |",
        "|---|---|---|---|---|---|---:|---|---|",
    ]
    lines.extend(_probe_row(probe) for probe in matrix.probes)
    return lines


def _compact_capability_table(suite: SuiteResult) -> list[str]:
    lines = [
        "Capability matrix:",
        "",
        "| Capability | Status | Provider | Backend/model | Dimension |",
        "|---|---|---|---|---:|",
    ]
    for probe in suite.capability_matrix.probes:
        provider = probe.provider
        lines.append(
            "| {cap} | `{status}` | `{provider}` | `{backend}` / `{model}` | {dimension} |".format(
                cap=_cell(probe.capability),
                status=probe.status.value,
                provider=_cell(provider.provider_key if provider else "-"),
                backend=_cell(provider.backend if provider else "-"),
                model=_cell(provider.model if provider else "-"),
                dimension=provider.dimension if provider and provider.dimension is not None else "-",
            )
        )
    return lines


def _probe_row(probe: CapabilityProbe) -> str:
    provider = probe.provider
    return (
        f"| {_cell(probe.capability)} | `{probe.status.value}` | "
        f"`{_cell(provider.biz_key if provider else '-')}` | "
        f"`{_cell(provider.provider_key if provider else '-')}` | "
        f"`{_cell(provider.backend if provider else '-')}` | "
        f"`{_cell(provider.model if provider else '-')}` | "
        f"{provider.dimension if provider and provider.dimension is not None else '-'} | "
        f"{'yes' if provider and provider.is_default else 'no'} | {_cell(probe.reason)} |"
    )


def _metrics_section(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    return [
        "",
        "## Metrics matrix",
        "",
        *_metrics_table(paths),
    ]


def _metrics_table(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    lines = [
        "| Path | Status | Dataset | Cases | Hit@1 | Recall@5 | MRR | nDCG | Coverage | No-answer | Forbidden@1 | Forbidden@5 | Before-gold |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for path in paths:
        if not path.datasets:
            lines.append(
                f"| `{_cell(path.path_id)}` | `{path.status.value}` | - | - | - | - | - | - | - | - | - | - | - |"
            )
            continue
        for dataset in path.datasets:
            metric = dataset.metrics
            lines.append(
                "| `{path}` | `{status}` | {dataset} | {cases} | {hit1} | {recall} | {mrr} | {ndcg} | {coverage} | {no_answer} | {forbidden1} | {forbidden5} | {before} |".format(
                    path=_cell(path.path_id),
                    status=path.status.value,
                    dataset=_cell(dataset.dataset),
                    cases=metric.get("cases", "-"),
                    hit1=_metric(metric.get("hit_at_1")),
                    recall=_metric(metric.get("recall_at_k")),
                    mrr=_metric(metric.get("mrr")),
                    ndcg=_metric(metric.get("ndcg")),
                    coverage=_metric(metric.get("evidence_coverage")),
                    no_answer=_metric(metric.get("no_answer_accuracy")),
                    forbidden1=_metric(metric.get("forbidden_at_1_rate")),
                    forbidden5=_metric(metric.get("forbidden_hit_rate")),
                    before=_metric(metric.get("forbidden_before_gold_rate")),
                )
            )
    return lines


def _path_details(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    lines = ["", "## Path details"]
    for path in paths:
        pipeline = path.pipeline
        lines.extend(
            (
                "",
                f"### `{path.path_id}`",
                "",
                f"- Status: `{path.status.value}`",
                f"- Reason: {_cell(path.reason)}",
                f"- Pipeline: `{_cell(pipeline.arrow)}`",
                f"- Candidate K: vector `{pipeline.vector_candidate_k}`, keyword `{pipeline.keyword_candidate_k}`, rerank `{pipeline.rerank_candidate_k}`; final `{pipeline.top_k}`",
                f"- Tokenizer: `{pipeline.keyword_tokenizer}`; raw-md: `{pipeline.raw_md_mode}` (min `{pipeline.raw_md_min_results}`)",
                f"- Weights: `{', '.join(f'{key}={value:g}' for key, value in pipeline.weights)}`",
                f"- Expanded query effect: {_cell(pipeline.expanded_query_effect)}",
                f"- Duration: `{path.duration_seconds:.3f}s`",
            )
        )
        if pipeline.providers:
            lines.extend(("", "Providers:", ""))
            for provider in pipeline.providers:
                lines.append(
                    f"- `{provider.capability}`: biz `{provider.biz_key}`, provider `{provider.provider_key}`, backend `{provider.backend}`, model `{provider.model}`, dimension `{provider.dimension if provider.dimension is not None else '-'}`"
                )
        for dataset in path.datasets:
            source_counts = dataset.metrics.get("planner_source_counts", {})
            if isinstance(source_counts, dict):
                source_summary = ", ".join(
                    f"{key}={value}"
                    for key, value in sorted(source_counts.items())
                ) or "-"
            else:
                source_summary = _cell(source_counts)
            lines.extend((
                "",
                f"- Dataset `{_cell(dataset.dataset)}`: source `{_cell(dataset.source_path)}`; duration `{dataset.duration_seconds:.3f}s`",
                f"- Planner activity: sources `{_cell(source_summary)}`; expanded-query cases `{dataset.metrics.get('expanded_query_cases', 0)}/{dataset.metrics.get('planner_trace_cases', 0)}`; variants `{dataset.metrics.get('expanded_query_total', 0)}`",
            ))
            lines.extend(_dataset_failures(dataset))
    return lines


def _planner_activity(paths: tuple[BenchmarkPathResult, ...]) -> list[str]:
    rows: list[str] = []
    for path in paths:
        for dataset in path.datasets:
            metrics = dataset.metrics
            sources = metrics.get("planner_source_counts", {})
            if isinstance(sources, dict):
                source_summary = ", ".join(
                    f"{key}={value}"
                    for key, value in sorted(sources.items())
                ) or "-"
            else:
                source_summary = str(sources)
            rows.append(
                "| `{path}` | {dataset} | `{sources}` | {expanded}/{traces} | {total} | {effect} |".format(
                    path=_cell(path.path_id),
                    dataset=_cell(dataset.dataset),
                    sources=_cell(source_summary),
                    expanded=metrics.get("expanded_query_cases", 0),
                    traces=metrics.get("planner_trace_cases", 0),
                    total=metrics.get("expanded_query_total", 0),
                    effect=_cell(path.pipeline.expanded_query_effect),
                )
            )
    if not rows:
        return []
    return [
        "",
        "Planner/query expansion activity:",
        "",
        "| Path | Dataset | Planner sources | Cases with expansion | Variants | Expansion use |",
        "|---|---|---|---:|---:|---|",
        *rows,
    ]


def _dataset_failures(dataset: DatasetResult) -> list[str]:
    problematic = [case for case in dataset.cases if case.issues]
    lines = [
        "",
        f"#### {dataset.dataset}: failures and contamination ({len(problematic)}/{len(dataset.cases)})",
        "",
    ]
    if not problematic:
        lines.append("No failed, partial, unscored, or forbidden-ranked cases.")
        return lines
    for case in problematic:
        lines.extend(_case_detail(case))
    return lines


def _case_detail(case: CaseResult) -> list[str]:
    summary = f"{case.question_id or case.sample_id} — {', '.join(case.issues)}"
    lines = [
        "<details>",
        f"<summary>{_cell(summary)}</summary>",
        "",
        f"- Question: {_cell(case.question)}",
        f"- Gold: `{', '.join(case.gold_evidence) or '-'}`",
        f"- Forbidden: `{', '.join(case.forbidden_evidence) or '-'}`",
    ]
    trace = case.planner_trace
    if trace is not None:
        lines.extend(
            (
                f"- Planner: `{trace.planner_source}`",
                f"- Normalized: `{_cell(trace.normalized_query)}`",
                f"- Keyword queries: `{_cell(' | '.join(trace.keyword_queries) or '-')}`",
                f"- Expanded queries: `{_cell(' | '.join(trace.expanded_queries) or '-')}`",
                f"- Raw terms: `{_cell(' | '.join(trace.raw_md_terms) or '-')}`",
                f"- Expansion use: {_cell(trace.expanded_query_effect)}",
            )
        )
    lines.extend(
        (
            "",
            "| Rank | Evidence | Final | Vector | Keyword | Raw | Exact | Fuzzy | Expanded | Granularity | Hybrid | Rerank | Preview |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        )
    )
    if not case.rankings:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - | no results |")
    for ranked in case.rankings:
        scores = dict(ranked.scores)
        lines.append(
            "| {rank} | `{evidence}` | {final} | {vector} | {keyword} | {raw} | {exact} | {fuzzy} | {expanded} | {granularity} | {hybrid} | {rerank} | {preview} |".format(
                rank=ranked.rank,
                evidence=_cell(ranked.evidence_id or "-"),
                final=_score(ranked.final_score),
                vector=_score(scores.get("vector")),
                keyword=_score(scores.get("keyword")),
                raw=_score(scores.get("raw_md")),
                exact=_score(scores.get("exact")),
                fuzzy=_score(scores.get("fuzzy")),
                expanded=_score(scores.get("expanded")),
                granularity=_score(scores.get("granularity")),
                hybrid=_score(scores.get("hybrid")),
                rerank=_score(scores.get("rerank")),
                preview=_cell(ranked.text_preview),
            )
        )
    lines.extend(("", "</details>", ""))
    return lines


def _gold_issue_summary(
    paths: tuple[BenchmarkPathResult, ...],
) -> list[tuple[str, list[str]]]:
    summary: list[tuple[str, list[str]]] = []
    for path in paths:
        ids = sorted(
            {
                case.question_id
                for dataset in path.datasets
                if dataset.dataset == "rp-gold"
                for case in dataset.cases
                if case.issues
            }
        )
        if ids:
            summary.append((path.path_id, ids))
    return summary


def _metric(value: object) -> str:
    if value is None or value == "-":
        return "-"
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return _cell(str(value))


def _score(value: float | None) -> str:
    return "-" if value is None else f"{float(value):.6f}"


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _git(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ("git", *args),
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _safe_service_url(value: str) -> str:
    """Keep endpoint diagnostics while excluding credentials and query data."""
    try:
        parsed = urlsplit(value.strip())
        if not parsed.scheme or not parsed.hostname:
            return "invalid"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
    except ValueError:
        return "invalid"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
