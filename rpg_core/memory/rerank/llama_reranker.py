"""Local llama.cpp reranker for hybrid memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import time

from loguru import logger

from rpg_world.rpg_core.memory.rerank.common import extract_text
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
    verbose: bool = False
    """透传给 llama.cpp 的 verbose 开关（打印 GPU 层加载、KV cache 等信息）。"""


class RerankParseError(Exception):
    def __init__(self, message: str, preview: str = "") -> None:
        super().__init__(message)
        self.preview = preview


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

        logger.info(
            "[LlamaReranker] rerank start — query={!r} candidates={}",
            query,
            len(candidates),
        )
        started_at = time.monotonic()
        scored: list[MemoryCandidate] = []
        for candidate in candidates:
            try:
                score, reason, elapsed_ms, raw_text = self._score_candidate(runner, query, candidate)
            except Exception as exc:
                preview = getattr(exc, "preview", "")
                logger.warning(
                    "[LlamaReranker] pointwise score failed — candidate={} fallback={} preview={!r}",
                    candidate.memory_id,
                    exc,
                    preview,
                )
                return candidates

            candidate.rerank_score = max(0.0, min(1.0, score / 100.0))
            candidate.debug["llama_score_norm"] = candidate.rerank_score
            if reason:
                candidate.debug["llama_reason"] = reason
            scored.append(candidate)
            logger.info(
                "[LlamaReranker] candidate scored — id={} score={:.0f} elapsed_ms={:.0f}",
                candidate.memory_id,
                score,
                elapsed_ms,
            )

        total_ms = (time.monotonic() - started_at) * 1000.0
        logger.info("[LlamaReranker] pointwise rerank done — total_ms={:.0f} scored={}", total_ms, len(scored))
        hybrid_norm = normalize_values(scored, lambda item: item.hybrid_score)
        for candidate in scored:
            candidate.rerank_score = (
                self._config.llama_weight * candidate.rerank_score
                + (1.0 - self._config.llama_weight) * hybrid_norm[candidate.memory_id]
            )
        return sorted(scored, key=lambda item: item.final_score, reverse=True)

    def _score_candidate(self, runner, query: str, candidate: MemoryCandidate) -> tuple[float, str, float, str]:
        prompt = _build_pointwise_prompt(query, candidate)
        started_at = time.monotonic()
        output = runner(prompt)
        elapsed_ms = (time.monotonic() - started_at) * 1000.0
        raw_text = extract_text(output)
        try:
            score, reason = _parse_pointwise_output(raw_text)
        except Exception as exc:
            raise RerankParseError(str(exc), preview=_short_preview(raw_text)) from exc
        return score, reason, elapsed_ms, raw_text

    def _get_runner(self, model_path: Path):
        if self._model is None:
            try:
                from rpg_world.rpg_core.llama_service import LlamaCompletionModel

                logger.info(
                    "[LlamaReranker] loading model: {} (n_ctx={}, n_gpu_layers={}, verbose={})",
                    model_path,
                    self._config.n_ctx,
                    self._config.n_gpu_layers,
                    self._config.verbose,
                )
                self._model = LlamaCompletionModel(
                    model_path,
                    n_ctx=self._config.n_ctx,
                    n_gpu_layers=self._config.n_gpu_layers,
                    verbose=self._config.verbose,
                    request_timeout_ms=self._config.request_timeout_ms,
                )
                logger.info("[LlamaReranker] model loaded successfully")
            except Exception as exc:
                logger.warning("[LlamaReranker] client init failed, fallback: {}", exc)
                return None

        def run(prompt: str) -> Any:
            return self._model.complete(
                prompt,
                max_tokens=128,
                temperature=self._config.temperature,
                stop=[],
            )

        return run

def _build_pointwise_prompt(query: str, candidate: MemoryCandidate) -> str:
    return (
        "你是一个本地记忆重排器。\n"
        "请只根据查询和单条候选记忆判断相关性。\n"
        "只输出一行，格式严格为：<0-100整数分数>\t<简短原因>\n"
        "不要输出JSON，不要代码块，不要解释。\n\n"
        f"用户查询：{query}\n\n"
        f"候选记忆：{candidate.content}"
    )


def _parse_pointwise_output(text: str) -> tuple[float, str]:
    cleaned = _short_preview(text, limit=4000)
    if not cleaned:
        raise ValueError("empty rerank output")
    first_line = cleaned.splitlines()[0].strip()
    if not first_line:
        raise ValueError("empty rerank output")
    parts = first_line.split("\t")
    if len(parts) == 1:
        parts = [part.strip() for part in first_line.split("|") if part.strip()]
    if len(parts) == 1:
        parts = [part.strip() for part in first_line.split(",") if part.strip()]
    score_text = parts[0]
    reason = parts[1] if len(parts) >= 2 else ""
    try:
        score = float(score_text)
    except Exception:
        import re

        match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", first_line)
        if not match:
            raise ValueError(f"no numeric score found: {first_line!r}")
        score = float(match.group(1))
        if len(parts) >= 2:
            reason = parts[-1]
    return score, reason


def _short_preview(text: str, limit: int = 800) -> str:
    return " ".join((text or "").split())[:limit]


