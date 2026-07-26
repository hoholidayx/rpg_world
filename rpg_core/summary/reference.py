"""Session-scoped Summary query provider for reference surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from rpg_core.summary.reader import SummaryDocument, SummaryReader
from rpg_data.model.session_reference import (
    SessionReferenceLocator,
    SessionReferenceSummarySource,
)


@dataclass(frozen=True)
class ResolvedSummaryDocument:
    """One rendered Summary with authoritative persisted Turn ranges merged in."""

    summary_id: str
    kind: str
    title: str
    excerpt: str
    text: str
    turn_start: int | None
    turn_end: int | None
    time: str
    location: str
    characters: tuple[str, ...]
    updated_at: str | None
    summary_type: str = ""
    batch_id: int | None = None
    last_batch_id: int | None = None
    source_turn_start: int | None = None
    source_turn_end: int | None = None
    source_message_ids: tuple[int, ...] = ()
    turn_range_source: Literal["sql", "front_matter", "none"] = "none"


class SummarySourceDataPort(Protocol):
    def get_summary_source(
        self,
        locator: SessionReferenceLocator,
    ) -> SessionReferenceSummarySource: ...


class SessionSummaryReferenceProvider:
    """Read Summary markdown while leaving scope/path facts in ``rpg_data``."""

    def __init__(self, data: SummarySourceDataPort) -> None:
        self._data = data

    def list_summaries(
        self,
        locator: SessionReferenceLocator,
    ) -> tuple[ResolvedSummaryDocument, ...]:
        source = self._data.get_summary_source(locator)
        index = SummaryReader(source.runtime_dir).read_index()
        turn_ranges = _turn_ranges(source)
        batches = tuple(
            _resolve_batch(document, turn_ranges)
            for document in reversed(index.batches)
        )
        if index.overall is None:
            return batches
        return (
            _resolve_overall(index.overall, index.batches, turn_ranges),
            *batches,
        )

    def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> ResolvedSummaryDocument | None:
        source = self._data.get_summary_source(locator)
        index = SummaryReader(source.runtime_dir).read_index()
        turn_ranges = _turn_ranges(source)
        if str(summary_id) == "overall":
            if index.overall is None:
                return None
            return _resolve_overall(index.overall, index.batches, turn_ranges)
        try:
            batch_id = int(summary_id)
        except (TypeError, ValueError):
            return None
        document = next(
            (item for item in index.batches if item.batch_id == batch_id),
            None,
        )
        return (
            _resolve_batch(document, turn_ranges)
            if document is not None
            else None
        )


def _turn_ranges(
    source: SessionReferenceSummarySource,
) -> dict[int, tuple[int, int]]:
    return {
        item.batch_id: (item.turn_start, item.turn_end)
        for item in source.batch_turn_ranges
    }


def _resolve_batch(
    document: SummaryDocument,
    turn_ranges: dict[int, tuple[int, int]],
) -> ResolvedSummaryDocument:
    turn_start, turn_end, range_source = _resolved_batch_range(
        document,
        turn_ranges,
    )
    return _resolved_document(
        document,
        turn_start=turn_start,
        turn_end=turn_end,
        turn_range_source=range_source,
    )


def _resolve_overall(
    document: SummaryDocument,
    batches: tuple[SummaryDocument, ...],
    turn_ranges: dict[int, tuple[int, int]],
) -> ResolvedSummaryDocument:
    batches_by_id = {
        item.batch_id: item
        for item in batches
        if item.batch_id is not None
    }
    eligible_batch_ids = sorted(
        batch_id
        for batch_id in set(turn_ranges) | set(batches_by_id)
        if (
            document.last_batch_id is None
            or batch_id <= document.last_batch_id
        )
    )
    eligible_ranges: list[tuple[int, int]] = []
    range_sources: set[str] = set()
    for batch_id in eligible_batch_ids:
        if batch_id in turn_ranges:
            eligible_ranges.append(turn_ranges[batch_id])
            range_sources.add("sql")
            continue
        batch = batches_by_id.get(batch_id)
        if batch is None:
            continue
        turn_start, turn_end, range_source = _resolved_batch_range(
            batch,
            turn_ranges,
        )
        if turn_start is not None and turn_end is not None:
            eligible_ranges.append((turn_start, turn_end))
            range_sources.add(range_source)

    turn_start = (
        min(item[0] for item in eligible_ranges)
        if eligible_ranges
        else None
    )
    turn_end = (
        max(item[1] for item in eligible_ranges)
        if eligible_ranges
        else None
    )
    range_source: Literal["sql", "front_matter", "none"]
    if "sql" in range_sources:
        range_source = "sql"
    elif "front_matter" in range_sources:
        range_source = "front_matter"
    else:
        range_source = "none"
    return _resolved_document(
        document,
        turn_start=turn_start,
        turn_end=turn_end,
        turn_range_source=range_source,
    )


def _resolved_batch_range(
    document: SummaryDocument,
    turn_ranges: dict[int, tuple[int, int]],
) -> tuple[
    int | None,
    int | None,
    Literal["sql", "front_matter", "none"],
]:
    if document.batch_id is not None:
        turn_range = turn_ranges.get(document.batch_id)
        if turn_range is not None:
            return turn_range[0], turn_range[1], "sql"
    if (
        document.source_turn_start is not None
        and document.source_turn_end is not None
        and document.source_turn_end >= document.source_turn_start
    ):
        return (
            document.source_turn_start,
            document.source_turn_end,
            "front_matter",
        )
    return None, None, "none"


def _resolved_document(
    document: SummaryDocument,
    *,
    turn_start: int | None,
    turn_end: int | None,
    turn_range_source: Literal["sql", "front_matter", "none"],
) -> ResolvedSummaryDocument:

    return ResolvedSummaryDocument(
        summary_id=(
            "overall" if document.kind == "overall" else str(document.batch_id)
        ),
        kind=document.kind,
        title=document.title,
        excerpt=document.excerpt,
        text=document.markdown,
        turn_start=turn_start,
        turn_end=turn_end,
        time=document.time,
        location=document.location,
        characters=document.characters,
        updated_at=document.updated_at,
        summary_type=document.summary_type,
        batch_id=document.batch_id,
        last_batch_id=document.last_batch_id,
        source_turn_start=document.source_turn_start,
        source_turn_end=document.source_turn_end,
        source_message_ids=document.source_message_ids,
        turn_range_source=turn_range_source,
    )


__all__ = [
    "ResolvedSummaryDocument",
    "SessionSummaryReferenceProvider",
    "SummarySourceDataPort",
]
