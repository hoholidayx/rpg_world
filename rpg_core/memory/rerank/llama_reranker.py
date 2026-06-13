"""Local llama.cpp reranker for hybrid memory retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.retrieval.scoring import normalize_values


@dataclass
class LlamaRerankConfig:
    enabled: bool = False
    model_path: str = ""
    max_candidates: int = 10
    n_ctx: int = 4096
    temperature: float = 0.0


class LlamaReranker:
    """Rerank candidates with a local llama-cpp-python model."""

    def __init__(self, config: LlamaRerankConfig) -> None:
        self._config = config
        self._llama: Any | None = None
        self._load_attempted = False

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

        llama = self._get_llama(model_path)
        if llama is None:
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
        prompt = _build_prompt(query, head)
        try:
            output = llama(
                prompt,
                max_tokens=1024,
                temperature=self._config.temperature,
                stop=[],
            )
            text = _extract_text(output)
            parsed = _parse_json_array(text)
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
                0.7 * llama_score_norm
                + 0.3 * hybrid_norm[candidate.memory_id]
            )
            if key in reasons:
                candidate.debug["llama_reason"] = reasons[key]
            candidate.debug["llama_score_norm"] = llama_score_norm

        logger.info("[LlamaReranker] rerank done — scored={} total={}", len(scores), len(candidates))
        return sorted(head, key=lambda item: item.final_score, reverse=True) + tail

    def _get_llama(self, model_path: Path) -> Any | None:
        if self._llama is not None:
            return self._llama
        if self._load_attempted:
            return None
        self._load_attempted = True
        try:
            from llama_cpp import Llama

            logger.info("[LlamaReranker] loading model: {} (n_ctx={})", model_path, self._config.n_ctx)
            self._llama = Llama(
                model_path=str(model_path),
                n_ctx=self._config.n_ctx,
                verbose=False,
            )
            logger.info("[LlamaReranker] model loaded")
            return self._llama
        except Exception as exc:
            logger.warning("[LlamaReranker] load failed, fallback: {}", exc)
            return None


def _build_prompt(query: str, candidates: list[MemoryCandidate]) -> str:
    payload = [
        {"id": str(candidate.memory_id), "content": candidate.content}
        for candidate in candidates
    ]
    return (
        "你是一个本地记忆检索重排器。给定用户查询和候选记忆，请判断每条候选记忆是否能帮助回答查询。\n"
        "只根据候选内容本身打分，不要编造。\n"
        "评分：\n"
        "0 = 完全无关\n"
        "30 = 弱相关\n"
        "60 = 有一定相关\n"
        "80 = 强相关\n"
        "100 = 精确命中\n"
        "请只输出 JSON 数组，不要输出其他文字。\n\n"
        f"用户查询：\n{query}\n\n"
        "候选记忆：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _extract_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        choices = output.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                return str(first.get("text") or first.get("message", {}).get("content") or "")
    return str(output)


def _parse_json_array(text: str) -> list[Any]:
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON array found")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("rerank output is not an array")
    return parsed
