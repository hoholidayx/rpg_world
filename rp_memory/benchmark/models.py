"""Typed records shared by benchmark discovery, execution, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BenchmarkStatus(StrEnum):
    EXECUTED = "executed"
    SKIPPED_DISABLED = "skipped_disabled"
    SKIPPED_UNCONFIGURED = "skipped_unconfigured"
    SKIPPED_SERVICE_UNREACHABLE = "skipped_service_unreachable"
    SKIPPED_PROBE_FAILED = "skipped_probe_failed"
    DEGRADED_RUNTIME_FALLBACK = "degraded_runtime_fallback"
    FAILED = "failed"


@dataclass(frozen=True)
class ProviderInfo:
    capability: str
    biz_key: str
    provider_key: str
    backend: str
    model: str
    is_default: bool = False
    dimension: int | None = None


@dataclass(frozen=True)
class CapabilityProbe:
    capability: str
    status: BenchmarkStatus
    reason: str
    provider: ProviderInfo | None = None


@dataclass(frozen=True)
class CapabilityMatrix:
    service_status: BenchmarkStatus
    service_reason: str
    probes: tuple[CapabilityProbe, ...] = ()

    def for_capability(self, capability: str) -> tuple[CapabilityProbe, ...]:
        return tuple(item for item in self.probes if item.capability == capability)

    def available(self, capability: str) -> tuple[CapabilityProbe, ...]:
        return tuple(
            item
            for item in self.for_capability(capability)
            if item.status is BenchmarkStatus.EXECUTED and item.provider is not None
        )

    def default(self, capability: str) -> CapabilityProbe | None:
        probes = self.for_capability(capability)
        return next(
            (
                item
                for item in probes
                if item.provider is not None and item.provider.is_default
            ),
            probes[0] if probes else None,
        )


@dataclass(frozen=True)
class PipelineDescription:
    planner: str
    retrievers: tuple[str, ...]
    fusion: str
    reranker: str
    top_k: int
    vector_candidate_k: int
    keyword_candidate_k: int
    rerank_candidate_k: int
    keyword_tokenizer: str
    raw_md_mode: str
    raw_md_min_results: int
    weights: tuple[tuple[str, float], ...]
    expanded_query_effect: str
    providers: tuple[ProviderInfo, ...] = ()

    @property
    def arrow(self) -> str:
        retrieval = "+".join(self.retrievers) if self.retrievers else "none"
        return (
            f"{self.planner} → {retrieval} → {self.fusion} → "
            f"{self.reranker} → Top-{self.top_k}"
        )


@dataclass(frozen=True)
class PlannerTrace:
    planner_source: str
    normalized_query: str
    keyword_queries: tuple[str, ...]
    expanded_queries: tuple[str, ...]
    raw_md_terms: tuple[str, ...]
    expanded_query_effect: str


@dataclass(frozen=True)
class RankedEvidence:
    rank: int
    evidence_id: str
    text_preview: str
    final_score: float
    scores: tuple[tuple[str, float | None], ...]
    source: str = ""
    file_path: str = ""


@dataclass(frozen=True)
class CaseResult:
    dataset: str
    sample_id: str
    question_id: str
    question: str
    gold_evidence: tuple[str, ...]
    forbidden_evidence: tuple[str, ...]
    no_answer: bool
    scored: bool
    issues: tuple[str, ...]
    planner_trace: PlannerTrace | None
    rankings: tuple[RankedEvidence, ...]


@dataclass(frozen=True)
class DatasetResult:
    dataset: str
    source_path: str
    metrics: dict[str, object]
    cases: tuple[CaseResult, ...]
    duration_seconds: float


@dataclass(frozen=True)
class BenchmarkPathResult:
    path_id: str
    status: BenchmarkStatus
    reason: str
    pipeline: PipelineDescription
    datasets: tuple[DatasetResult, ...] = ()
    duration_seconds: float = 0.0
    runtime_fallbacks: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkEnvironment:
    run_id: str
    started_at_utc: str
    command: str
    repo_root: str
    git_revision: str
    git_dirty: bool
    git_status_summary: str
    python_version: str
    sqlite_version: str
    jieba_version: str
    platform: str
    paths: tuple[tuple[str, str], ...]
    profile: str = ""
    llm_service_url: str = ""


@dataclass(frozen=True)
class SuiteResult:
    environment: BenchmarkEnvironment
    capability_matrix: CapabilityMatrix
    paths: tuple[BenchmarkPathResult, ...]
    finished_at_utc: str
    informational_only: bool = True
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def successful(self) -> bool:
        mandatory = {
            item.path_id: item
            for item in self.paths
            if item.path_id in {"offline.keyword_rule", "offline.local_fallback"}
        }
        baseline = mandatory.get("offline.keyword_rule")
        return (
            not self.errors
            and baseline is not None
            and baseline.status is BenchmarkStatus.EXECUTED
            and all(item.status is not BenchmarkStatus.FAILED for item in self.paths)
        )
