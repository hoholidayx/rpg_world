"""Local llama.cpp reranker for hybrid memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from rpg_world.rpg_core.memory.rerank.common import build_rerank_prompt, extract_text, parse_json_array
from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.retrieval.scoring import normalize_values


@dataclass
class LlamaRerankConfig:
    enabled: bool = False
    model_path: str = ""
    max_candidates: int = 10
    n_ctx: int = 4096
    n_gpu_layers: int = 0
    temperature: float = 0.0
    request_timeout_ms: int = 60000
    llama_weight: float = 0.70
    """Reranker 融合评分中 LLM 分的权重（剩余 ``1 - llama_weight`` 为混合分权重）。"""


class LlamaReranker:
    """Rerank candidates with a process-isolated llama.cpp model."""

    def __init__(self, config: LlamaRerankConfig) -> None:
        self._config = config
        self._model: Any | None = None

    def rerank(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        """Return reranked candidates, falling back to hybrid scores on failure."""
        if not self._config.enabled:
            logger.info("[LlamaReranker] skipped — disabled")
            return candidates
        if not candidates:
            logger.info("[LlamaReranker] skipped — no candidates")
            return candidates
        model_path = Path(self._config.model_path)
        if not model_path.is_file():
            logger.warning("[LlamaReranker] skipped — model_path missing: {}", model_path)
            return candidates

        runner = self._get_runner(model_path)
        if runner is None:
            logger.warning("[LlamaReranker] skipped — model unavailable")
            return candidates

        head = candidates[: max(1, self._config.max_candidates)]
        tail = candidates[len(head) :]
        logger.info(
            "[LlamaReranker] rerank start — query={!r} candidates={} head={}",
            query,
            len(candidates),
            len(head),
        )
        prompt = build_rerank_prompt(query, head)
        try:
            output = runner(prompt)
            text = extract_text(output)
            parsed = parse_json_array(text)
        except Exception as exc:
            logger.warning("[LlamaReranker] rerank failed, fallback: {}", exc)
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
            logger.warning("[LlamaReranker] no valid scores parsed, fallback")
            return candidates

        hybrid_norm = normalize_values(head, lambda item: item.hybrid_score)
        for candidate in head:
            key = str(candidate.memory_id)
            llama_score_norm = max(0.0, min(1.0, scores.get(key, 0.0) / 100.0))
            candidate.rerank_score = (
                self._config.llama_weight * llama_score_norm
                + (1.0 - self._config.llama_weight) * hybrid_norm[candidate.memory_id]
            )
            if key in reasons:
                candidate.debug["llama_reason"] = reasons[key]
            candidate.debug["llama_score_norm"] = llama_score_norm

        logger.info("[LlamaReranker] rerank done — scored={} total={}", len(scores), len(candidates))
        return sorted(head, key=lambda item: item.final_score, reverse=True) + tail

    def _get_runner(self, model_path: Path):
        if self._model is None:
            try:
                from rpg_world.rpg_core.llama_service import LlamaCompletionModel

                self._model = LlamaCompletionModel(
                    model_path,
                    n_ctx=self._config.n_ctx,
                    n_gpu_layers=self._config.n_gpu_layers,
                    request_timeout_ms=self._config.request_timeout_ms,
                )
            except Exception as exc:
                logger.warning("[LlamaReranker] client init failed, fallback: {}", exc)
                return None

        def run(prompt: str) -> Any:
            return self._model.complete(
                prompt,
                max_tokens=1024,
                temperature=self._config.temperature,
                stop=[],
            )

        return run
