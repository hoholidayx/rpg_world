"""Typed read models for Session-scoped reference queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

from rpg_data.model.status import StatusTableDocument

_T = TypeVar("_T")


@dataclass(frozen=True)
class SessionReferenceLocator:
    """Complete ownership locator required by every reference read."""

    session_id: str
    workspace_id: str
    story_id: int


@dataclass(frozen=True)
class SessionReferenceScope:
    """Persisted Session identity and lifecycle facts."""

    locator: SessionReferenceLocator
    lifecycle: str
    title: str = ""
    player_character_id: int | None = None
    session_version: int = 1
    updated_at: str = ""

    @property
    def session_id(self) -> str:
        return self.locator.session_id

    @property
    def workspace_id(self) -> str:
        return self.locator.workspace_id

    @property
    def story_id(self) -> int:
        return self.locator.story_id


@dataclass(frozen=True)
class ReferenceDataPage(Generic[_T]):
    """One stable, one-based page returned by the persistence boundary."""

    items: tuple[_T, ...]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        if self.total == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size


@dataclass(frozen=True)
class SessionReferenceCharacter:
    """Lightweight character-card row without detail bodies."""

    id: int
    name: str
    description: str = ""
    sort_order: int = 0
    details_count: int = 0
    metadata_json: str = "{}"
    version: int = 1
    updated_at: str = ""

    @property
    def character_id(self) -> int:
        return self.id


@dataclass(frozen=True)
class SessionReferenceCharacterDetailItem:
    """Lightweight character-detail row without its body or tags."""

    id: int
    character_id: int
    name: str
    sort_order: int = 0
    version: int = 1
    updated_at: str = ""

    @property
    def detail_id(self) -> int:
        return self.id


@dataclass(frozen=True)
class SessionReferenceCharacterDetail(SessionReferenceCharacterDetailItem):
    """One fully loaded character-card detail."""

    content: str = ""
    tags_json: str = "[]"


@dataclass(frozen=True)
class SessionReferenceStatusOrder:
    """Caller-supplied field ranks compiled into stable SQL ordering."""

    status_kind_order: tuple[str, ...] = ()
    ordered_character_ids: tuple[int, ...] = ()
    associated_first: bool = False

    def __post_init__(self) -> None:
        kinds = tuple(str(value).strip() for value in self.status_kind_order)
        if any(not value for value in kinds) or len(set(kinds)) != len(kinds):
            raise ValueError(
                "status_kind_order must contain unique non-empty values"
            )
        if any(isinstance(value, bool) for value in self.ordered_character_ids):
            raise ValueError(
                "ordered_character_ids must contain unique positive IDs"
            )
        character_ids = tuple(int(value) for value in self.ordered_character_ids)
        if (
            any(value <= 0 for value in character_ids)
            or len(set(character_ids)) != len(character_ids)
        ):
            raise ValueError(
                "ordered_character_ids must contain unique positive IDs"
            )
        object.__setattr__(self, "status_kind_order", kinds)
        object.__setattr__(self, "ordered_character_ids", character_ids)
        if not isinstance(self.associated_first, bool):
            raise ValueError("associated_first must be a boolean")


@dataclass(frozen=True)
class SessionReferenceStatusTableItem:
    """Lightweight Session status-table row without its document."""

    id: int
    name: str
    status_kind: str
    description: str = ""
    sort_order: int = 0
    associated_character_id: int | None = None
    associated_character_name: str | None = None
    source_story_status_table_id: int | None = None
    origin: str = ""
    metadata_json: str = "{}"
    version: int = 1
    updated_at: str = ""

    @property
    def table_id(self) -> int:
        return self.id


@dataclass(frozen=True)
class SessionReferenceStatusTableDetail(SessionReferenceStatusTableItem):
    """One fully loaded Session status-table document."""

    document: StatusTableDocument = field(default_factory=StatusTableDocument)


@dataclass(frozen=True)
class SummaryBatchTurnRange:
    """Persisted min/max committed turn IDs for one Summary batch."""

    batch_id: int
    turn_start: int
    turn_end: int


@dataclass(frozen=True)
class SessionReferenceSummarySource:
    """Safe runtime location and persisted Summary batch associations."""

    runtime_dir: Path
    batch_turn_ranges: tuple[SummaryBatchTurnRange, ...] = ()


__all__ = [
    "ReferenceDataPage",
    "SessionReferenceCharacter",
    "SessionReferenceCharacterDetail",
    "SessionReferenceCharacterDetailItem",
    "SessionReferenceLocator",
    "SessionReferenceScope",
    "SessionReferenceStatusOrder",
    "SessionReferenceStatusTableDetail",
    "SessionReferenceStatusTableItem",
    "SessionReferenceSummarySource",
    "SummaryBatchTurnRange",
]
