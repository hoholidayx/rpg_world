"""OpenAI-compatible reranker for hybrid memory retrieval."""

from __future__ import annotations

from openai import AsyncOpenAI

from rpg_world.rpg_core.memory.asyncio_utils import run_awaitable_sync
from rpg_world.rpg_core.memory.rerank.common import build_rerank_prompt, extract_text, parse_json_array
from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.retrieval.scoring import normalize_values


class OpenAIReranker:
    """Rerank candidates with an OpenAI-compatible chat model."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_candidates: int = 10,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        rerank_weight: float = 0.70,
    ) -> None:
        self._model = model
        self._max_candidates = max_candidates
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._rerank_weight = rerank_weight
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def rerank(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        if not candidates:
            return candidates
        return run_awaitable_sync(self._rerank_async(query, candidates))

    async def _rerank_async(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        head = candidates[: max(1, self._max_candidates)]
        tail = candidates[len(head) :]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a memory reranker."},
                    {"role": "user", "content": build_rerank_prompt(query, head)},
                ],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            text = extract_text(response.choices[0].message.content or "")
            parsed = parse_json_array(text)
        except Exception:
            return candidates

        scores = {
            str(item.get("id")): float(item.get("score", 0.0))
            for item in parsed
            if isinstance(item, dict)
        }
        reasons = {
            str(item.get("id")): str(item.get("reason", ""))
            for item in parsed
            if isinstance(item, dict)
        }
        if not scores:
            return candidates

        hybrid_norm = normalize_values(head, lambda item: item.hybrid_score)
        for candidate in head:
            key = str(candidate.memory_id)
            rerank_score = max(0.0, min(1.0, scores.get(key, 0.0) / 100.0))
            candidate.rerank_score = (
                self._rerank_weight * rerank_score
                + (1.0 - self._rerank_weight) * hybrid_norm[candidate.memory_id]
            )
            if key in reasons:
                candidate.debug["openai_reason"] = reasons[key]
            candidate.debug["openai_score_norm"] = rerank_score

        return sorted(head, key=lambda item: item.final_score, reverse=True) + tail
