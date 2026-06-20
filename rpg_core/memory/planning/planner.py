"""Query planning for memory retrieval."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

from loguru import logger

from rpg_world.rpg_core.memory.planning.plan import QueryPlan, make_empty_plan


_MAX_QUERY_VARIANTS = 5
_MAX_RAW_MD_TERMS = 12
_MAX_QUERY_CHARS = 80
_STOPWORDS = frozenset(
    {
        "的",
        "了",
        "呢",
        "吗",
        "么",
        "啊",
        "吧",
        "和",
        "与",
        "及",
        "或",
        "在",
        "是",
        "有",
        "这个",
        "那个",
        "怎么",
        "什么",
        "一下",
        "一个",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "is",
    }
)


class QueryPlanError(Exception):
    """Raised when a query planner cannot produce a valid plan."""


class BaseQueryPlanner(ABC):
    @abstractmethod
    def plan(self, query: str) -> QueryPlan:
        """Return a structured query plan."""


class RuleBasedQueryPlanner(BaseQueryPlanner):
    """Deterministic fallback planner based on normalization and jieba terms."""

    def __init__(self, jieba_dict: str | None = None) -> None:
        self._jieba_dict = jieba_dict or None
        self._tokenizer = _get_jieba_tokenizer(self._jieba_dict)

    def plan(self, query: str) -> QueryPlan:
        normalized = _normalize(query)
        if not normalized:
            return make_empty_plan(query)
        raw_md_terms = tuple(self._extract_terms(normalized))
        return QueryPlan(
            original_query=query,
            normalized_query=normalized,
            bigram_queries=tuple(_dedupe([normalized, _compact(normalized)])),
            expanded_queries=(),
            raw_md_terms=raw_md_terms,
            planner_source="rule_based",
        )

    def _extract_terms(self, text: str) -> list[str]:
        try:
            if self._tokenizer is None:
                raise RuntimeError("jieba tokenizer unavailable")
            parts = self._tokenizer.lcut(text)
        except Exception as exc:
            logger.warning("[RuleBasedQueryPlanner] jieba unavailable, regex fallback: {}", exc)
            parts = re.findall(r"[A-Za-z0-9_]+(?:[.\-+][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+", text)
        terms: list[str] = []
        for part in parts:
            term = part.strip()
            if not term or term in _STOPWORDS:
                continue
            if len(term) == 1 and _is_cjk(term):
                continue
            terms.append(term)
        return _dedupe(terms)[:_MAX_RAW_MD_TERMS]


class LlamaQueryPlanner(BaseQueryPlanner):
    """Process-isolated llama.cpp query planner backed by a GGUF model."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        temperature: float = 0.0,
        max_tokens: int = 512,
        request_timeout_ms: int = 60000,
        fallback_planner: BaseQueryPlanner | None = None,
    ) -> None:
        from rpg_world.rpg_core.llama_service import LlamaCompletionModel

        self._model = LlamaCompletionModel(
            model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            request_timeout_ms=request_timeout_ms,
        )
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._fallback_planner = fallback_planner
        logger.info("[LlamaQueryPlanner] process client ready: {} (n_ctx={})", model_path, n_ctx)

    def plan(self, query: str) -> QueryPlan:
        normalized = _normalize(query)
        if not normalized:
            return make_empty_plan(query, planner_source="llama")
        prompt = _build_prompt(normalized)
        output = self._model.complete(
            prompt,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stop=[],
        )
        data = _parse_json_object(_extract_text(output))
        return _plan_from_mapping(
            query,
            normalized,
            data,
            planner_source="llama",
            fallback_planner=self._fallback_planner,
        )


