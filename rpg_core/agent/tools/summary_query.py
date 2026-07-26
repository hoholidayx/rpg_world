"""Session-scoped read-only queries over rendered Summary documents."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from rpg_core.agent.tools.history_query import (
    HISTORY_SEARCH_DEFAULT_LIMIT,
    HISTORY_SEARCH_MAX_LIMIT,
    HISTORY_SEARCH_MAX_TERM_CHARS,
    HISTORY_SEARCH_MAX_TERMS,
)
from rpg_data.model.session_reference import SessionReferenceLocator

if TYPE_CHECKING:
    from rpg_core.summary.reference import ResolvedSummaryDocument
    from rpg_data.model.session import Session

_TAG = "[SummaryQueryService]"

SUMMARY_SEARCH_DEFAULT_LIMIT = HISTORY_SEARCH_DEFAULT_LIMIT
SUMMARY_SEARCH_MAX_LIMIT = HISTORY_SEARCH_MAX_LIMIT
SUMMARY_SEARCH_MAX_TERMS = HISTORY_SEARCH_MAX_TERMS
SUMMARY_SEARCH_MAX_TERM_CHARS = HISTORY_SEARCH_MAX_TERM_CHARS
SUMMARY_SEARCH_EXCERPT_CHARS = 280
SUMMARY_READ_CONTENT_BUDGET = 20_000

_ASCII_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_LOWER = "abcdefghijklmnopqrstuvwxyz"
_ASCII_LOWER_TRANSLATION = str.maketrans(_ASCII_UPPER, _ASCII_LOWER)
_BATCH_SUMMARY_ID_RE = re.compile(r"^[0-9]+$")
_SEARCH_FIELD_ORDER = ("title", "time", "location", "characters", "text")
_METADATA_FIELDS = frozenset({"title", "time", "location", "characters"})


class SummaryQuerySessionDataPort(Protocol):
    """Narrow Session identity lookup used to build an owned locator."""

    def get_session(self, session_id: str) -> "Session | None": ...


class SummaryReferenceProviderPort(Protocol):
    """Synchronous Summary snapshot provider executed inside a worker."""

    def list_summaries(
        self,
        locator: SessionReferenceLocator,
    ) -> tuple["ResolvedSummaryDocument", ...]: ...

    def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> "ResolvedSummaryDocument | None": ...


class SummaryQueryService:
    """Validate and execute bounded Summary search/read requests."""

    def __init__(
        self,
        *,
        session_id: Callable[[], str],
        session_data: SummaryQuerySessionDataPort,
        summaries: SummaryReferenceProviderPort,
        close_worker_connection: Callable[[], None],
    ) -> None:
        self._session_id = session_id
        self._session_data = session_data
        self._summaries = summaries
        self._close_worker_connection = close_worker_connection

    async def search(
        self,
        *,
        terms: object,
        limit: object = SUMMARY_SEARCH_DEFAULT_LIMIT,
    ) -> dict[str, object]:
        """Search Summary headers and bodies using literal OR terms."""

        try:
            normalized_terms = _normalize_terms(terms)
            normalized_limit = _bounded_int(
                limit,
                name="limit",
                minimum=1,
                maximum=SUMMARY_SEARCH_MAX_LIMIT,
            )
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))

        session_id = "<unavailable>"
        try:
            session_id = str(self._session_id())
            documents = await asyncio.to_thread(
                self._list_worker,
                session_id,
            )
            matches = _search_documents(documents, normalized_terms)
            has_more = len(matches) > normalized_limit
            return {
                "ok": True,
                "terms": list(normalized_terms),
                "items": [
                    _search_item(match)
                    for match in matches[:normalized_limit]
                ],
                "hasMore": has_more,
            }
        except Exception as exc:
            logger.error(
                _TAG + " summary search failed: session_id={}, error_type={}",
                session_id,
                type(exc).__name__,
            )
            return _error("internal_error", "摘要搜索失败，请稍后重试")

    async def read(self, *, summary_id: object) -> dict[str, object]:
        """Read one overall or Batch Summary by its canonical identifier."""

        try:
            normalized_summary_id = _normalize_summary_id(summary_id)
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))

        session_id = "<unavailable>"
        try:
            session_id = str(self._session_id())
            document = await asyncio.to_thread(
                self._get_worker,
                session_id,
                normalized_summary_id,
            )
            if document is None:
                return _error(
                    "summary_not_found",
                    f"当前会话中不存在 Summary {normalized_summary_id}",
                )
            content, truncated = _truncate_content(
                document.text,
                SUMMARY_READ_CONTENT_BUDGET,
            )
            return {
                "ok": True,
                **_base_item(document),
                "excerpt": document.excerpt,
                "content": content,
                "contentTruncated": truncated,
            }
        except Exception as exc:
            logger.error(
                _TAG
                + " summary read failed: session_id={}, summary_id={}, error_type={}",
                session_id,
                normalized_summary_id,
                type(exc).__name__,
            )
            return _error("internal_error", "摘要读取失败，请稍后重试")

    def _list_worker(
        self,
        session_id: str,
    ) -> tuple["ResolvedSummaryDocument", ...]:
        try:
            locator = self._locator(session_id)
            return self._summaries.list_summaries(locator)
        finally:
            self._close_worker_connection()

    def _get_worker(
        self,
        session_id: str,
        summary_id: str,
    ) -> "ResolvedSummaryDocument | None":
        try:
            locator = self._locator(session_id)
            return self._summaries.get_summary(locator, summary_id)
        finally:
            self._close_worker_connection()

    def _locator(self, session_id: str) -> SessionReferenceLocator:
        session = self._session_data.get_session(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return SessionReferenceLocator(
            session_id=str(session.id),
            workspace_id=str(session.workspace_id),
            story_id=int(session.story_id),
        )


@dataclass(frozen=True, slots=True)
class _SummaryMatch:
    document: "ResolvedSummaryDocument"
    matched_terms: tuple[str, ...]
    matched_fields: tuple[str, ...]


def _search_documents(
    documents: tuple["ResolvedSummaryDocument", ...],
    terms: tuple[str, ...],
) -> list[_SummaryMatch]:
    matches: list[_SummaryMatch] = []
    for document in documents:
        fields = _search_fields(document)
        matched_terms = tuple(
            term
            for term in terms
            if any(
                _ascii_lower(term) in fields[field]
                for field in _SEARCH_FIELD_ORDER
            )
        )
        if not matched_terms:
            continue
        matched_fields = tuple(
            field
            for field in _SEARCH_FIELD_ORDER
            if any(_ascii_lower(term) in fields[field] for term in terms)
        )
        matches.append(_SummaryMatch(document, matched_terms, matched_fields))

    matches.sort(
        key=lambda match: (
            -len(match.matched_terms),
            -int(bool(_METADATA_FIELDS & set(match.matched_fields))),
            -int(match.document.kind == "batch"),
            -(
                match.document.batch_id
                if match.document.batch_id is not None
                else -1
            ),
            match.document.summary_id,
        )
    )
    return matches


def _search_fields(
    document: "ResolvedSummaryDocument",
) -> dict[str, str]:
    return {
        "title": _ascii_lower(document.title),
        "time": _ascii_lower(document.time),
        "location": _ascii_lower(document.location),
        "characters": _ascii_lower("\n".join(document.characters)),
        "text": _ascii_lower(document.text),
    }


def _search_item(match: _SummaryMatch) -> dict[str, object]:
    document = match.document
    excerpt = _matched_excerpt(
        document.text,
        match.matched_terms,
        fallback=document.excerpt,
    )
    return {
        **_base_item(document),
        "matchedTerms": list(match.matched_terms),
        "matchedFields": list(match.matched_fields),
        "excerpt": excerpt,
    }


def _base_item(
    document: "ResolvedSummaryDocument",
) -> dict[str, object]:
    return {
        "summaryId": document.summary_id,
        "kind": document.kind,
        "title": document.title,
        "frontMatter": _front_matter(document),
        "resolvedTurnRange": {
            "start": document.turn_start,
            "end": document.turn_end,
            "source": document.turn_range_source,
        },
        "updatedAt": document.updated_at,
    }


def _front_matter(
    document: "ResolvedSummaryDocument",
) -> dict[str, object]:
    if document.kind == "overall":
        return {
            "type": document.summary_type or "overall",
            "last_batch_id": document.last_batch_id,
        }
    return {
        "batch_id": document.batch_id,
        "title": document.title,
        "source_turn_start": document.source_turn_start,
        "source_turn_end": document.source_turn_end,
        "source_message_ids": list(document.source_message_ids),
        "time": document.time,
        "location": document.location,
        "characters": list(document.characters),
    }


def _matched_excerpt(
    content: str,
    matched_terms: tuple[str, ...],
    *,
    fallback: str,
) -> str:
    if not content:
        return fallback
    folded = _ascii_lower(content)
    positions = [
        folded.find(_ascii_lower(term))
        for term in matched_terms
        if term
    ]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return fallback
    if len(content) <= SUMMARY_SEARCH_EXCERPT_CHARS:
        return content

    anchor = min(positions)
    start = max(0, anchor - SUMMARY_SEARCH_EXCERPT_CHARS // 2)
    start = min(start, len(content) - SUMMARY_SEARCH_EXCERPT_CHARS)
    end = start + SUMMARY_SEARCH_EXCERPT_CHARS
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    interior_size = SUMMARY_SEARCH_EXCERPT_CHARS - len(prefix) - len(suffix)
    if prefix:
        start = min(start + 1, len(content))
    end = min(len(content), start + interior_size)
    if suffix and end == len(content):
        start = max(0, end - interior_size)
    return prefix + content[start:end] + suffix


def _truncate_content(content: str, budget: int) -> tuple[str, bool]:
    if len(content) <= budget:
        return content, False
    remaining = budget - 1
    head_size = (remaining + 1) // 2
    tail_size = remaining - head_size
    return content[:head_size] + "…" + content[-tail_size:], True


def _normalize_terms(raw_terms: object) -> tuple[str, ...]:
    if not isinstance(raw_terms, (list, tuple)):
        raise ValueError("terms 必须是包含 1–8 个字符串的数组")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_term in raw_terms:
        if not isinstance(raw_term, str):
            raise ValueError("terms 中的每一项都必须是字符串")
        term = raw_term.strip()
        if not term:
            continue
        if len(term) > SUMMARY_SEARCH_MAX_TERM_CHARS:
            raise ValueError(
                f"每个搜索词最多 {SUMMARY_SEARCH_MAX_TERM_CHARS} 个字符"
            )
        dedupe_key = _ascii_lower(term)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(term)

    if not normalized:
        raise ValueError("terms 至少需要包含一个非空搜索词")
    if len(normalized) > SUMMARY_SEARCH_MAX_TERMS:
        raise ValueError(f"terms 最多包含 {SUMMARY_SEARCH_MAX_TERMS} 个搜索词")
    return tuple(normalized)


def _normalize_summary_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("summary_id 必须是 overall 或十进制 Batch ID 字符串")
    normalized = value.strip()
    if normalized == "overall":
        return normalized
    if (
        len(normalized) > 32
        or not _BATCH_SUMMARY_ID_RE.fullmatch(normalized)
    ):
        raise ValueError("summary_id 必须是 overall 或十进制 Batch ID 字符串")
    return str(int(normalized))


def _bounded_int(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} 必须是整数")
    if value < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} 不能大于 {maximum}")
    return value


def _ascii_lower(value: str) -> str:
    return value.translate(_ASCII_LOWER_TRANSLATION)


def _error(error_code: str, message: str) -> dict[str, object]:
    return {
        "ok": False,
        "errorCode": error_code,
        "message": message,
    }
