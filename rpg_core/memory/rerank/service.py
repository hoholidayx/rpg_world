"""Provider-agnostic memory rerank business logic."""

from __future__ import annotations

import time

from loguru import logger

from rpg_world.rpg_core.memory.asyncio_utils import run_awaitable_sync
from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.rerank.base import MemoryReranker
from rpg_world.rpg_core.llm.base_provider import LLMProvider
from rpg_world.rpg_core.memory.rerank.common import (
    blend_pointwise_scores,
    build_pointwise_prompt,
    parse_pointwise_output,
    short_preview,
)


class PointwiseMemoryReranker(MemoryReranker):
    """Generic reranker that relies only on the ``LLMProvider`` abstraction."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        rerank_weight: float = 0.70,
        provider_label: str = "llm",
    ) -> None:
        self._provider = provider
        self._rerank_weight = rerank_weight
        self._provider_label = provider_label

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
        for candidate in candidates:
            try:
                score, reason, elapsed_ms = await self._score_candidate(query, candidate)
            except Exception as exc:
                preview = getattr(exc, "preview", "")
                logger.warning(
                    "[PointwiseMemoryReranker] pointwise score failed — provider={} candidate={} fallback={} preview={!r}",
                    self._provider_label,
                    candidate.memory_id,
                    exc,
                    preview,
                )
                return candidates

            pointwise_scores[candidate.memory_id] = score
            if reason:
                reasons[candidate.memory_id] = reason
            scored.append(candidate)
            logger.info(
                "[PointwiseMemoryReranker] candidate scored — provider={} id={} score={:.0f} elapsed_ms={:.0f}",
                self._provider_label,
                candidate.memory_id,
                score,
                elapsed_ms,
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

    async def _score_candidate(self, query: str, candidate: MemoryCandidate) -> tuple[float, str, float]:
        prompt = build_pointwise_prompt(query, candidate)
        started_at = time.monotonic()
        response = await self._provider.chat(
            [
                {"role": "system", "content": "你是一个本地记忆重排器。"},
                {"role": "user", "content": prompt},
            ]
        )
        elapsed_ms = (time.monotonic() - started_at) * 1000.0
        raw_text = _extract_response_text(response)
        try:
            score, reason = parse_pointwise_output(raw_text)
        except Exception as exc:
            raise _RerankParseError(str(exc), preview=short_preview(raw_text)) from exc
        return score, reason, elapsed_ms


class _RerankParseError(Exception):
    def __init__(self, message: str, preview: str = "") -> None:
        super().__init__(message)
        self.preview = preview


def _extract_response_text(response: object) -> str:
    if hasattr(response, "content"):
        return str(getattr(response, "content") or "")
    if isinstance(response, dict):
        return str(response.get("content") or response.get("text") or "")
    return str(response)
