"""Execute the fixed LoCoMo and RP Gold recall path matrix."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rp_memory.benchmark.capabilities import DetectedCapabilities
from rp_memory.benchmark.metrics import evaluate_rankings, evaluate_rp_rankings
from rp_memory.benchmark.models import (
    BenchmarkPathResult,
    BenchmarkStatus,
    CapabilityProbe,
    CaseResult,
    DatasetResult,
    PipelineDescription,
    PlannerTrace,
    ProviderInfo,
    RankedEvidence,
)
from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.openai_planner import OpenAIQueryPlanner
from rp_memory.planning.plan import QueryPlan
from rp_memory.planning.planner import BaseQueryPlanner, RuleBasedQueryPlanner
from rp_memory.recall_query import RecallQueryContext
from rp_memory.rerank.base import MemoryReranker
from rp_memory.rerank.service import PointwiseMemoryReranker
from rp_memory.retrieval.hybrid_retriever import HybridRetriever
from rp_memory.retrieval.keyword_retriever import KeywordRetriever
from rp_memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch
from rp_memory.retrieval.raw_md_retriever import RawMarkdownRetriever
from rp_memory.retrieval.sqlvec_retriever import SqlVecRetriever
from rp_memory.storage.types import ChunkRecord
from rp_memory.storage.vector_store import VectorStore


TOP_K = 5
_BASELINE_WEIGHTS = (
    ("vector", 0.60),
    ("keyword", 0.25),
    ("raw_md", 0.05),
    ("exact", 0.10),
    ("expanded", 0.10),
    ("recency", 0.0),
    ("granularity", 0.05),
)


@dataclass(frozen=True)
class BenchmarkDataset:
    dataset: str
    source_path: Path
    samples: tuple[dict[str, object], ...]
    rp_constraints: bool = False


@dataclass(frozen=True)
class _PathSpec:
    path_id: str
    status: BenchmarkStatus
    reason: str
    pipeline: PipelineDescription
    jieba_dict: str
    embedding_provider: object | None = None
    planner_provider: object | None = None
    rerank_provider: object | None = None
    vector_only_when_available: bool = False

    @property
    def runnable(self) -> bool:
        return self.status in {
            BenchmarkStatus.EXECUTED,
            BenchmarkStatus.DEGRADED_RUNTIME_FALLBACK,
        }


class _TrackingEmbedding:
    def __init__(self, provider: object) -> None:
        self._provider = provider
        self.errors: list[str] = []

    def get_default_model(self) -> str:
        return str(self._provider.get_default_model())  # type: ignore[attr-defined]

    async def dimension(self) -> int:
        return int(await self._provider.dimension())  # type: ignore[attr-defined]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = await self._provider.embed(texts)  # type: ignore[attr-defined]
        except Exception as exc:
            self.errors.append(_safe_runtime_reason(exc))
            raise
        if len(vectors) != len(texts):
            error = f"embedding count mismatch: texts={len(texts)} vectors={len(vectors)}"
            self.errors.append(error)
            raise ValueError(error)
        return vectors


class _TrackingPlanner(BaseQueryPlanner):
    def __init__(self, provider: object, fallback: RuleBasedQueryPlanner, label: str) -> None:
        self._primary = OpenAIQueryPlanner(
            provider,  # type: ignore[arg-type]
            fallback_planner=fallback,
            planner_source=label,
        )
        self._fallback = fallback
        self.errors: list[str] = []

    async def plan(self, query: str) -> QueryPlan:
        try:
            return await self._primary.plan(query)
        except Exception as exc:
            self.errors.append(_safe_runtime_reason(exc))
            return await self._fallback.plan(query)

    async def plan_context(self, context: RecallQueryContext) -> QueryPlan:
        try:
            return await self._primary.plan_context(context)
        except Exception as exc:
            self.errors.append(_safe_runtime_reason(exc))
            return await self._fallback.plan_context(context)


class _TrackingReranker(MemoryReranker):
    def __init__(self, provider: object, *, weight: float, label: str) -> None:
        self._delegate = PointwiseMemoryReranker(
            provider,
            rerank_weight=weight,
            provider_label=label,
        )
        self.fallback_count = 0

    async def rerank(
        self,
        query: str,
        candidates: list[MemoryCandidate],
    ) -> list[MemoryCandidate]:
        result = await self._delegate.rerank(query, candidates)
        if result and any(candidate.rerank_score is None for candidate in result):
            self.fallback_count += 1
        return result


class _BenchmarkRawMarkdownRetriever(RawMarkdownRetriever):
    """Align raw-file candidates with path-independent benchmark evidence IDs."""

    async def search_plan_async(
        self,
        plan: QueryPlan,
        top_k: int = 5,
    ) -> list[MemoryCandidate]:
        candidates = await super().search_plan_async(plan, top_k=top_k)
        for candidate in candidates:
            benchmark_id = candidate.metadata.get("benchmark_memory_id")
            if benchmark_id is None:
                raise ValueError("benchmark raw candidate is missing benchmark_memory_id")
            candidate.memory_id = int(benchmark_id)
        return candidates


def load_jsonl_dataset(path: Path, *, dataset: str = "locomo") -> BenchmarkDataset:
    samples = tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    return BenchmarkDataset(dataset, path.resolve(), samples, rp_constraints=False)


def build_rp_gold_dataset(path: Path, samples: list[dict[str, object]]) -> BenchmarkDataset:
    return BenchmarkDataset(
        "rp-gold",
        path.resolve(),
        tuple(samples),
        rp_constraints=True,
    )


def build_path_specs(
    memory_settings,
    capabilities: DetectedCapabilities,
    *,
    offline_only: bool,
    top_k: int = TOP_K,
) -> tuple[_PathSpec, ...]:
    specs: list[_PathSpec] = [
        _PathSpec(
            path_id="offline.keyword_rule",
            status=BenchmarkStatus.EXECUTED,
            reason="frozen deterministic keyword/rule baseline",
            pipeline=_pipeline(
                planner="rule_based",
                retrievers=("keyword",),
                fusion="hybrid",
                reranker="disabled",
                top_k=top_k,
                vector_k=50,
                keyword_k=50,
                rerank_k=8,
                tokenizer="jieba",
                raw_mode="disabled",
                raw_min=0,
                weights=_BASELINE_WEIGHTS,
                expanded_effect="existing-candidate scoring only",
            ),
            jieba_dict="",
        )
    ]
    configured_weights = _configured_weights(memory_settings)
    raw_mode = str(memory_settings.raw_md_mode)
    specs.append(
        _PathSpec(
            path_id="offline.local_fallback",
            status=(
                BenchmarkStatus.SKIPPED_DISABLED
                if raw_mode == "disabled"
                else BenchmarkStatus.EXECUTED
            ),
            reason=(
                "memory.raw_md_mode is disabled"
                if raw_mode == "disabled"
                else f"keyword plus configured raw markdown mode={raw_mode}"
            ),
            pipeline=_pipeline(
                planner="rule_based",
                retrievers=("keyword",) if raw_mode == "disabled" else ("keyword", "raw-md"),
                fusion="hybrid",
                reranker="disabled",
                top_k=top_k,
                vector_k=int(memory_settings.vector_k),
                keyword_k=int(memory_settings.keyword_k),
                rerank_k=int(memory_settings.rerank_candidate_k),
                tokenizer=str(memory_settings.keyword_tokenizer),
                raw_mode=raw_mode,
                raw_min=int(memory_settings.raw_md_min_results),
                weights=configured_weights,
                expanded_effect="raw-md candidate generation and existing-candidate scoring",
            ),
            jieba_dict=str(memory_settings.jieba_dict or ""),
        )
    )

    for capability in ("embedding", "planner", "reranker"):
        probes = capabilities.matrix.for_capability(capability)
        if not probes:
            probes = (
                CapabilityProbe(
                    capability=capability,
                    status=BenchmarkStatus.SKIPPED_UNCONFIGURED,
                    reason="capability probe produced no provider entry",
                ),
            )
        for probe in probes:
            specs.append(
                _individual_spec(
                    memory_settings,
                    capabilities,
                    capability,
                    probe,
                    configured_weights,
                    top_k,
                )
            )

    specs.append(
        _effective_spec(
            memory_settings,
            capabilities,
            configured_weights,
            offline_only=offline_only,
            top_k=top_k,
        )
    )
    return tuple(specs)


async def run_benchmark_paths(
    datasets: tuple[BenchmarkDataset, ...],
    memory_settings,
    capabilities: DetectedCapabilities,
    *,
    index_root: Path,
    offline_only: bool,
    top_k: int = TOP_K,
) -> tuple[BenchmarkPathResult, ...]:
    index_root.mkdir(parents=True, exist_ok=True)
    results: list[BenchmarkPathResult] = []
    for spec in build_path_specs(
        memory_settings,
        capabilities,
        offline_only=offline_only,
        top_k=top_k,
    ):
        if not spec.runnable:
            results.append(
                BenchmarkPathResult(
                    path_id=spec.path_id,
                    status=spec.status,
                    reason=spec.reason,
                    pipeline=spec.pipeline,
                )
            )
            continue
        try:
            results.append(
                await _run_path(
                    spec,
                    datasets,
                    index_root=index_root / _safe_component(spec.path_id),
                )
            )
        except Exception as exc:
            results.append(
                BenchmarkPathResult(
                    path_id=spec.path_id,
                    status=BenchmarkStatus.FAILED,
                    reason=_safe_runtime_reason(exc),
                    pipeline=spec.pipeline,
                )
            )
    return tuple(results)


async def _run_path(
    spec: _PathSpec,
    datasets: tuple[BenchmarkDataset, ...],
    *,
    index_root: Path,
) -> BenchmarkPathResult:
    started = time.monotonic()
    fallback = RuleBasedQueryPlanner(jieba_dict=spec.jieba_dict or None)
    embedding = (
        _TrackingEmbedding(spec.embedding_provider)
        if spec.embedding_provider is not None
        else None
    )
    planner: BaseQueryPlanner
    tracking_planner: _TrackingPlanner | None = None
    if spec.planner_provider is not None:
        provider = _provider_info(spec.pipeline.providers, "planner")
        label = f"benchmark:{provider.provider_key if provider else 'planner'}"
        tracking_planner = _TrackingPlanner(spec.planner_provider, fallback, label)
        planner = tracking_planner
    else:
        planner = fallback
    tracking_reranker: _TrackingReranker | None = None
    if spec.rerank_provider is not None:
        provider = _provider_info(spec.pipeline.providers, "reranker")
        label = f"benchmark_{_safe_component(provider.provider_key if provider else 'reranker')}"
        tracking_reranker = _TrackingReranker(
            spec.rerank_provider,
            weight=dict(spec.pipeline.weights).get("rerank", 0.70),
            label=label,
        )

    dataset_results: list[DatasetResult] = []
    runtime_notes: list[str] = []
    for dataset in datasets:
        dataset_results.append(
            await _evaluate_dataset(
                dataset,
                spec,
                planner=planner,
                embedding=embedding,
                reranker=tracking_reranker,
                index_root=index_root / _safe_component(dataset.dataset),
                runtime_notes=runtime_notes,
            )
        )
    if embedding is not None and embedding.errors:
        runtime_notes.append(
            f"embedding runtime fallback count={len(embedding.errors)}; last={embedding.errors[-1]}"
        )
    if tracking_planner is not None and tracking_planner.errors:
        runtime_notes.append(
            f"planner rule fallback count={len(tracking_planner.errors)}; "
            f"last={tracking_planner.errors[-1]}"
        )
    if tracking_reranker is not None and tracking_reranker.fallback_count:
        runtime_notes.append(
            f"reranker hybrid-score fallback count={tracking_reranker.fallback_count}"
        )
    runtime_notes = list(dict.fromkeys(runtime_notes))
    status = spec.status
    reason = spec.reason
    if runtime_notes:
        status = BenchmarkStatus.DEGRADED_RUNTIME_FALLBACK
        reason = "; ".join([reason, *runtime_notes])
    return BenchmarkPathResult(
        path_id=spec.path_id,
        status=status,
        reason=reason,
        pipeline=spec.pipeline,
        datasets=tuple(dataset_results),
        duration_seconds=time.monotonic() - started,
        runtime_fallbacks=tuple(runtime_notes),
    )


async def _evaluate_dataset(
    dataset: BenchmarkDataset,
    spec: _PathSpec,
    *,
    planner: BaseQueryPlanner,
    embedding: _TrackingEmbedding | None,
    reranker: _TrackingReranker | None,
    index_root: Path,
    runtime_notes: list[str],
) -> DatasetResult:
    started = time.monotonic()
    index_root.mkdir(parents=True, exist_ok=True)
    metric_cases: list[tuple[list[str], list[str]]] = []
    rp_metric_cases: list[tuple[list[str], list[str], list[str]]] = []
    case_results: list[CaseResult] = []
    unscored = 0
    for sample in dataset.samples:
        sample_id = str(sample.get("sample_id", "") or "sample")
        sample_root = index_root / _safe_component(sample_id)
        raw_dir = sample_root / "raw"
        records = _materialize_documents(dataset.dataset, sample_id, sample, raw_dir)
        embeddings: list[list[float]] | None = None
        dimension: int | None = None
        if embedding is not None:
            provider = _provider_info(spec.pipeline.providers, "embedding")
            dimension = provider.dimension if provider is not None else None
            try:
                embeddings = await _embed_documents(
                    embedding,
                    [record.text for record in records],
                    dimension=dimension,
                )
            except Exception:
                embeddings = None
                dimension = None
        db_path = sample_root / "recall.db"
        store = VectorStore(
            db_path,
            dimension=dimension,
            keyword_tokenizer=spec.pipeline.keyword_tokenizer,
            jieba_dict=spec.jieba_dict,
        )
        try:
            store.upsert(records, embeddings)
            if dimension is not None and not store.vector_enabled:
                runtime_notes.append(f"{dataset.dataset}/{sample_id}: vector backend unavailable")
            sqlvec = (
                SqlVecRetriever(store, embedding)
                if embedding is not None and store.vector_enabled
                else None
            )
            keyword = KeywordRetriever(store, limit=spec.pipeline.keyword_candidate_k)
            raw_retriever = None
            if spec.pipeline.raw_md_mode != "disabled":
                raw_retriever = _BenchmarkRawMarkdownRetriever(
                    RawMarkdownGrepSearch(
                        [raw_dir],
                        rule_based_planner=RuleBasedQueryPlanner(
                            jieba_dict=spec.jieba_dict or None
                        ),
                    )
                )
            hybrid = _build_hybrid(
                spec.pipeline,
                sqlvec=sqlvec,
                keyword=keyword,
                raw=raw_retriever,
                planner=planner,
                reranker=reranker,
            )
            for question in sample.get("questions", []):
                if not isinstance(question, dict):
                    raise ValueError(f"{dataset.dataset}/{sample_id} question must be an object")
                gold = [
                    str(value)
                    for value in question.get(
                        "gold_evidence",
                        question.get("evidence", []),
                    )
                ]
                forbidden = [str(value) for value in question.get("forbidden_evidence", [])]
                no_answer = bool(question.get("no_answer", False))
                question_id = str(question.get("id", "") or "")
                question_text = str(question.get("question", "") or "")
                if not gold and not no_answer:
                    unscored += 1
                    case_results.append(
                        CaseResult(
                            dataset=dataset.dataset,
                            sample_id=sample_id,
                            question_id=question_id,
                            question=question_text,
                            gold_evidence=(),
                            forbidden_evidence=tuple(forbidden),
                            no_answer=False,
                            scored=False,
                            issues=("unscored_missing_gold_evidence",),
                            planner_trace=None,
                            rankings=(),
                        )
                    )
                    continue
                context = RecallQueryContext(
                    current_input=question_text,
                    recent_turns=tuple(str(value) for value in question.get("recent_turns", [])),
                    player_character=str(question.get("player_character", "") or ""),
                    scene_time=str(question.get("scene_time", "") or ""),
                    scene_location=str(question.get("scene_location", "") or ""),
                )
                plan = await planner.plan_context(context)
                vector_only = spec.vector_only_when_available and sqlvec is not None
                if vector_only:
                    try:
                        candidates = await sqlvec.search_plan(
                            plan,
                            top_k=spec.pipeline.top_k,
                        )
                    except Exception as exc:
                        runtime_notes.append(
                            f"{dataset.dataset}/{question_id}: vector-only query fell back to local hybrid: "
                            f"{_safe_runtime_reason(exc)}"
                        )
                        vector_only = False
                        candidates = await hybrid.hybrid_search(
                            plan,
                            top_k=spec.pipeline.top_k,
                        )
                else:
                    candidates = await hybrid.hybrid_search(
                        plan,
                        top_k=spec.pipeline.top_k,
                    )
                rankings = tuple(
                    _ranked_evidence(
                        candidate,
                        rank=index,
                        vector_only=vector_only,
                    )
                    for index, candidate in enumerate(candidates, start=1)
                )
                ranked_ids = [item.evidence_id for item in rankings if item.evidence_id]
                metric_cases.append((gold, ranked_ids))
                rp_metric_cases.append((gold, forbidden, ranked_ids))
                issues = _case_issues(
                    gold,
                    forbidden,
                    ranked_ids,
                    no_answer=no_answer,
                    top_k=spec.pipeline.top_k,
                )
                case_results.append(
                    CaseResult(
                        dataset=dataset.dataset,
                        sample_id=sample_id,
                        question_id=question_id,
                        question=question_text,
                        gold_evidence=tuple(gold),
                        forbidden_evidence=tuple(forbidden),
                        no_answer=no_answer,
                        scored=True,
                        issues=tuple(issues),
                        planner_trace=PlannerTrace(
                            planner_source=plan.planner_source,
                            normalized_query=plan.normalized_query,
                            keyword_queries=plan.keyword_queries,
                            expanded_queries=plan.expanded_queries,
                            raw_md_terms=plan.raw_md_terms,
                            expanded_query_effect=spec.pipeline.expanded_query_effect,
                        ),
                        rankings=rankings,
                    )
                )
        finally:
            store.close()
    metric_values = (
        evaluate_rp_rankings(rp_metric_cases, top_k=spec.pipeline.top_k)
        if dataset.rp_constraints
        else evaluate_rankings(
            metric_cases,
            top_k=spec.pipeline.top_k,
            unscored_cases=unscored,
        )
    )
    metrics: dict[str, object] = asdict(metric_values)
    traces = [
        case.planner_trace
        for case in case_results
        if case.scored and case.planner_trace is not None
    ]
    source_counts: dict[str, int] = {}
    for trace in traces:
        source_counts[trace.planner_source] = source_counts.get(trace.planner_source, 0) + 1
    metrics.update({
        "planner_trace_cases": len(traces),
        "planner_source_counts": source_counts,
        "expanded_query_cases": sum(bool(trace.expanded_queries) for trace in traces),
        "expanded_query_total": sum(len(trace.expanded_queries) for trace in traces),
    })
    return DatasetResult(
        dataset=dataset.dataset,
        source_path=str(dataset.source_path),
        metrics=metrics,
        cases=tuple(case_results),
        duration_seconds=time.monotonic() - started,
    )


def _individual_spec(
    memory_settings,
    capabilities: DetectedCapabilities,
    capability: str,
    probe: CapabilityProbe,
    weights: tuple[tuple[str, float], ...],
    top_k: int,
) -> _PathSpec:
    provider = probe.provider
    suffix = _safe_component(provider.provider_key if provider is not None else "default")
    path_segment = "rerank" if capability == "reranker" else capability
    path_id = f"configured.{path_segment}.{suffix}"
    handle = None
    if probe.status is BenchmarkStatus.EXECUTED and provider is not None:
        handle = capabilities.handle(capability, provider.provider_key)
    planner = "rule_based"
    retrievers = ("keyword",)
    reranker = "disabled"
    expanded_effect = "existing-candidate scoring only"
    if capability == "embedding":
        retrievers = ("vector", "keyword")
        expanded_effect = "vector candidate generation and existing-candidate scoring"
    elif capability == "planner":
        planner = f"llm:{provider.provider_key if provider else 'default'}+rule-fallback"
    else:
        reranker = f"pointwise:{provider.provider_key if provider else 'default'}"
    pipeline = _pipeline(
        planner=planner,
        retrievers=retrievers,
        fusion="hybrid",
        reranker=reranker,
        top_k=top_k,
        vector_k=int(memory_settings.vector_k),
        keyword_k=int(memory_settings.keyword_k),
        rerank_k=int(memory_settings.rerank_candidate_k),
        tokenizer=str(memory_settings.keyword_tokenizer),
        raw_mode="disabled",
        raw_min=0,
        weights=weights,
        expanded_effect=expanded_effect,
        providers=(provider,) if provider is not None else (),
        rerank_weight=float(memory_settings.rerank_score_weight),
    )
    return _PathSpec(
        path_id=path_id,
        status=probe.status,
        reason=probe.reason,
        pipeline=pipeline,
        jieba_dict=str(memory_settings.jieba_dict or ""),
        embedding_provider=handle if capability == "embedding" else None,
        planner_provider=handle if capability == "planner" else None,
        rerank_provider=handle if capability == "reranker" else None,
    )


def _effective_spec(
    memory_settings,
    capabilities: DetectedCapabilities,
    weights: tuple[tuple[str, float], ...],
    *,
    offline_only: bool,
    top_k: int,
) -> _PathSpec:
    if offline_only:
        status = BenchmarkStatus.SKIPPED_DISABLED
        reason = "--offline-only disables configured.effective"
    elif not memory_settings.enabled:
        status = BenchmarkStatus.SKIPPED_DISABLED
        reason = "memory.enabled is false"
    else:
        status = BenchmarkStatus.EXECUTED
        reason = "default configured capabilities available"

    desired = ["embedding"]
    if memory_settings.query_planner_enabled:
        desired.append("planner")
    if memory_settings.rerank_enabled:
        desired.append("reranker")
    selected: dict[str, CapabilityProbe] = {}
    missing: list[str] = []
    if not offline_only and memory_settings.enabled:
        for capability in desired:
            probe = capabilities.matrix.default(capability)
            if (
                probe is not None
                and probe.status is BenchmarkStatus.EXECUTED
                and probe.provider is not None
            ):
                selected[capability] = probe
            else:
                detail = probe.reason if probe is not None else "no provider probe"
                missing.append(f"{capability}: {detail}")
        if missing:
            status = BenchmarkStatus.DEGRADED_RUNTIME_FALLBACK
            reason = "configured defaults unavailable; local fallback will run: " + "; ".join(missing)

    providers = tuple(
        probe.provider
        for capability in ("embedding", "planner", "reranker")
        if (probe := selected.get(capability)) is not None and probe.provider is not None
    )
    handles = {
        capability: capabilities.handle(capability, probe.provider.provider_key)
        for capability, probe in selected.items()
        if probe.provider is not None
    }
    embedding_available = "embedding" in selected
    hybrid = bool(memory_settings.hybrid_enabled or not embedding_available)
    retrievers: list[str] = []
    if embedding_available:
        retrievers.append("vector")
    if hybrid:
        retrievers.append("keyword")
        if str(memory_settings.raw_md_mode) != "disabled":
            retrievers.append("raw-md")
    planner_label = "rule_based"
    if "planner" in selected:
        planner_label = f"llm:{selected['planner'].provider.provider_key}+rule-fallback"  # type: ignore[union-attr]
    reranker_label = "disabled"
    rerank_handle = handles.get("reranker") if hybrid else None
    if rerank_handle is not None:
        reranker_label = f"pointwise:{selected['reranker'].provider.provider_key}"  # type: ignore[union-attr]
    elif "reranker" in selected and not hybrid:
        reranker_label = "not-applied-by-vector-only-runtime"
    raw_mode = str(memory_settings.raw_md_mode) if hybrid else "disabled"
    expanded_effect = (
        "vector/raw-md candidate generation and existing-candidate scoring"
        if embedding_available and raw_mode != "disabled"
        else "vector candidate generation and existing-candidate scoring"
        if embedding_available
        else "raw-md candidate generation and existing-candidate scoring"
        if raw_mode != "disabled"
        else "existing-candidate scoring only"
    )
    return _PathSpec(
        path_id="configured.effective",
        status=status,
        reason=reason,
        pipeline=_pipeline(
            planner=planner_label,
            retrievers=tuple(retrievers),
            fusion="hybrid" if hybrid else "vector-only",
            reranker=reranker_label,
            top_k=top_k,
            vector_k=int(memory_settings.vector_k),
            keyword_k=int(memory_settings.keyword_k),
            rerank_k=int(memory_settings.rerank_candidate_k),
            tokenizer=str(memory_settings.keyword_tokenizer),
            raw_mode=raw_mode,
            raw_min=int(memory_settings.raw_md_min_results),
            weights=weights,
            expanded_effect=expanded_effect,
            providers=providers,
            rerank_weight=float(memory_settings.rerank_score_weight),
        ),
        jieba_dict=str(memory_settings.jieba_dict or ""),
        embedding_provider=handles.get("embedding"),
        planner_provider=handles.get("planner"),
        rerank_provider=rerank_handle,
        vector_only_when_available=not hybrid,
    )


def _pipeline(
    *,
    planner: str,
    retrievers: tuple[str, ...],
    fusion: str,
    reranker: str,
    top_k: int,
    vector_k: int,
    keyword_k: int,
    rerank_k: int,
    tokenizer: str,
    raw_mode: str,
    raw_min: int,
    weights: tuple[tuple[str, float], ...],
    expanded_effect: str,
    providers: tuple[ProviderInfo, ...] = (),
    rerank_weight: float | None = None,
) -> PipelineDescription:
    normalized_weights = weights
    if rerank_weight is not None:
        normalized_weights = (*weights, ("rerank", rerank_weight))
    return PipelineDescription(
        planner=planner,
        retrievers=retrievers,
        fusion=fusion,
        reranker=reranker,
        top_k=top_k,
        vector_candidate_k=max(1, vector_k),
        keyword_candidate_k=max(1, keyword_k),
        rerank_candidate_k=max(1, rerank_k),
        keyword_tokenizer=tokenizer,
        raw_md_mode=raw_mode,
        raw_md_min_results=max(0, raw_min),
        weights=normalized_weights,
        expanded_query_effect=expanded_effect,
        providers=providers,
    )


def _configured_weights(memory_settings) -> tuple[tuple[str, float], ...]:
    return (
        ("vector", float(memory_settings.hybrid_vector_weight)),
        ("keyword", float(memory_settings.hybrid_keyword_weight)),
        ("raw_md", float(memory_settings.hybrid_raw_md_weight)),
        ("exact", float(memory_settings.hybrid_exact_weight)),
        ("expanded", float(memory_settings.hybrid_expanded_weight)),
        ("recency", 0.0),
        ("granularity", float(memory_settings.hybrid_granularity_weight)),
    )


def _build_hybrid(
    pipeline: PipelineDescription,
    *,
    sqlvec: SqlVecRetriever | None,
    keyword: KeywordRetriever,
    raw: RawMarkdownRetriever | None,
    planner: BaseQueryPlanner,
    reranker: MemoryReranker | None,
) -> HybridRetriever:
    weights = dict(pipeline.weights)
    return HybridRetriever(
        sqlvec_retriever=sqlvec,
        keyword_retriever=keyword,
        raw_md_retriever=raw,
        query_planner=planner,
        reranker=reranker,
        hybrid_vector_weight=weights.get("vector", 0.0),
        hybrid_keyword_weight=weights.get("keyword", 0.0),
        hybrid_raw_md_weight=weights.get("raw_md", 0.0),
        hybrid_exact_weight=weights.get("exact", 0.0),
        hybrid_expanded_weight=weights.get("expanded", 0.0),
        hybrid_recency_weight=0.0,
        hybrid_granularity_weight=weights.get("granularity", 0.0),
        raw_md_mode=pipeline.raw_md_mode,
        raw_md_min_results=pipeline.raw_md_min_results,
        keyword_tokenizer=pipeline.keyword_tokenizer,
        rerank_candidate_k=pipeline.rerank_candidate_k,
        vector_candidate_k=pipeline.vector_candidate_k,
        keyword_candidate_k=pipeline.keyword_candidate_k,
    )


def _materialize_documents(
    dataset: str,
    sample_id: str,
    sample: dict[str, object],
    raw_dir: Path,
) -> list[ChunkRecord]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    documents = sample.get("documents", [])
    if not isinstance(documents, list):
        raise ValueError(f"{dataset}/{sample_id} documents must be a list")
    records: list[ChunkRecord] = []
    memory_ids: set[int] = set()
    for index, document in enumerate(documents, start=1):
        if not isinstance(document, dict):
            raise ValueError(f"{dataset}/{sample_id} document must be an object")
        evidence_id = str(document.get("id", "") or "")
        text = str(document.get("text", "") or "")
        if not evidence_id or not text.strip():
            raise ValueError(f"{dataset}/{sample_id} document id/text must not be empty")
        memory_id = _stable_memory_id(dataset, sample_id, evidence_id)
        if memory_id in memory_ids:
            raise ValueError(f"{dataset}/{sample_id} benchmark memory ID collision")
        memory_ids.add(memory_id)
        raw_path = raw_dir / f"{index:04d}-{_safe_component(evidence_id)}.md"
        raw_metadata = document.get("metadata", {})
        if not isinstance(raw_metadata, dict):
            raise ValueError(f"{dataset}/{sample_id}/{evidence_id} metadata must be an object")
        front_matter = {
            **{
                key: value
                for key, value in raw_metadata.items()
                if isinstance(value, (str, int, float, bool))
            },
            "evidence_id": evidence_id,
            "source": dataset,
            "benchmark_memory_id": memory_id,
        }
        raw_path.write_text(
            _render_raw_document(front_matter, text),
            encoding="utf-8",
        )
        metadata: dict[str, object] = dict(raw_metadata)
        metadata.update({
            "source": dataset,
            "file": str(raw_path),
            "benchmark_raw_file": str(raw_path),
            "chunk_idx": 0,
            "evidence_id": evidence_id,
            "benchmark_memory_id": memory_id,
        })
        for key in ("session", "date"):
            if document.get(key) not in (None, ""):
                metadata[key] = document[key]
        records.append(
            ChunkRecord(
                id=memory_id,
                text=text,
                metadata=metadata,
            )
        )
    return records


async def _embed_documents(
    embedding: _TrackingEmbedding,
    texts: list[str],
    *,
    dimension: int | None,
    batch_size: int = 64,
) -> list[list[float]]:
    if dimension is None or dimension <= 0:
        raise ValueError("embedding provider dimension was not recorded by capability probe")
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = await embedding.embed(texts[start : start + batch_size])
        if any(len(vector) != dimension for vector in batch):
            raise ValueError("document embedding dimension mismatch")
        vectors.extend(batch)
    return vectors


def _ranked_evidence(
    candidate: MemoryCandidate,
    *,
    rank: int,
    vector_only: bool,
) -> RankedEvidence:
    scores = (
        ("vector", candidate.vector_score),
        ("keyword", candidate.keyword_score),
        ("raw_md", candidate.raw_md_score),
        ("exact", candidate.exact_score),
        ("fuzzy", candidate.fuzzy_score),
        ("expanded", candidate.expanded_score),
        ("recency", candidate.recency_score),
        ("granularity", candidate.granularity_score),
        ("hybrid", candidate.hybrid_score),
        ("rerank", candidate.rerank_score),
    )
    return RankedEvidence(
        rank=rank,
        evidence_id=str(candidate.metadata.get("evidence_id", "") or ""),
        text_preview=" ".join(candidate.content.split())[:240],
        final_score=(candidate.vector_score if vector_only else candidate.final_score),
        scores=scores,
        source=str(candidate.metadata.get("source", "") or ""),
        file_path=str(candidate.metadata.get("file", "") or ""),
    )


def _case_issues(
    gold_values: list[str],
    forbidden_values: list[str],
    ranked_values: list[str],
    *,
    no_answer: bool,
    top_k: int,
) -> list[str]:
    gold = set(gold_values)
    forbidden = set(forbidden_values)
    ranked = ranked_values[:top_k]
    issues: list[str] = []
    if no_answer:
        if ranked:
            issues.append("no_answer_false_positive")
    elif gold:
        if not ranked or ranked[0] not in gold:
            issues.append("hit_at_1_miss")
        matched = gold.intersection(ranked)
        if not matched:
            issues.append("recall_at_k_miss")
        elif len(matched) < len(gold):
            issues.append("partial_evidence_coverage")
    if ranked and ranked[0] in forbidden:
        issues.append("forbidden_at_1")
    if forbidden.intersection(ranked):
        issues.append("forbidden_hit_at_k")
    first_gold = min((i for i, value in enumerate(ranked) if value in gold), default=len(ranked) + 1)
    first_forbidden = min(
        (i for i, value in enumerate(ranked) if value in forbidden),
        default=len(ranked) + 1,
    )
    if forbidden and first_forbidden < first_gold:
        issues.append("forbidden_before_gold")
    return issues


def _render_raw_document(metadata: dict[str, object], text: str) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value).lower()
        lines.append(f"{key}: {rendered}")
    lines.extend(("---", text, ""))
    return "\n".join(lines)


def _stable_memory_id(dataset: str, sample_id: str, evidence_id: str) -> int:
    identity = json.dumps(
        [dataset, sample_id, evidence_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return int(digest, 16) % (2**63 - 1) + 1


def _provider_info(providers: tuple[ProviderInfo, ...], capability: str) -> ProviderInfo | None:
    return next((provider for provider in providers if provider.capability == capability), None)


def _safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return normalized[:96] or "default"


def _safe_runtime_reason(exc: Exception) -> str:
    value = " ".join(str(exc or type(exc).__name__).split())[:400]
    value = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", value)
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)\S+", r"\1[REDACTED]", value)
    return value or type(exc).__name__
