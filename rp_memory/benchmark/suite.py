"""Top-level selectable benchmark workflow with guaranteed local reporting."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from llm_client.manager import LLMClientManager
from rp_memory.benchmark.capabilities import detect_capabilities
from rp_memory.benchmark.datasets import (
    DEFAULT_DATASETS,
    LOCOMO,
    LONGMEMEVAL_S,
    RP_GOLD,
    parse_datasets,
)
from rp_memory.benchmark.locomo import LOCOMO_COMMIT, prepare_locomo
from rp_memory.benchmark.longmemeval import (
    LONGMEMEVAL_REVISION,
    prepare_longmemeval,
)
from rp_memory.benchmark.models import (
    BenchmarkPathResult,
    BenchmarkStatus,
    CapabilityMatrix,
    PipelineDescription,
    SuiteResult,
)
from rp_memory.benchmark.report import (
    capture_environment,
    new_run_identity,
    record_summary,
    render_full_report,
    write_report,
)
from rp_memory.benchmark.rp_gold import load_rp_gold
from rp_memory.benchmark.runner import (
    TOP_K,
    BenchmarkDataset,
    build_rp_gold_dataset,
    load_jsonl_dataset,
    run_benchmark_paths,
)
from rpg_core.settings import settings


@dataclass(frozen=True)
class SuiteOptions:
    repo_root: Path
    data_dir: Path
    results_dir: Path
    tracked_runs_dir: Path
    report_index_path: Path
    command: str
    datasets: tuple[str, ...] = DEFAULT_DATASETS
    offline_only: bool = False
    record: bool = False
    locomo_tier: str = "full"


@dataclass(frozen=True)
class SuiteExecution:
    result: SuiteResult
    report_path: Path
    history_recorded: bool
    tracked_report_path: Path | None = None


def default_options(
    *,
    command: str,
    datasets: tuple[str, ...] = DEFAULT_DATASETS,
    offline_only: bool = False,
    record: bool = False,
    locomo_tier: str = "full",
    repo_root: Path | None = None,
) -> SuiteOptions:
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    return SuiteOptions(
        repo_root=root,
        data_dir=root / "data/benchmarks",
        results_dir=root / "data/benchmarks/results",
        tracked_runs_dir=root / "docs/benchmarks/runs",
        report_index_path=root / "docs/benchmarks/README.md",
        command=command,
        datasets=parse_datasets(datasets),
        offline_only=offline_only,
        record=record,
        locomo_tier=locomo_tier,
    )


def prepare_selected_datasets(
    data_dir: Path,
    datasets: tuple[str, ...],
    *,
    force: bool = False,
) -> dict[str, dict[str, Path]]:
    selected = parse_datasets(datasets)
    prepared: dict[str, dict[str, Path]] = {}
    if LOCOMO in selected:
        prepared[LOCOMO] = prepare_locomo(data_dir / LOCOMO, force=force)
    if LONGMEMEVAL_S in selected:
        prepared[LONGMEMEVAL_S] = prepare_longmemeval(
            data_dir / LONGMEMEVAL_S,
            force=force,
        )
    if RP_GOLD in selected:
        prepared[RP_GOLD] = {"source": Path(__file__).with_name("rp_gold.json")}
    return prepared


def execute_suite(options: SuiteOptions) -> SuiteExecution:
    run_id, started_at = new_run_identity()
    options.results_dir.mkdir(parents=True, exist_ok=True)
    work_parent = options.data_dir / "work"
    work_parent.mkdir(parents=True, exist_ok=True)
    report_path = options.results_dir / f"rp-memory-recall-full-{run_id}.md"
    expected_paths = _expected_paths(options, report_path)
    result: SuiteResult | None = None
    with tempfile.TemporaryDirectory(prefix=f"{run_id}-", dir=work_parent) as temporary:
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
            selected = parse_datasets(options.datasets)
            if options.record and LOCOMO in selected and options.locomo_tier != "full":
                raise ValueError("--record requires the full LoCoMo tier")
            prepared = prepare_selected_datasets(options.data_dir, selected)
            datasets = _load_datasets(selected, prepared, locomo_tier=options.locomo_tier)
            detected, path_results = asyncio.run(
                _run_async(datasets, index_root=index_root, offline_only=options.offline_only)
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
                paths=(BenchmarkPathResult(
                    path_id="suite",
                    status=BenchmarkStatus.FAILED,
                    reason=error,
                    pipeline=_failed_pipeline(),
                ),),
                finished_at_utc=_utc_now(),
                errors=(error,),
            )
        finally:
            if result is not None:
                write_report(report_path, render_full_report(result))
    assert result is not None
    history_recorded = False
    tracked_report_path: Path | None = None
    if options.record and result.successful:
        tracked_report_path, history_recorded = record_summary(
            result,
            runs_dir=options.tracked_runs_dir,
            index_path=options.report_index_path,
            local_report_path=report_path,
        )
    return SuiteExecution(
        result,
        report_path.resolve(),
        history_recorded,
        tracked_report_path,
    )


def _load_datasets(
    selected: tuple[str, ...],
    prepared: dict[str, dict[str, Path]],
    *,
    locomo_tier: str,
) -> tuple[BenchmarkDataset, ...]:
    datasets: list[BenchmarkDataset] = []
    for dataset in selected:
        paths = prepared[dataset]
        if dataset == LOCOMO:
            datasets.append(load_jsonl_dataset(paths[locomo_tier], dataset=LOCOMO))
        elif dataset == RP_GOLD:
            datasets.append(build_rp_gold_dataset(paths["source"], load_rp_gold()))
        elif dataset == LONGMEMEVAL_S:
            datasets.append(
                load_jsonl_dataset(paths["full"], dataset=LONGMEMEVAL_S)
            )
        else:  # pragma: no cover - parse_datasets owns this boundary
            raise ValueError(f"unsupported benchmark dataset: {dataset}")
    return tuple(datasets)


async def _run_async(
    datasets: tuple[BenchmarkDataset, ...],
    *,
    index_root: Path,
    offline_only: bool,
):  # noqa: ANN202
    try:
        memory_settings = settings.memory_settings
        detected = await detect_capabilities(memory_settings, offline_only=offline_only)
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
    selected = parse_datasets(options.datasets)
    paths = {
        "repository": options.repo_root,
        "result_markdown": report_path,
        "tracked_runs": options.tracked_runs_dir,
        "tracked_index": options.report_index_path,
    }
    if LOCOMO in selected:
        cache = options.data_dir / LOCOMO
        paths.update({
            "locomo_raw": cache / f"locomo10.{LOCOMO_COMMIT[:8]}.json",
            "locomo_full": cache / "locomo.full.jsonl",
            "locomo_smoke": cache / "locomo.smoke.jsonl",
            "locomo_manifest": cache / "manifest.json",
        })
    if RP_GOLD in selected:
        paths["rp_gold"] = Path(__file__).with_name("rp_gold.json")
    if LONGMEMEVAL_S in selected:
        cache = options.data_dir / LONGMEMEVAL_S
        paths.update({
            "longmemeval_raw": cache / f"longmemeval-s.{LONGMEMEVAL_REVISION[:8]}.json",
            "longmemeval_full": cache / "longmemeval-s.full.jsonl",
            "longmemeval_manifest": cache / "manifest.json",
        })
    return paths


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
