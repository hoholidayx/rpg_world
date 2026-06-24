"""Query planning for memory retrieval."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from loguru import logger

from rpg_core.common_types import JsonObject, JsonValue
from rpg_core.llm.base_provider import LLMProvider
from rp_memory.asyncio_utils import run_awaitable_sync
from rp_memory.planning.plan import QueryPlan, make_empty_plan


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
            keyword_queries=tuple(_dedupe([normalized, _compact(normalized)])),
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
            if not _is_meaningful_term(term):
                continue
            if len(term) == 1 and _is_cjk(term):
                continue
            terms.append(term)
        return _dedupe(terms)[:_MAX_RAW_MD_TERMS]


class LlamaQueryPlanner(BaseQueryPlanner):
    """Query planner backed by a llama.cpp model via ``LLMProvider``."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        fallback_planner: BaseQueryPlanner | None = None,
    ) -> None:
        self._provider = provider
        self._fallback_planner = fallback_planner
        logger.info(
            "[LlamaQueryPlanner] ready: {}",
            provider.get_default_model(),
        )

    def plan(self, query: str) -> QueryPlan:
        normalized = _normalize(query)
        if not normalized:
            return make_empty_plan(query, planner_source="llama")
        prompt = _build_prompt(normalized)
        response = _run_llm_chat_sync(
            self._provider,
            [
                {"role": "system", "content": "You are a memory query planner."},
                {"role": "user", "content": prompt},
            ],
        )
        data = _parse_json_object(response.content)
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
        "字段：keyword_queries、expanded_queries、raw_md_terms、query_type。\n"
        "keyword_queries 用于 keyword FTS，应是短查询短语，不要预分词。\n"
        "raw_md_terms 用于 markdown 字符串召回，应是有意义的中文词或英文术语。\n"
        f"用户查询：{query}"
    )


def _plan_from_mapping(
    original_query: str,
    normalized_query: str,
    data: JsonObject,
    planner_source: str,
    fallback_planner: BaseQueryPlanner | None = None,
) -> QueryPlan:
    keyword_queries = _dedupe(
        [normalized_query, *_as_strings(data.get("keyword_queries")), _compact(normalized_query)]
    )
    expanded_queries = _dedupe(_as_strings(data.get("expanded_queries")))
    raw_md_terms = _filter_meaningful_terms(_dedupe([
        *_as_strings(data.get("raw_md_terms")),
        *(_plan_terms_from_fallback(fallback_planner, normalized_query)),
    ]))
    query_type = str(data.get("query_type") or "general")[:40]
    return QueryPlan(
        original_query=original_query,
        normalized_query=normalized_query,
        keyword_queries=tuple(keyword_queries[:_MAX_QUERY_VARIANTS]),
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
        if not _is_meaningful_term(term):
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


def _filter_meaningful_terms(items: list[str]) -> list[str]:
    return [item for item in items if _is_meaningful_term(item)]


def _as_strings(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list | tuple):
        return []
    return [str(item)[:_MAX_QUERY_CHARS] for item in value if item is not None]


def _is_cjk(text: str) -> bool:
    return all("\u4e00" <= char <= "\u9fff" for char in text)


def _is_meaningful_term(term: str) -> bool:
    if not term or term in _STOPWORDS:
        return False
    return bool(re.search(r"[A-Za-z0-9_\u4e00-\u9fff]", term))


def _run_llm_chat_sync(provider: LLMProvider, messages: list[dict]):
    """Run ``provider.chat()`` synchronously, safe for any event-loop state."""
    return run_awaitable_sync(provider.chat(messages))


def _parse_json_object(text: str) -> JsonObject:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise QueryPlanError("no JSON object found")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise QueryPlanError("planner output is not an object")
    return parsed
