"""Provider-agnostic memory rerank business logic."""

from __future__ import annotations

import re
import time

from loguru import logger

from llm_client.types import DocumentScoreProvider
from rp_memory.asyncio_utils import run_awaitable_sync
from rp_memory.candidate import MemoryCandidate
from rp_memory.rerank.base import MemoryReranker
from rp_memory.rerank.common import (
    blend_pointwise_scores,
)
from rp_memory.rerank.providers import ChatPointwiseScoreProvider, LogitRerankProvider, MemoryScoreProvider


class PointwiseMemoryReranker(MemoryReranker):
    """Generic reranker that fuses provider scores with hybrid retrieval scores."""

    def __init__(
        self,
        provider: object,
        *,
        rerank_weight: float = 0.70,
        provider_label: str = "llm",
        max_candidate_chars: int = 2400,
    ) -> None:
        self._provider = provider
        self._score_provider = _as_score_provider(provider, max_candidate_chars=max_candidate_chars)
        self._rerank_weight = rerank_weight
        self._provider_label = provider_label
        self._max_candidate_chars = max_candidate_chars

    def rerank(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        if not candidates:
            logger.info("[PointwiseMemoryReranker] skipped — no candidates")
            return candidates
        return run_awaitable_sync(self._rerank_async(query, candidates))

    async def _rerank_async(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        logger.info(
            "[PointwiseMemoryReranker] rerank start — provider={} query={!r} candidates={}",
            self._provider_label,
            query,
            len(candidates),
        )
        started_at = time.monotonic()
        scored: list[MemoryCandidate] = []
        pointwise_scores: dict[int, float] = {}
        reasons: dict[int, str] = {}
        pending: list[MemoryCandidate] = []
        for candidate in candidates:
            deterministic_score = _deterministic_score(query, candidate)
            if deterministic_score is None:
                pending.append(candidate)
                continue
            pointwise_scores[candidate.memory_id] = deterministic_score
            reasons[candidate.memory_id] = "deterministic exact/term match"
            candidate.debug[f"{self._provider_label}_source"] = "deterministic"
            scored.append(candidate)
            logger.info(
                "[PointwiseMemoryReranker] candidate scored — provider={} id={} score={:.2f} norm={:.3f} elapsed_ms=0 source=deterministic",
                self._provider_label,
                candidate.memory_id,
                deterministic_score,
                deterministic_score / 100.0,
            )
        if pending:
            provider_started_at = time.monotonic()
            try:
                score_results = await self._score_provider.score(query, pending)
            except Exception as exc:
                preview = getattr(exc, "preview", "")
                logger.warning(
                    "[PointwiseMemoryReranker] pointwise score failed — provider={} candidates={} fallback={} preview={!r}",
                    self._provider_label,
                    len(pending),
                    exc,
                    preview,
                )
                return candidates
            elapsed_ms = (time.monotonic() - provider_started_at) * 1000.0
            if len(score_results) != len(pending):
                logger.warning(
                    "[PointwiseMemoryReranker] pointwise score failed — provider={} candidates={} fallback=score count mismatch preview=''",
                    self._provider_label,
                    len(pending),
                )
                return candidates

            for candidate, score_result in zip(pending, score_results, strict=True):
                score_norm = score_result.clamped_score
                pointwise_scores[candidate.memory_id] = score_norm * 100.0
                _write_provider_debug(candidate, self._provider_label, score_result.debug)
                if score_result.reason:
                    reasons[candidate.memory_id] = score_result.reason
                scored.append(candidate)
                logger.info(
                    "[PointwiseMemoryReranker] candidate scored — provider={} id={} score={:.2f} norm={:.3f} elapsed_ms={:.0f} source={}",
                    self._provider_label,
                    candidate.memory_id,
                    score_norm * 100.0,
                    score_norm,
                    elapsed_ms,
                    score_result.debug.get("source", "provider"),
                )

        total_ms = (time.monotonic() - started_at) * 1000.0
        logger.info(
            "[PointwiseMemoryReranker] rerank done — provider={} total_ms={:.0f} scored={}",
            self._provider_label,
            total_ms,
            len(scored),
        )
        return blend_pointwise_scores(
            scored,
            pointwise_scores,
            reasons,
            self._rerank_weight,
            f"{self._provider_label}_score_norm",
            f"{self._provider_label}_reason",
        )


def _deterministic_score(query: str, candidate: MemoryCandidate) -> float | None:
    """Avoid LLM calls only for full-query exact hits."""
    content = candidate.content or ""
    normalized_query = " ".join((query or "").split())
    if not normalized_query:
        return None
    if candidate.exact_score >= 1.0 or _contains_text(content, normalized_query):
        return 100.0
    return None


def _contains_text(content: str, needle: str) -> bool:
    if not content or not needle:
        return False
    compact_needle = _compact(needle)
    if not compact_needle:
        return False
    return needle in content or compact_needle in _compact(content)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _as_score_provider(provider: object, *, max_candidate_chars: int) -> MemoryScoreProvider:
    if isinstance(provider, MemoryScoreProvider):
        return provider
    if isinstance(provider, DocumentScoreProvider):
        return LogitRerankProvider(provider)
    return ChatPointwiseScoreProvider(provider, max_candidate_chars=max_candidate_chars)  # type: ignore[arg-type]


def _write_provider_debug(candidate: MemoryCandidate, provider_label: str, debug: dict[str, object]) -> None:
    for key, value in debug.items():
        candidate.debug[f"{provider_label}_{key}"] = value
