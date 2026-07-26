"""Session-scoped Summary query provider for reference surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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
        documents = (
            (() if index.overall is None else (index.overall,))
            + tuple(reversed(index.batches))
        )
        return tuple(_resolve(document, turn_ranges) for document in documents)

    def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> ResolvedSummaryDocument | None:
        source = self._data.get_summary_source(locator)
        document = SummaryReader(source.runtime_dir).get(str(summary_id))
        if document is None:
            return None
        return _resolve(document, _turn_ranges(source))


def _turn_ranges(
    source: SessionReferenceSummarySource,
) -> dict[int, tuple[int, int]]:
    return {
        item.batch_id: (item.turn_start, item.turn_end)
        for item in source.batch_turn_ranges
    }


def _resolve(
    document: SummaryDocument,
    turn_ranges: dict[int, tuple[int, int]],
) -> ResolvedSummaryDocument:
    turn_start: int | None = None
    turn_end: int | None = None
    if document.batch_id is not None:
        turn_range = turn_ranges.get(document.batch_id)
        if turn_range is not None:
            turn_start, turn_end = turn_range
        elif (
            document.source_turn_start is not None
            and document.source_turn_end is not None
        ):
            turn_start = document.source_turn_start
            turn_end = document.source_turn_end
    elif document.kind == "overall":
        eligible_ranges = [
            turn_range
            for batch_id, turn_range in turn_ranges.items()
            if document.last_batch_id is None or batch_id <= document.last_batch_id
        ]
        if eligible_ranges:
            turn_start = min(item[0] for item in eligible_ranges)
            turn_end = max(item[1] for item in eligible_ranges)

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
    )


__all__ = [
    "ResolvedSummaryDocument",
    "SessionSummaryReferenceProvider",
    "SummarySourceDataPort",
]
