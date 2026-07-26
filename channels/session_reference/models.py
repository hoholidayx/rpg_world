"""Player-facing Session reference projections for lightweight channels."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from rpg_data.model.session_reference import SessionReferenceLocator


T = TypeVar("T")


class SessionReferenceResource(StrEnum):
    """Read-only resource groups exposed by the channel reference layer."""

    CHARACTERS = "characters"
    STATUS_TABLES = "status_tables"
    SUMMARIES = "summaries"
    STORY_MEMORIES = "story_memories"
    PERSISTENT_MEMORIES = "persistent_memories"
    TURN_ANNOTATIONS = "turn_annotations"


ALL_SESSION_REFERENCE_RESOURCES = frozenset(SessionReferenceResource)


@dataclass(frozen=True)
class SessionReferencePolicy:
    """Immutable product policy for one reference-reader composition."""

    enabled_resources: frozenset[SessionReferenceResource] = (
        ALL_SESSION_REFERENCE_RESOURCES
    )
    max_page_size: int = 100
    excerpt_limit: int = 160

    def __post_init__(self) -> None:
        resources = frozenset(
            SessionReferenceResource(item) for item in self.enabled_resources
        )
        if (
            isinstance(self.max_page_size, bool)
            or not isinstance(self.max_page_size, int)
            or self.max_page_size <= 0
        ):
            raise ValueError("max_page_size must be positive")
        if (
            isinstance(self.excerpt_limit, bool)
            or not isinstance(self.excerpt_limit, int)
            or self.excerpt_limit < 20
        ):
            raise ValueError("excerpt_limit must be at least 20")
        object.__setattr__(self, "enabled_resources", resources)


DEFAULT_SESSION_REFERENCE_POLICY = SessionReferencePolicy()


@dataclass(frozen=True)
class ReferencePage(Generic[T]):
    items: tuple[T, ...]
    page: int
    page_size: int
    total: int
    total_pages: int


@dataclass(frozen=True)
class SessionReferenceScope:
    locator: SessionReferenceLocator
    title: str
    lifecycle: str
    player_character_id: int | None
    version: int
    updated_at: str


@dataclass(frozen=True)
class CharacterSummary:
    id: int
    name: str
    description: str
    is_player: bool
    details_count: int
    version: int
    updated_at: str


@dataclass(frozen=True)
class CharacterDetailSummary:
    id: int
    title: str
    version: int = 1
    updated_at: str = ""


@dataclass(frozen=True)
class CharacterDetail:
    id: int
    character_id: int
    title: str
    content: str
    version: int
    updated_at: str


@dataclass(frozen=True)
class CharacterCard:
    id: int
    name: str
    description: str
    is_player: bool
    details_count: int
    version: int
    updated_at: str


@dataclass(frozen=True)
class StatusRow:
    key: str
    value: str


@dataclass(frozen=True)
class StatusTableSummary:
    id: int
    name: str
    description: str
    kind: str
    character_id: int | None
    character_name: str | None
    version: int
    updated_at: str


@dataclass(frozen=True)
class StatusTableDetail:
    id: int
    name: str
    description: str
    kind: str
    character_id: int | None
    character_name: str | None
    rows: tuple[StatusRow, ...]
    version: int
    updated_at: str


@dataclass(frozen=True)
class SummarySummary:
    id: str
    title: str
    excerpt: str
    kind: str
    turn_start: int | None
    turn_end: int | None
    time: str
    location: str
    characters: tuple[str, ...]
    updated_at: str | None


@dataclass(frozen=True)
class SummaryDetail:
    id: str
    title: str
    excerpt: str
    text: str
    kind: str
    turn_start: int | None
    turn_end: int | None
    time: str
    location: str
    characters: tuple[str, ...]
    updated_at: str | None


@dataclass(frozen=True)
class EvidenceReference:
    turn_id: int
    message_id: int


@dataclass(frozen=True)
class NarrativeOutcomeAnnotation:
    outcome_code: str
    label: str
    reason: str
    actor: str | None = None


@dataclass(frozen=True)
class PlotInjectionAnnotation:
    event_title: str
    directive: str


@dataclass(frozen=True)
class CommittedTurnAnnotations:
    turn_id: int
    outcome: NarrativeOutcomeAnnotation | None = None
    plot_injections: tuple[PlotInjectionAnnotation, ...] = ()


@dataclass(frozen=True)
class StoryMemorySummary:
    id: int
    title: str
    excerpt: str
    memory_kind: str
    epistemic_status: str
    salience: float
    turn_start: int
    turn_end: int
    evidence: tuple[EvidenceReference, ...]
    version: int
    updated_at: str


@dataclass(frozen=True)
class StoryMemoryDetail:
    id: int
    title: str
    excerpt: str
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    turn_start: int
    turn_end: int
    evidence: tuple[EvidenceReference, ...]
    version: int
    updated_at: str


@dataclass(frozen=True)
class PersistentMemorySummary:
    id: str
    title: str
    excerpt: str
    memory_kind: str
    epistemic_status: str
    salience: float
    evidence: tuple[EvidenceReference, ...]
    revision_number: int
    updated_at: str


@dataclass(frozen=True)
class PersistentMemoryDetail:
    id: str
    title: str
    excerpt: str
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    evidence: tuple[EvidenceReference, ...]
    revision_number: int
    updated_at: str


__all__ = [
    "ALL_SESSION_REFERENCE_RESOURCES",
    "CharacterCard",
    "CharacterDetail",
    "CharacterDetailSummary",
    "CharacterSummary",
    "CommittedTurnAnnotations",
    "DEFAULT_SESSION_REFERENCE_POLICY",
    "EvidenceReference",
    "NarrativeOutcomeAnnotation",
    "PersistentMemoryDetail",
    "PersistentMemorySummary",
    "PlotInjectionAnnotation",
    "ReferencePage",
    "SessionReferenceLocator",
    "SessionReferencePolicy",
    "SessionReferenceResource",
    "SessionReferenceScope",
    "StatusRow",
    "StatusTableDetail",
    "StatusTableSummary",
    "StoryMemoryDetail",
    "StoryMemorySummary",
    "SummaryDetail",
    "SummarySummary",
]
