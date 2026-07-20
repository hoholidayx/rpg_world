"""Typed storage contracts for Story, Dream, and Persistent Memory ledgers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEvidence:
    """Immutable identity of one authoritative Session message."""

    message_id: int
    turn_id: int
    message_version: int
    content_hash: str


@dataclass(frozen=True)
class StoryMemoryRowValues:
    """Complete values for one Story Memory row create or update."""

    turn_id: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    source_turn_start: int
    source_turn_end: int
    dedupe_key: str
    dream_processed: bool
    metadata_schema_version: int
    metadata_json: str
    version: int


@dataclass(frozen=True)
class SessionStoryMemory:
    id: int
    session_id: str
    turn_id: int
    text: str = ""
    memory_kind: str = "event"
    epistemic_status: str = "confirmed"
    salience: float = 0.5
    source_turn_start: int = 0
    source_turn_end: int = 0
    dedupe_key: str = ""
    dream_processed: bool = False
    metadata_schema_version: int = 1
    metadata_json: str = "{}"
    evidence: tuple[MemoryEvidence, ...] = ()
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionStoryMemoryStats:
    total_facts: int
    dream_processed_facts: int
    pending_dream_facts: int
    latest_updated_at: str = ""


@dataclass(frozen=True)
class SessionStoryMemoryPage:
    items: tuple[SessionStoryMemory, ...]
    page: int
    page_size: int
    total: int
    stats: SessionStoryMemoryStats


@dataclass(frozen=True)
class DreamProposalItemEvidence:
    id: int
    proposal_item_id: str
    message_id: int
    turn_id: int
    message_version: int
    content_hash: str
    created_at: str = ""


@dataclass(frozen=True)
class DreamProposalItem:
    id: str
    proposal_id: str
    action: str
    dedupe_key: str
    selected: bool
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    reason: str = ""
    target_memory_id: str | None = None
    base_revision_number: int | None = None
    sort_order: int = 0
    evidence: tuple[DreamProposalItemEvidence, ...] = ()
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DreamProposal:
    id: str
    session_id: str
    depth: str
    scope: str
    status: str
    history_fingerprint: str
    source_fingerprint: str
    ledger_revision: int
    next_messages_manifest_json: str = "{}"
    next_story_memories_manifest_json: str = "{}"
    next_summary_batches_manifest_json: str = "{}"
    source_story_memory_ids: tuple[int, ...] = ()
    error_code: str = ""
    error_message: str = ""
    items: tuple[DreamProposalItem, ...] = ()
    applied_at: str = ""
    rejected_at: str = ""
    finished_at: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DreamProposalCreateValues:
    id: str
    session_id: str
    depth: str
    scope: str
    status: str
    history_fingerprint: str
    source_fingerprint: str
    ledger_revision: int
    next_messages_manifest_json: str
    next_story_memories_manifest_json: str
    next_summary_batches_manifest_json: str
    source_story_memory_ids: tuple[int, ...]


@dataclass(frozen=True)
class DreamProposalRowUpdate:
    status: str
    error_code: str
    error_message: str
    version: int
    set_applied_at: bool = False
    set_rejected_at: bool = False
    set_finished_at: bool = False


@dataclass(frozen=True)
class DreamProposalItemRowValues:
    id: str
    action: str
    dedupe_key: str
    selected: bool
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    reason: str
    target_memory_id: str | None
    base_revision_number: int | None
    sort_order: int
    evidence: tuple[MemoryEvidence, ...]


@dataclass(frozen=True)
class PersistentMemory:
    id: str
    session_id: str
    dedupe_key: str
    lifecycle: str
    current_revision_number: int
    superseded_by_memory_id: str | None = None
    created_from_proposal_id: str | None = None
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class PersistentMemoryCreateValues:
    id: str
    session_id: str
    dedupe_key: str
    lifecycle: str
    current_revision_number: int
    superseded_by_memory_id: str | None
    created_from_proposal_id: str | None


@dataclass(frozen=True)
class PersistentMemoryRowUpdate:
    lifecycle: str
    current_revision_number: int
    superseded_by_memory_id: str | None
    version: int


@dataclass(frozen=True)
class PersistentMemoryEvidence(MemoryEvidence):
    id: int
    revision_id: int
    created_at: str = ""


@dataclass(frozen=True)
class PersistentMemoryRevision:
    id: int
    memory_id: str
    revision_number: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    source_proposal_id: str | None = None
    evidence: tuple[PersistentMemoryEvidence, ...] = ()
    created_at: str = ""


@dataclass(frozen=True)
class PersistentMemoryRevisionCreateValues:
    memory_id: str
    revision_number: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    source_proposal_id: str | None
    evidence: tuple[MemoryEvidence, ...]


@dataclass(frozen=True)
class PersistentMemoryBundle:
    memory: PersistentMemory
    current_revision: PersistentMemoryRevision
    revisions: tuple[PersistentMemoryRevision, ...] = ()

    @property
    def text(self) -> str:
        return self.current_revision.text

    @property
    def memory_kind(self) -> str:
        return self.current_revision.memory_kind

    @property
    def epistemic_status(self) -> str:
        return self.current_revision.epistemic_status

    @property
    def salience(self) -> float:
        return self.current_revision.salience


@dataclass(frozen=True)
class DreamState:
    session_id: str
    ledger_revision: int = 0
    messages_manifest_json: str = "{}"
    story_memories_manifest_json: str = "{}"
    summary_batches_manifest_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DreamStateRowValues:
    ledger_revision: int
    messages_manifest_json: str
    story_memories_manifest_json: str
    summary_batches_manifest_json: str
    version: int


@dataclass(frozen=True)
class DreamResetResult:
    session_id: str
    memories_cleared: int = 0
    proposals_cleared: int = 0
    states_cleared: int = 0


__all__ = [
    "DreamProposal",
    "DreamProposalCreateValues",
    "DreamProposalItem",
    "DreamProposalItemEvidence",
    "DreamProposalItemRowValues",
    "DreamProposalRowUpdate",
    "DreamResetResult",
    "DreamState",
    "DreamStateRowValues",
    "MemoryEvidence",
    "PersistentMemory",
    "PersistentMemoryBundle",
    "PersistentMemoryCreateValues",
    "PersistentMemoryEvidence",
    "PersistentMemoryRevision",
    "PersistentMemoryRevisionCreateValues",
    "PersistentMemoryRowUpdate",
    "SessionStoryMemory",
    "SessionStoryMemoryPage",
    "SessionStoryMemoryStats",
    "StoryMemoryRowValues",
]
