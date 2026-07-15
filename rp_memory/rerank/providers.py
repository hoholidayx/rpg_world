"""Score providers used by the memory pointwise reranker."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from commons.types import DebugInfo

from llm_client.types import DocumentScoreProvider, LLMProvider, LLMResponse
from rp_memory.candidate import MemoryCandidate
from rp_memory.rerank.common import (
    MEMORY_RERANK_SYSTEM_PROMPT,
    build_pointwise_prompt,
    parse_pointwise_output,
    short_preview,
)


@dataclass(frozen=True)
class MemoryScore:
    """Normalized pointwise memory relevance score."""

    score: float
    reason: str = ""
    debug: DebugInfo = field(default_factory=dict)

    @property
    def clamped_score(self) -> float:
        return max(0.0, min(1.0, float(self.score)))


class MemoryScoreProvider(ABC):
    """Provider interface that returns one normalized score per candidate."""

    @abstractmethod
    async def score(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryScore]:
        """Return scores in the same order as *candidates*."""


class ChatPointwiseScoreProvider(MemoryScoreProvider):
    """Legacy chat-completion reranker that parses numeric text output."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_candidate_chars: int = 2400,
    ) -> None:
        self._provider = provider
        self._max_candidate_chars = max_candidate_chars

    async def score(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryScore]:
        return await asyncio.gather(
            *(self._score_one(query, candidate) for candidate in candidates),
        )

    async def _score_one(self, query: str, candidate: MemoryCandidate) -> MemoryScore:
        prompt = build_pointwise_prompt(query, candidate, max_candidate_chars=self._max_candidate_chars)
        response = await self._provider.chat(
            [
                {"role": "system", "content": MEMORY_RERANK_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        raw_text = _extract_response_text(response)
        raw_preview = short_preview(raw_text, limit=160)
        try:
            score, reason = parse_pointwise_output(raw_text)
        except Exception as exc:
            raise _RerankParseError(str(exc), preview=raw_preview) from exc
        return MemoryScore(
            score=max(0.0, min(1.0, score / 100.0)),
            reason=reason,
            debug={"raw": raw_preview, "source": "chat"},
        )


class LogitRerankProvider(MemoryScoreProvider):
    """Memory-score adapter for generic local yes/no-logit document rerank."""

    def __init__(self, provider: DocumentScoreProvider) -> None:
        self._provider = provider

    def get_default_model(self) -> str:
        get_default_model = getattr(self._provider, "get_default_model", None)
        if callable(get_default_model):
            return str(get_default_model())
        return type(self._provider).__name__

    async def score(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryScore]:
        documents = [candidate.content for candidate in candidates]
        raw_scores = await self._provider.score_documents(query, documents)
        if len(raw_scores) != len(documents):
            raise ValueError(f"rerank score count mismatch: expected={len(documents)} got={len(raw_scores)}")
        results: list[MemoryScore] = []
        for raw in raw_scores:
            results.append(
                MemoryScore(
                    score=raw.clamped_score,
                    reason=raw.reason,
                    debug=dict(raw.debug),
                )
            )
        return results


class _RerankParseError(Exception):
    def __init__(self, message: str, preview: str = "") -> None:
        super().__init__(message)
        self.preview = preview


def _extract_response_text(response: LLMResponse) -> str:
    if hasattr(response, "content"):
        return str(getattr(response, "content") or "")
    if isinstance(response, dict):
        return str(response.get("content") or response.get("text") or "")
    return str(response)
