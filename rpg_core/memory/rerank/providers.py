"""Score providers used by the memory pointwise reranker."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from rpg_world.rpg_core.common_types import DebugInfo


from rpg_world.rpg_core.llama_service.client import LlamaRerankModel
from rpg_world.rpg_core.llm.base_provider import LLMProvider
from rpg_world.rpg_core.llm.types import LLMResponse
from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.rerank.common import (
    MEMORY_RERANK_SYSTEM_PROMPT,
    build_pointwise_prompt,
    parse_pointwise_output,
    short_preview,
)


DEFAULT_QWEN_RERANK_INSTRUCTION = (
    "Given a user query, judge whether the candidate memory is relevant and useful for answering it."
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


class LogitRerankProvider(LLMProvider, MemoryScoreProvider):
    """Rerank provider backed by local model yes/no logits."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        instruction: str = DEFAULT_QWEN_RERANK_INSTRUCTION,
        max_length: int | None = None,
        model: LlamaRerankModel | None = None,
    ) -> None:
        self._model_path = str(Path(model_path))
        self._instruction = instruction or DEFAULT_QWEN_RERANK_INSTRUCTION
        self._max_length = max(1, int(max_length or n_ctx))
        self._model = model or LlamaRerankModel(
            self._model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )

    def get_default_model(self) -> str:
        return self._model_path

    async def score(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryScore]:
        documents = [candidate.content for candidate in candidates]
        raw_scores = await asyncio.to_thread(
            self._model.rerank,
            query,
            documents,
            instruction=self._instruction,
            max_length=self._max_length,
        )
        if len(raw_scores) != len(candidates):
            raise ValueError(f"rerank score count mismatch: expected={len(candidates)} got={len(raw_scores)}")
        results: list[MemoryScore] = []
        for raw in raw_scores:
            score = max(0.0, min(1.0, float(raw.get("score", 0.0))))
            yes_logit = float(raw.get("yes_logit", 0.0))
            no_logit = float(raw.get("no_logit", 0.0))
            results.append(
                MemoryScore(
                    score=score,
                    reason="yes/no logits",
                    debug={
                        "source": "logits",
                        "yes_logit": yes_logit,
                        "no_logit": no_logit,
                    },
                )
            )
        return results

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        raise NotImplementedError("LogitRerankProvider supports score(), not chat()")

    async def chat_stream(self, messages: list[dict], tools: list[dict] | None = None):
        raise NotImplementedError("LogitRerankProvider supports score(), not chat_stream()")


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
