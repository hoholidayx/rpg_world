"""Raw markdown grep fallback for memory retrieval.

This is the raw markdown retrieval stage when vector and keyword search
produce no useful candidates or fail independently.
It scans the raw markdown files under the watched memory source paths
instead of depending on the SQLite database.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.plan import QueryPlan
from rp_memory.planning.planner import BaseQueryPlanner, RuleBasedQueryPlanner


@dataclass
class RawMarkdownGrepSearch:
    """Final fallback searcher based on raw markdown file scanning."""

    source_paths: list[Path]
    limit: int = 50
    rule_based_planner: BaseQueryPlanner | None = None
    jieba_dict: str | None = None

    def search(self, query: str, limit: int | None = None) -> list[MemoryCandidate]:
        """Return candidates matched by scanning raw markdown files.

        The search is intentionally tolerant: all failures are swallowed and
        converted to an empty result so that this stage never breaks the
        hybrid pipeline.
        """
        try:
            logger.info(
                "[RawMarkdownGrepSearch] search start — query={!r} roots={} limit={}",
                query,
                len(self.source_paths),
                limit or self.limit,
            )
            plan = self._plan_query(query)
            return self._search_plan(plan, limit=limit or self.limit)
        except Exception as exc:
            logger.warning("[RawMarkdownGrepSearch] fallback search failed: {}", exc)
            return []

    def search_plan(self, plan: QueryPlan, limit: int | None = None) -> list[MemoryCandidate]:
        """Return candidates matched by a structured query plan."""
        try:
            logger.info(
                "[RawMarkdownGrepSearch] search_plan start — query={!r} terms={} expanded_queries={} roots={} limit={}",
                plan.normalized_query,
                len(plan.raw_md_terms),
                len(plan.expanded_queries),
                len(self.source_paths),
                limit or self.limit,
            )
            return self._search_plan(plan, limit=limit or self.limit)
        except Exception as exc:
            logger.warning("[RawMarkdownGrepSearch] fallback search_plan failed: {}", exc)
            return []

    def _plan_query(self, query: str) -> QueryPlan:
        planner = self._fallback_planner()
        plan_sync = getattr(planner, "plan_sync", None)
        if plan_sync is None:
            raise TypeError("raw markdown fallback requires a synchronous rule planner")
        return plan_sync(query)

    def _search_plan(self, plan: QueryPlan, limit: int) -> list[MemoryCandidate]:
        normalized = plan.normalized_query
        if not normalized:
            return []

        terms = list(plan.raw_md_terms)
        expanded_queries = list(plan.expanded_queries)
        expanded_terms = self._expanded_terms(expanded_queries)
        logger.info(
            "[RawMarkdownGrepSearch] expanded terms — queries={} terms={}",
            expanded_queries,
            expanded_terms,
        )
        candidates: list[MemoryCandidate] = []
        for file_path in self._iter_md_files():
            try:
                raw_text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            exact_score = 1.0 if normalized in raw_text or _compact(normalized) in _compact(raw_text) else 0.0
            raw_md_score = _score_raw_md(normalized, raw_text, terms)
            expanded_score = _score_expanded(raw_text, expanded_queries, expanded_terms)
            match_score = max(exact_score, raw_md_score, expanded_score)
            if match_score <= 0.0:
                continue

            metadata = {
                "source": file_path.parent.name or file_path.stem,
                "file": str(file_path),
                "chunk_idx": 0,
                "created_at": float(file_path.stat().st_mtime),
                "raw_md_terms": terms,
                "raw_md_expanded_queries": expanded_queries,
                "raw_md_expanded_terms": expanded_terms,
            }
            metadata.update(_frontmatter_metadata(raw_text))
            candidates.append(
                MemoryCandidate(
                    memory_id=_stable_memory_id(file_path),
                    content=raw_text,
                    metadata=metadata,
                    raw_md_score=raw_md_score,
                    exact_score=exact_score,
                    expanded_score=expanded_score,
                    debug={
                        "raw_md_source": str(file_path),
                        "raw_md_terms": terms,
                        "raw_md_expanded_queries": expanded_queries,
                        "raw_md_expanded_terms": expanded_terms,
                        "raw_md_expanded_score": expanded_score,
                        "raw_md_match_score": match_score,
                        "raw_md_score": raw_md_score,
                    },
                )
            )

        candidates.sort(
            key=lambda item: (
                item.exact_score,
                item.raw_md_score,
                item.expanded_score,
                float(item.metadata.get("created_at") or 0.0),
            ),
            reverse=True,
        )
        logger.info("[RawMarkdownGrepSearch] search done — matched={}", len(candidates))
        return candidates[:limit]

    def _expanded_terms(self, expanded_queries: list[str]) -> list[str]:
        if not expanded_queries:
            return []
        planner = self._fallback_planner()
        terms: list[str] = []
        try:
            for query in expanded_queries:
                if not query:
                    continue
                plan_sync = getattr(planner, "plan_sync", None)
                if plan_sync is None:
                    continue
                terms.extend(plan_sync(query).raw_md_terms)
        except Exception as exc:
            logger.warning("[RawMarkdownGrepSearch] expanded query tokenization failed — exact-only fallback: {}", exc)
            return []
        return _dedupe(terms)

    def _fallback_planner(self) -> BaseQueryPlanner:
        return self.rule_based_planner or RuleBasedQueryPlanner(jieba_dict=self.jieba_dict or None)

    def _iter_md_files(self) -> list[Path]:
        files: list[Path] = []
        seen: set[Path] = set()
        for root in self.source_paths:
            if not root.exists():
                continue
            if root.is_file():
                if root.suffix.lower() == ".md":
                    resolved = root.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        files.append(resolved)
                continue
            for file_path in sorted(root.rglob("*.md")):
                if not file_path.is_file():
                    continue
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(resolved)
        return files


def _stable_memory_id(file_path: Path) -> int:
    uid = hashlib.sha256(f"{file_path}:0".encode()).hexdigest()[:16]
    return int(uid, 16) % (2**63)


def _score_raw_md(
    query: str,
    text: str,
    terms: list[str] | None = None,
) -> float:
    if not query or not text:
        return 0.0
    if query in text:
        return 1.0

    compact_text = _compact(text)
    compact_query = _compact(query)
    if compact_query and compact_query in compact_text:
        return 1.0

    meaningful_terms = [term for term in (terms or []) if term]
    if meaningful_terms:
        matched = sum(
            1
            for term in meaningful_terms
            if term in text or _compact(term) in compact_text
        )
        return matched / len(meaningful_terms)
    return 0.0


def _score_expanded(text: str, expanded_queries: list[str], expanded_terms: list[str] | None = None) -> float:
    if not text or not expanded_queries:
        return 0.0
    compact_text = _compact(text)
    for expanded in expanded_queries:
        normalized = " ".join(expanded.split())
        if not normalized:
            continue
        compact_expanded = _compact(normalized)
        if normalized in text or compact_expanded in compact_text:
            return 1.0
    meaningful_terms = [term for term in (expanded_terms or []) if term]
    if not meaningful_terms:
        return 0.0
    matched = sum(
        1
        for term in meaningful_terms
        if term in text or _compact(term) in compact_text
    )
    return matched / len(meaningful_terms)


def _frontmatter_metadata(text: str) -> dict[str, object]:
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    metadata: dict[str, object] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            continue
        metadata[key] = _parse_frontmatter_value(value.strip())
    return metadata


def _parse_frontmatter_value(value: str) -> object:
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = " ".join((item or "").split())
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
