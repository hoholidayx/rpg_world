"""Assembled memory retriever combining sqlvec, keyword, and raw markdown search."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.plan import QueryPlan
from rp_memory.planning.planner import BaseQueryPlanner, RuleBasedQueryPlanner
from rp_memory.rerank.base import MemoryReranker
from rp_memory.retrieval.keyword_retriever import KeywordRetriever
from rp_memory.retrieval.raw_md_retriever import RawMarkdownRetriever
from rp_memory.retrieval.retriever import BaseRetriever
from rp_memory.retrieval.priority import granularity_score
from rp_memory.retrieval.scoring import apply_hybrid_scores, exact_and_fuzzy_scores
from rp_memory.retrieval.sqlvec_retriever import SqlVecRetriever

if TYPE_CHECKING:
    from loguru import Logger


class HybridRetriever(BaseRetriever):
    """Assembled retriever that merges sqlvec, keyword, and raw markdown results."""

    def __init__(
        self,
        sqlvec_retriever: SqlVecRetriever | None = None,
        keyword_retriever: KeywordRetriever | None = None,
        raw_md_retriever: RawMarkdownRetriever | None = None,
        query_planner: BaseQueryPlanner | None = None,
        reranker: MemoryReranker | None = None,
        hybrid_vector_weight: float = 0.60,
        hybrid_keyword_weight: float = 0.25,
        hybrid_raw_md_weight: float = 0.05,
        hybrid_exact_weight: float = 0.10,
        hybrid_expanded_weight: float = 0.10,
        hybrid_recency_weight: float = 0.05,
        hybrid_granularity_weight: float = 0.05,
        raw_md_mode: str = "fallback_only",
        raw_md_min_results: int = 0,
        keyword_tokenizer: str = "jieba",
        rerank_candidate_k: int = 8,
    ) -> None:
        self._sqlvec_retriever = sqlvec_retriever
        self._keyword_retriever = keyword_retriever
        self._raw_md_retriever = raw_md_retriever
        self._query_planner = query_planner or RuleBasedQueryPlanner()
        self._reranker = reranker
        self._hybrid_vector_weight = hybrid_vector_weight
        self._hybrid_keyword_weight = hybrid_keyword_weight
        self._hybrid_raw_md_weight = hybrid_raw_md_weight
        self._hybrid_exact_weight = hybrid_exact_weight
        self._hybrid_expanded_weight = hybrid_expanded_weight
        self._hybrid_recency_weight = hybrid_recency_weight
        self._hybrid_granularity_weight = hybrid_granularity_weight
        self._raw_md_mode = _normalize_raw_md_mode(raw_md_mode)
        self._raw_md_min_results = max(0, int(raw_md_min_results or 0))
        self._keyword_tokenizer = keyword_tokenizer
        self._rerank_candidate_k = max(1, int(rerank_candidate_k))

    def _plan_query(self, query: str) -> QueryPlan:
        return self._query_planner.plan(query)

    async def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        return await asyncio.to_thread(self.retrieve_sync, query, top_k)

    def retrieve_sync(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        try:
            plan = self._plan_query(query)
        except Exception as exc:
            self._log_stage_error("plan", exc)
            return []
        return self._format(self._search_plan_candidates(plan, top_k))

    def retrieve_plan_sync(self, plan: QueryPlan, top_k: int = 5) -> list[tuple[str, float, dict]]:
        try:
            return self._format(self._search_plan_candidates(plan, top_k))
        except Exception as exc:
            self._log_stage_error("retrieve_plan", exc)
            return []

    def hybrid_search(self, query: str | QueryPlan, top_k: int = 20) -> list[MemoryCandidate]:
        try:
            plan = query if isinstance(query, QueryPlan) else self._plan_query(query)
        except Exception as exc:
            self._log_stage_error("plan", exc)
            return []
        from loguru import logger

        logger.info(
            "[HybridRetriever] search start — query={!r} planner={} top_k={} sqlvec={} keyword={} raw_md={} raw_md_mode={} keyword_tokenizer={}",
            plan.normalized_query,
            plan.planner_source,
            top_k,
            self._sqlvec_retriever is not None,
            self._keyword_retriever is not None,
            self._raw_md_retriever is not None,
            self._raw_md_mode,
            self._keyword_tokenizer,
        )
        return self._search_plan_candidates(plan, top_k)

    def _search_plan_candidates(self, plan: QueryPlan, top_k: int) -> list[MemoryCandidate]:
        retrieval_limit = self._retrieval_limit(top_k)
        failures: list[str] = []
        if self._sqlvec_retriever is not None:
            try:
                sqlvec_candidates = self._sqlvec_retriever.search_plan(plan, top_k=retrieval_limit)
            except Exception as exc:
                self._log_stage_error("sqlvec search", exc)
                failures.append("sqlvec_failed")
                sqlvec_candidates = []
        else:
            sqlvec_candidates = []

        keyword_candidates, keyword_failed = self._safe_keyword_candidates(plan, retrieval_limit)
        if keyword_failed:
            failures.append("keyword_failed")
        raw_md_candidates: list[MemoryCandidate] = []
        raw_md_reason = "disabled"
        raw_md_triggered = False
        if self._raw_md_retriever is None:
            if self._raw_md_mode != "disabled":
                raw_md_reason = "store_unavailable"
        elif self._raw_md_mode == "always":
            raw_md_triggered = True
            raw_md_candidates = self._safe_raw_md_candidates(plan, retrieval_limit)
            raw_md_reason = "always"
        elif self._raw_md_mode == "fallback_only":
            threshold = self._raw_md_min_results if self._raw_md_min_results > 0 else retrieval_limit
            main_count = _candidate_count(sqlvec_candidates, keyword_candidates)
            if failures:
                raw_md_triggered = True
                raw_md_reason = failures[0]
                raw_md_candidates = self._safe_raw_md_candidates(plan, retrieval_limit)
            elif main_count < threshold:
                raw_md_triggered = True
                raw_md_reason = "insufficient_candidates"
                raw_md_candidates = self._safe_raw_md_candidates(plan, retrieval_limit)
            else:
                raw_md_reason = "disabled"

        merged: dict[int, MemoryCandidate] = {}
        for candidate in sqlvec_candidates:
            merged[candidate.memory_id] = candidate
        for candidate in keyword_candidates:
            self._merge_candidate(merged, candidate, "keyword")
        before_raw_merge = len(merged)
        for candidate in raw_md_candidates:
            self._merge_candidate(merged, candidate, "raw_md")
        after_raw_merge = len(merged)

        candidates = list(merged.values())
        from loguru import logger

        logger.info(
            "[HybridRetriever] candidate merge done — sqlvec={} keyword={} raw_md={} merged={} planner={} expanded_queries={} keyword_tokenizer={} raw_md_mode={} raw_md_triggered={} raw_md_reason={} raw_md_before={} raw_md_after={}",
            len(sqlvec_candidates),
            len(keyword_candidates),
            len(raw_md_candidates),
            len(candidates),
            plan.planner_source,
            list(plan.expanded_queries),
            self._keyword_tokenizer,
            self._raw_md_mode,
            raw_md_triggered,
            raw_md_reason,
            before_raw_merge,
            after_raw_merge,
        )
        for candidate in candidates:
            logger.info(
                "[HybridRetriever] merged candidate — id={} source={} vector={:.4f} keyword={:.4f} raw_md={:.4f} exact={:.4f} fuzzy={:.4f} debug={}",
                candidate.memory_id,
                candidate.metadata.get("source", ""),
                candidate.vector_score,
                candidate.keyword_score,
                candidate.raw_md_score,
                candidate.exact_score,
                candidate.fuzzy_score,
                candidate.debug,
            )
        return self._finalize(plan, candidates, top_k)

    def _safe_keyword_candidates(self, plan: QueryPlan, top_k: int) -> tuple[list[MemoryCandidate], bool]:
        if self._keyword_retriever is None:
            return [], False
        try:
            return self._keyword_retriever.search_plan(plan, top_k=top_k), False
        except Exception as exc:
            self._log_stage_error("keyword search", exc)
            return [], True

    def _safe_raw_md_candidates(self, plan: QueryPlan, top_k: int) -> list[MemoryCandidate]:
        if self._raw_md_retriever is None:
            return []
        try:
            return self._raw_md_retriever.search_plan(plan, top_k=top_k)
        except Exception as exc:
            self._log_stage_error("raw markdown search", exc)
            return []

    def _retrieval_limit(self, top_k: int) -> int:
        if self._reranker is None:
            return max(top_k, 1)
        return max(top_k, self._rerank_candidate_k, 1)

    def _merge_candidate(self, merged: dict[int, MemoryCandidate], candidate: MemoryCandidate, source_name: str) -> None:
        existing = merged.get(candidate.memory_id)
        if existing is None:
            merged[candidate.memory_id] = candidate
            return
        existing.vector_score = max(existing.vector_score, candidate.vector_score)
        existing.keyword_score = max(existing.keyword_score, candidate.keyword_score)
        existing.raw_md_score = max(existing.raw_md_score, candidate.raw_md_score)
        existing.exact_score = max(existing.exact_score, candidate.exact_score)
        existing.fuzzy_score = max(existing.fuzzy_score, candidate.fuzzy_score)
        existing.expanded_score = max(existing.expanded_score, candidate.expanded_score)
        existing.hybrid_score = max(existing.hybrid_score, candidate.hybrid_score)
        existing.debug.update(candidate.debug)
        existing.debug.setdefault("sources", []).append(source_name)

    def _finalize(
        self,
        plan: QueryPlan,
        candidates: list[MemoryCandidate],
        top_k: int,
    ) -> list[MemoryCandidate]:
        now = time.time()
        query = plan.normalized_query or plan.original_query
        for candidate in candidates:
            exact, fuzzy = exact_and_fuzzy_scores(query, candidate.content)
            candidate.exact_score = exact
            candidate.fuzzy_score = fuzzy
            expanded_score, expanded_query = _expanded_match_score(
                plan.expanded_queries,
                candidate.content,
                _candidate_expanded_terms(candidate),
            )
            candidate.expanded_score = max(candidate.expanded_score, expanded_score)
            if expanded_query:
                candidate.debug["expanded_match_query"] = expanded_query
            created_at = _as_float(candidate.metadata.get("created_at"))
            candidate.recency_score = 1.0 / (1.0 + max(0.0, (now - created_at) / 86400.0)) if created_at else 0.0
            granularity, score = granularity_score(candidate.metadata)
            candidate.granularity_score = score
            candidate.debug["memory_granularity"] = granularity

        from loguru import logger

        logger.info(
            "[HybridRetriever] hybrid scoring — weights vector={:.3f} keyword={:.3f} raw_md={:.3f} exact={:.3f} expanded={:.3f} recency={:.3f} granularity={:.3f}",
            self._hybrid_vector_weight,
            self._hybrid_keyword_weight,
            self._hybrid_raw_md_weight,
            self._hybrid_exact_weight,
            self._hybrid_expanded_weight,
            self._hybrid_recency_weight,
            self._hybrid_granularity_weight,
        )
        apply_hybrid_scores(
            candidates,
            vector_weight=self._hybrid_vector_weight,
            keyword_weight=self._hybrid_keyword_weight,
            raw_md_weight=self._hybrid_raw_md_weight,
            exact_weight=self._hybrid_exact_weight,
            expanded_weight=self._hybrid_expanded_weight,
            recency_weight=self._hybrid_recency_weight,
            granularity_weight=self._hybrid_granularity_weight,
        )
        candidates = sorted(candidates, key=lambda item: item.hybrid_score, reverse=True)
        for rank, candidate in enumerate(candidates, start=1):
            logger.info(
                "[HybridRetriever] hybrid candidate — rank={} id={} hybrid={:.4f} vector={:.4f} keyword={:.4f} raw_md={:.4f} exact={:.4f} fuzzy={:.4f} expanded={:.4f} recency={:.4f} granularity={:.4f} file={}",
                rank,
                candidate.memory_id,
                candidate.hybrid_score,
                candidate.vector_score,
                candidate.keyword_score,
                candidate.raw_md_score,
                candidate.exact_score,
                candidate.fuzzy_score,
                candidate.expanded_score,
                candidate.recency_score,
                candidate.granularity_score,
                candidate.metadata.get("file", ""),
            )
        selected_count = max(top_k, self._rerank_candidate_k, 1) if self._reranker is not None else max(top_k, 1)
        logger.info(
            "[HybridRetriever] rerank pool — top_k={} rerank_candidate_k={} selected={} total={}",
            top_k,
            self._rerank_candidate_k,
            min(selected_count, len(candidates)),
            len(candidates),
        )
        candidates = candidates[:selected_count]
        if not candidates:
            logger.info("[HybridRetriever] rerank skipped — no candidates")
            return candidates
        if self._reranker is not None:
            rerank_query = _build_rerank_query(plan)
            logger.info(
                "[HybridRetriever] rerank start — candidates={} query={!r} expanded_queries={}",
                len(candidates),
                rerank_query,
                list(plan.expanded_queries),
            )
            try:
                candidates = self._reranker.rerank(rerank_query, candidates)
            except Exception as exc:
                self._log_stage_error("rerank", exc)
            else:
                logger.info("[HybridRetriever] rerank done — candidates={}", len(candidates))
                for rank, candidate in enumerate(candidates, start=1):
                    logger.info(
                        "[HybridRetriever] rerank candidate — rank={} id={} final={:.4f} rerank={:.4f} hybrid={:.4f} debug={}",
                        rank,
                        candidate.memory_id,
                        candidate.final_score,
                        candidate.rerank_score,
                        candidate.hybrid_score,
                        candidate.debug,
                    )
        else:
            logger.info("[HybridRetriever] rerank skipped — disabled or unavailable")
        return candidates[:top_k]

    def _format(self, candidates: list[MemoryCandidate]) -> list[tuple[str, float, dict]]:
        result: list[tuple[str, float, dict]] = []
        for candidate in candidates:
            metadata = dict(candidate.metadata)
            metadata.update(
                {
                    "memory_id": candidate.memory_id,
                    "vector_score": candidate.vector_score,
                    "keyword_score": candidate.keyword_score,
                    "raw_md_score": candidate.raw_md_score,
                    "exact_score": candidate.exact_score,
                    "fuzzy_score": candidate.fuzzy_score,
                    "expanded_score": candidate.expanded_score,
                    "granularity_score": candidate.granularity_score,
                    "recency_score": candidate.recency_score,
                    "hybrid_score": candidate.hybrid_score,
                    "rerank_score": candidate.rerank_score,
                    "debug": candidate.debug,
                }
            )
            result.append((candidate.content, candidate.final_score, metadata))
        return result

    def _log_stage_error(self, stage: str, exc: Exception) -> None:
        from loguru import logger

        logger.warning("[HybridRetriever] {} failed: {}", stage, exc)


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _candidate_count(*groups: list[MemoryCandidate]) -> int:
    return len({candidate.memory_id for group in groups for candidate in group})


def _normalize_raw_md_mode(mode: str) -> str:
    value = (mode or "fallback_only").strip().lower()
    if value in {"fallback_only", "always", "disabled"}:
        return value
    from loguru import logger

    logger.warning("[HybridRetriever] unknown raw_md_mode={!r}, fallback to fallback_only", mode)
    return "fallback_only"


def _expanded_match_score(
    expanded_queries: tuple[str, ...],
    content: str,
    expanded_terms: list[str] | None = None,
) -> tuple[float, str]:
    best_score = 0.0
    best_query = ""
    compact_content = _compact(content)
    for expanded_query in expanded_queries:
        normalized = " ".join((expanded_query or "").split())
        if not normalized:
            continue
        compact_query = _compact(normalized)
        score = 1.0 if normalized in content or (compact_query and compact_query in compact_content) else 0.0
        if score > best_score:
            best_score = score
            best_query = expanded_query
    meaningful_terms = [term for term in (expanded_terms or []) if term]
    if meaningful_terms:
        matched = sum(1 for term in meaningful_terms if term in content or _compact(term) in compact_content)
        score = matched / len(meaningful_terms)
        if score > best_score:
            best_score = score
            best_query = "expanded_terms"
    return best_score, best_query


def _candidate_expanded_terms(candidate: MemoryCandidate) -> list[str]:
    value = candidate.metadata.get("raw_md_expanded_terms") or candidate.debug.get("raw_md_expanded_terms")
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _compact(text: str) -> str:
    return "".join((text or "").split())


def _build_rerank_query(plan: QueryPlan) -> str:
    query = plan.normalized_query or plan.original_query
    expanded = [item for item in plan.expanded_queries if item and item != query]
    if not expanded:
        return query
    return f"{query}\n扩展查询：{' | '.join(expanded)}"
