"""Session-scoped SQL history query service used by main-Agent tools."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol

from loguru import logger

if TYPE_CHECKING:
    from rpg_data.model.session import (
        SessionHistorySearchHit,
        SessionHistoryTurnWindow,
        SessionMessage,
    )

_TAG = "[HistoryQueryService]"

HISTORY_SEARCH_DEFAULT_LIMIT = 5
HISTORY_SEARCH_MAX_LIMIT = 8
HISTORY_SEARCH_MAX_TERMS = 8
HISTORY_SEARCH_MAX_TERM_CHARS = 64
HISTORY_SEARCH_EXCERPT_CHARS = 280
HISTORY_READ_MAX_ADJACENT_TURNS = 2
HISTORY_READ_CONTENT_BUDGET = 20_000

_ASCII_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_LOWER = "abcdefghijklmnopqrstuvwxyz"
_ASCII_LOWER_TRANSLATION = str.maketrans(_ASCII_UPPER, _ASCII_LOWER)


class HistoryQueryDataPort(Protocol):
    """Narrow synchronous data boundary used by history query tools."""

    def search_history_turns(
        self,
        session_id: str,
        terms: Sequence[str],
        *,
        limit: int,
    ) -> list["SessionHistorySearchHit"]: ...

    def read_history_turn_window(
        self,
        session_id: str,
        *,
        anchor_turn_id: int,
        before_turns: int,
        after_turns: int,
    ) -> "SessionHistoryTurnWindow | None": ...


class HistoryQueryService:
    """Validate and execute read-only queries against committed SQL history."""

    def __init__(
        self,
        *,
        session_id: Callable[[], str],
        data: HistoryQueryDataPort,
        close_worker_connection: Callable[[], None],
    ) -> None:
        self._session_id = session_id
        self._data = data
        self._close_worker_connection = close_worker_connection

    async def search(
        self,
        *,
        terms: object,
        limit: object = HISTORY_SEARCH_DEFAULT_LIMIT,
    ) -> dict[str, object]:
        """Search the current Session and return unique candidate turns."""

        try:
            normalized_terms = _normalize_terms(terms)
            normalized_limit = _bounded_int(
                limit,
                name="limit",
                minimum=1,
                maximum=HISTORY_SEARCH_MAX_LIMIT,
            )
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))

        session_id = "<unavailable>"
        try:
            session_id = str(self._session_id())
            hits = await asyncio.to_thread(
                self._search_worker,
                session_id,
                normalized_terms,
                normalized_limit + 1,
            )
            has_more = len(hits) > normalized_limit
            return {
                "ok": True,
                "terms": list(normalized_terms),
                "items": [
                    _search_item(hit)
                    for hit in hits[:normalized_limit]
                ],
                "hasMore": has_more,
            }
        except Exception as exc:
            logger.error(
                _TAG + " history search failed: session_id={}, error_type={}",
                session_id,
                type(exc).__name__,
            )
            return _error("internal_error", "历史搜索失败，请稍后重试")

    async def read(
        self,
        *,
        turn_id: object,
        before_turns: object = 1,
        after_turns: object = 1,
    ) -> dict[str, object]:
        """Read one committed turn and bounded neighboring turn context."""

        try:
            anchor_turn_id = _bounded_int(
                turn_id,
                name="turn_id",
                minimum=1,
            )
            normalized_before = _bounded_int(
                before_turns,
                name="before_turns",
                minimum=0,
                maximum=HISTORY_READ_MAX_ADJACENT_TURNS,
            )
            normalized_after = _bounded_int(
                after_turns,
                name="after_turns",
                minimum=0,
                maximum=HISTORY_READ_MAX_ADJACENT_TURNS,
            )
        except ValueError as exc:
            return _error("invalid_arguments", str(exc))

        session_id = "<unavailable>"
        try:
            session_id = str(self._session_id())
            window = await asyncio.to_thread(
                self._read_worker,
                session_id,
                anchor_turn_id,
                normalized_before,
                normalized_after,
            )
            if window is None:
                return _error(
                    "turn_not_found",
                    f"当前会话中不存在 turn {anchor_turn_id}",
                )
            return _read_result(window)
        except Exception as exc:
            logger.error(
                _TAG
                + " history read failed: session_id={}, anchor_turn_id={}, error_type={}",
                session_id,
                anchor_turn_id,
                type(exc).__name__,
            )
            return _error("internal_error", "历史读取失败，请稍后重试")

    def _search_worker(
        self,
        session_id: str,
        terms: tuple[str, ...],
        limit: int,
    ) -> list["SessionHistorySearchHit"]:
        try:
            return self._data.search_history_turns(
                session_id,
                terms,
                limit=limit,
            )
        finally:
            self._close_worker_connection()

    def _read_worker(
        self,
        session_id: str,
        anchor_turn_id: int,
        before_turns: int,
        after_turns: int,
    ) -> "SessionHistoryTurnWindow | None":
        try:
            return self._data.read_history_turn_window(
                session_id,
                anchor_turn_id=anchor_turn_id,
                before_turns=before_turns,
                after_turns=after_turns,
            )
        finally:
            self._close_worker_connection()


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
        if len(term) > HISTORY_SEARCH_MAX_TERM_CHARS:
            raise ValueError(
                f"每个搜索词最多 {HISTORY_SEARCH_MAX_TERM_CHARS} 个字符"
            )
        dedupe_key = _ascii_lower(term)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(term)

    if not normalized:
        raise ValueError("terms 至少需要包含一个非空搜索词")
    if len(normalized) > HISTORY_SEARCH_MAX_TERMS:
        raise ValueError(f"terms 最多包含 {HISTORY_SEARCH_MAX_TERMS} 个搜索词")
    return tuple(normalized)


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


def _search_item(hit: "SessionHistorySearchHit") -> dict[str, object]:
    excerpt, truncated = _excerpt(
        str(hit.content),
        tuple(str(term) for term in hit.matched_terms),
    )
    return {
        "turnId": int(hit.turn_id),
        "messageId": int(hit.message_id),
        "role": str(hit.role),
        "mode": str(hit.mode),
        "matchedTerms": [str(term) for term in hit.matched_terms],
        "excerpt": excerpt,
        "excerptTruncated": truncated,
    }


def _excerpt(content: str, matched_terms: tuple[str, ...]) -> tuple[str, bool]:
    if len(content) <= HISTORY_SEARCH_EXCERPT_CHARS:
        return content, False

    normalized_content = _ascii_lower(content)
    positions = [
        normalized_content.find(_ascii_lower(term))
        for term in matched_terms
        if term
    ]
    positions = [position for position in positions if position >= 0]
    anchor = min(positions, default=0)

    start = max(0, anchor - HISTORY_SEARCH_EXCERPT_CHARS // 2)
    start = min(start, len(content) - HISTORY_SEARCH_EXCERPT_CHARS)
    end = start + HISTORY_SEARCH_EXCERPT_CHARS
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    interior_size = HISTORY_SEARCH_EXCERPT_CHARS - len(prefix) - len(suffix)

    if prefix:
        start = min(start + 1, len(content))
    end = min(len(content), start + interior_size)
    if suffix and end == len(content):
        start = max(0, end - interior_size)
    return prefix + content[start:end] + suffix, True


def _read_result(window: "SessionHistoryTurnWindow") -> dict[str, object]:
    messages = tuple(window.messages)
    allocations = _content_allocations(
        messages,
        tuple(int(turn_id) for turn_id in window.turn_ids),
        int(window.anchor_turn_id),
    )
    projected: list[dict[str, object]] = []
    any_truncated = False
    for index, message in enumerate(messages):
        content = str(message.content)
        projected_content, content_truncated = _truncate_content(
            content,
            allocations[index],
        )
        any_truncated = any_truncated or content_truncated
        projected.append({
            "messageId": int(message.id),
            "turnId": int(message.turn_id),
            "seqInTurn": int(message.seq_in_turn),
            "role": str(message.role),
            "mode": str(message.mode),
            "content": projected_content,
            "contentTruncated": content_truncated,
        })

    return {
        "ok": True,
        "anchorTurnId": int(window.anchor_turn_id),
        "turnIds": [int(turn_id) for turn_id in window.turn_ids],
        "messages": projected,
        "hasBefore": bool(window.has_before),
        "hasAfter": bool(window.has_after),
        "truncated": any_truncated,
    }


def _content_allocations(
    messages: Sequence["SessionMessage"],
    turn_ids: tuple[int, ...],
    anchor_turn_id: int,
) -> list[int]:
    allocations = [0] * len(messages)
    remaining = HISTORY_READ_CONTENT_BUDGET
    positions = {turn_id: index for index, turn_id in enumerate(turn_ids)}
    anchor_position = positions.get(anchor_turn_id, 0)
    prioritized_turns = sorted(
        turn_ids,
        key=lambda turn_id: (
            0 if turn_id == anchor_turn_id else 1,
            abs(positions[turn_id] - anchor_position),
            positions[turn_id],
        ),
    )

    for turn_id in prioritized_turns:
        indices = [
            index
            for index, message in enumerate(messages)
            if int(message.turn_id) == turn_id
        ]
        lengths = [len(str(messages[index].content)) for index in indices]
        turn_budget = min(remaining, sum(lengths))
        turn_allocations = _fair_allocations(lengths, turn_budget)
        for index, allocation in zip(indices, turn_allocations, strict=True):
            allocations[index] = allocation
        remaining -= sum(turn_allocations)
        if remaining <= 0:
            break

    return allocations


def _fair_allocations(lengths: Sequence[int], budget: int) -> list[int]:
    allocations = [0] * len(lengths)
    active = [index for index, length in enumerate(lengths) if length > 0]
    remaining = max(0, budget)
    while active and remaining:
        share = max(1, remaining // len(active))
        next_active: list[int] = []
        for index in active:
            capacity = lengths[index] - allocations[index]
            grant = min(capacity, share, remaining)
            allocations[index] += grant
            remaining -= grant
            if allocations[index] < lengths[index]:
                next_active.append(index)
            if remaining == 0:
                next_active.extend(
                    candidate
                    for candidate in active
                    if candidate > index and allocations[candidate] < lengths[candidate]
                )
                break
        active = next_active
    return allocations


def _truncate_content(content: str, budget: int) -> tuple[str, bool]:
    if len(content) <= budget:
        return content, False
    if budget <= 0:
        return "", True
    if budget == 1:
        return "…", True
    if budget == 2:
        return content[0] + content[-1], True

    remaining = budget - 1
    head_size = (remaining + 1) // 2
    tail_size = remaining - head_size
    return content[:head_size] + "…" + content[-tail_size:], True


def _ascii_lower(value: str) -> str:
    return value.translate(_ASCII_LOWER_TRANSLATION)


def _error(error_code: str, message: str) -> dict[str, object]:
    return {
        "ok": False,
        "errorCode": error_code,
        "message": message,
    }