class FallbackQueryPlanner(BaseQueryPlanner):
    """Use a primary planner and fall back to rule-based planning on runtime errors."""

    def __init__(
        self,
        primary: BaseQueryPlanner,
        fallback: RuleBasedQueryPlanner | None = None,
        jieba_dict: str | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or RuleBasedQueryPlanner(jieba_dict=jieba_dict)

    def plan(self, query: str) -> QueryPlan:
        try:
            return self._primary.plan(query)
        except Exception as exc:
            logger.warning("[QueryPlanner] primary planner failed, fallback: {}", exc)
            return self._fallback.plan(query)


def _build_prompt(query: str) -> str:
    return (
        "你是本地记忆检索查询规划器。请把用户查询改写为结构化 JSON。\n"
        "只输出 JSON 对象，不要输出解释。\n"
        "字段：bigram_queries、expanded_queries、raw_md_terms、query_type。\n"
        "bigram_queries 用于 bigram FTS，应是短查询短语，不要预分词。\n"
        "raw_md_terms 用于 markdown 字符串召回，应是有意义的中文词或英文术语。\n"
        f"用户查询：{query}"
    )


def _plan_from_mapping(
    original_query: str,
    normalized_query: str,
    data: dict[str, Any],
    planner_source: str,
    fallback_planner: BaseQueryPlanner | None = None,
) -> QueryPlan:
    bigram_queries = _dedupe(
        [normalized_query, *_as_strings(data.get("bigram_queries")), _compact(normalized_query)]
    )
    expanded_queries = _dedupe(_as_strings(data.get("expanded_queries")))
    raw_md_terms = _dedupe([
        *_as_strings(data.get("raw_md_terms")),
        *(_plan_terms_from_fallback(fallback_planner, normalized_query)),
    ])
    query_type = str(data.get("query_type") or "general")[:40]
    return QueryPlan(
        original_query=original_query,
        normalized_query=normalized_query,
        bigram_queries=tuple(bigram_queries[:_MAX_QUERY_VARIANTS]),
        expanded_queries=tuple(expanded_queries[:_MAX_QUERY_VARIANTS]),
        raw_md_terms=tuple(raw_md_terms[:_MAX_RAW_MD_TERMS]),
        query_type=query_type,
        planner_source=planner_source,
    )




def _plan_terms_from_fallback(fallback_planner: BaseQueryPlanner | None, query: str) -> list[str]:
    if fallback_planner is not None:
        try:
            plan = fallback_planner.plan(query)
            return list(plan.raw_md_terms)
        except Exception as exc:
            logger.warning("[QueryPlanner] fallback planner failed while extracting terms: {}", exc)
    return _extract_terms(query)


def _extract_terms(text: str) -> list[str]:
    tokenizer = _get_jieba_tokenizer(None)
    try:
        if tokenizer is None:
            raise RuntimeError("jieba tokenizer unavailable")
        parts = tokenizer.lcut(text)
    except Exception as exc:
        logger.warning("[RuleBasedQueryPlanner] jieba unavailable, regex fallback: {}", exc)
        parts = re.findall(r"[A-Za-z0-9_]+(?:[.\-+][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+", text)
    terms: list[str] = []
    for part in parts:
        term = part.strip()
        if not term or term in _STOPWORDS:
            continue
        if len(term) == 1 and _is_cjk(term):
            continue
        terms.append(term)
    return _dedupe(terms)[:_MAX_RAW_MD_TERMS]


@lru_cache(maxsize=8)
def _get_jieba_tokenizer(dictionary_path: str | None):
    try:
        import jieba

        if dictionary_path:
            tokenizer = jieba.Tokenizer(dictionary=dictionary_path)
        else:
            tokenizer = jieba.Tokenizer()
        return tokenizer
    except Exception as exc:
        logger.warning("[RuleBasedQueryPlanner] jieba tokenizer init failed, regex fallback: {}", exc)
        return None


def _normalize(text: str) -> str:
    return " ".join((text or "").split())[:_MAX_QUERY_CHARS]


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = _normalize(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _as_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list | tuple):
        return []
    return [str(item)[:_MAX_QUERY_CHARS] for item in value if item is not None]


def _is_cjk(text: str) -> bool:
    return all("\u4e00" <= char <= "\u9fff" for char in text)


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


def _parse_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise QueryPlanError("no JSON object found")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise QueryPlanError("planner output is not an object")
    return parsed
