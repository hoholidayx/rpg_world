"""Top-level fixed benchmark workflow with guaranteed local reporting."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from llm_client.manager import LLMClientManager
from rp_memory.benchmark.capabilities import detect_capabilities
from rp_memory.benchmark.locomo import LOCOMO_COMMIT, prepare_locomo
from rp_memory.benchmark.models import (
    BenchmarkPathResult,
    BenchmarkStatus,
    CapabilityMatrix,
    PipelineDescription,
    SuiteResult,
)
from rp_memory.benchmark.report import (
    append_history,
    capture_environment,
    new_run_identity,
    render_full_report,
    write_report,
)
from rp_memory.benchmark.rp_gold import load_rp_gold
from rp_memory.benchmark.runner import (
    TOP_K,
    build_rp_gold_dataset,
    load_jsonl_dataset,
    run_benchmark_paths,
)
from rpg_core.settings import settings


@dataclass(frozen=True)
class SuiteOptions:
    repo_root: Path
    cache_dir: Path
    results_dir: Path
    history_path: Path
    command: str
    offline_only: bool = False
    record: bool = False
    locomo_tier: str = "full"


@dataclass(frozen=True)
class SuiteExecution:
    result: SuiteResult
    report_path: Path
    history_recorded: bool


def default_options(
    *,
    command: str,
    offline_only: bool = False,
    record: bool = False,
    locomo_tier: str = "full",
    repo_root: Path | None = None,
) -> SuiteOptions:
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    return SuiteOptions(
        repo_root=root,
        cache_dir=root / "data/benchmarks/locomo",
        results_dir=root / "data/benchmarks/results",
        history_path=root / "docs/benchmarks/rp-memory-recall-history.md",
        command=command,
        offline_only=offline_only,
        record=record,
        locomo_tier=locomo_tier,
    )


def execute_suite(options: SuiteOptions) -> SuiteExecution:
    run_id, started_at = new_run_identity()
    options.results_dir.mkdir(parents=True, exist_ok=True)
    work_parent = options.repo_root / "data/benchmarks/work"
    work_parent.mkdir(parents=True, exist_ok=True)
    report_path = options.results_dir / f"{run_id}.md"
    expected_paths = _expected_paths(options, report_path)
    result: SuiteResult | None = None
    with tempfile.TemporaryDirectory(
        prefix=f"{run_id}-",
        dir=work_parent,
    ) as temporary:
        index_root = Path(temporary).resolve()
        expected_paths["temporary_indexes"] = index_root
        environment = capture_environment(
            run_id=run_id,
            started_at_utc=started_at,
            command=options.command,
            repo_root=options.repo_root,
            paths=expected_paths,
        )
        try:
            if options.record and options.locomo_tier != "full":
                raise ValueError("--record requires the full LoCoMo tier")
            locomo_paths = prepare_locomo(options.cache_dir)
            locomo_path = locomo_paths[options.locomo_tier]
            gold_path = Path(__file__).with_name("rp_gold.json")
            datasets = (
                load_jsonl_dataset(locomo_path),
                build_rp_gold_dataset(gold_path, load_rp_gold()),
            )
            detected, path_results = asyncio.run(
                _run_async(
                    datasets,
                    index_root=index_root,
                    offline_only=options.offline_only,
                )
            )
            result = SuiteResult(
                environment=environment,
                capability_matrix=detected.matrix,
                paths=path_results,
                finished_at_utc=_utc_now(),
            )
        except Exception as exc:
            error = _safe_error(exc)
            result = SuiteResult(
                environment=environment,
                capability_matrix=CapabilityMatrix(
                    service_status=BenchmarkStatus.SKIPPED_PROBE_FAILED,
                    service_reason="suite stopped before capability matrix completed",
                ),
                paths=(
                    BenchmarkPathResult(
                        path_id="suite",
                        status=BenchmarkStatus.FAILED,
                        reason=error,
                        pipeline=_failed_pipeline(),
                    ),
                ),
                finished_at_utc=_utc_now(),
                errors=(error,),
            )
        finally:
            if result is not None:
                write_report(report_path, render_full_report(result))
    assert result is not None
    history_recorded = False
    if options.record and result.successful:
        history_recorded = append_history(
            result,
            history_path=options.history_path,
            local_report_path=report_path,
        )
    return SuiteExecution(result, report_path.resolve(), history_recorded)


async def _run_async(datasets, *, index_root: Path, offline_only: bool):  # noqa: ANN001
    try:
        memory_settings = settings.memory_settings
        detected = await detect_capabilities(
            memory_settings,
            offline_only=offline_only,
        )
        paths = await run_benchmark_paths(
            datasets,
            memory_settings,
            detected,
            index_root=index_root,
            offline_only=offline_only,
            top_k=TOP_K,
        )
        return detected, paths
    finally:
        await LLMClientManager.areset()


def _expected_paths(options: SuiteOptions, report_path: Path) -> dict[str, Path]:
    raw_name = f"locomo10.{LOCOMO_COMMIT[:8]}.json"
    return {
        "repository": options.repo_root,
        "locomo_raw": options.cache_dir / raw_name,
        "locomo_full": options.cache_dir / "locomo.full.jsonl",
        "locomo_smoke": options.cache_dir / "locomo.smoke.jsonl",
        "locomo_manifest": options.cache_dir / "manifest.json",
        "rp_gold": Path(__file__).with_name("rp_gold.json"),
        "result_markdown": report_path,
        "tracked_history": options.history_path,
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _failed_pipeline() -> PipelineDescription:
    return PipelineDescription(
        planner="not-started",
        retrievers=(),
        fusion="not-started",
        reranker="not-started",
        top_k=TOP_K,
        vector_candidate_k=0,
        keyword_candidate_k=0,
        rerank_candidate_k=0,
        keyword_tokenizer="-",
        raw_md_mode="disabled",
        raw_md_min_results=0,
        weights=(),
        expanded_query_effect="not-started",
    )


def _safe_error(exc: Exception) -> str:
    import re

    value = f"{type(exc).__name__}: {' '.join(str(exc).split())[:600]}"
    value = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)\S+", r"\1[REDACTED]", value)
    return value
