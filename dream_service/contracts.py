"""Public, storage-neutral contracts used by the Dream HTTP process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rp_memory.dream.types import (
    DreamProposalItemDraft,
    DreamSelection,
    DreamSourceSnapshot,
)


@dataclass(frozen=True)
class DreamEvidenceView:
    message_id: int
    turn_id: int
    message_version: int
    content_hash: str


@dataclass(frozen=True)
class DreamProposalItemView:
    item_id: str
    action: str
    target_memory_id: str | None
    base_revision_number: int | None
    selected: bool
    text: str | None
    memory_kind: str | None
    epistemic_status: str | None
    salience: float | None
    reason: str
    evidence: tuple[DreamEvidenceView, ...]


@dataclass(frozen=True)
class DreamProposalView:
    proposal_id: str
    session_id: str
    depth: str
    scope: str
    status: str
    ledger_revision: int
    items: tuple[DreamProposalItemView, ...]
    error_code: str
    error_message: str
    created_at: str
    updated_at: str
    finished_at: str


@dataclass(frozen=True)
class DreamProposalListView:
    items: tuple[DreamProposalView, ...]


@dataclass(frozen=True)
class DreamRevisionView:
    revision_number: int
    text: str
    memory_kind: str
    epistemic_status: str
    salience: float
    dedupe_key: str
    proposal_id: str | None
    created_at: str


@dataclass(frozen=True)
class DreamMemoryView:
    memory_id: str
    session_id: str
    lifecycle: str
    current_revision_number: int
    superseded_by_memory_id: str | None
    evidence_valid: bool
    current_revision: DreamRevisionView
    revisions: tuple[DreamRevisionView, ...]
    evidence: tuple[DreamEvidenceView, ...]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DreamMemoryListView:
    items: tuple[DreamMemoryView, ...]
    active_count: int
    active_limit: int


@dataclass(frozen=True)
class DreamProposalItemUpdate:
    item_id: str
    selected: bool | None = None
    text: str | None = None
    memory_kind: str | None = None
    epistemic_status: str | None = None
    salience: float | None = None


class DreamRepository(Protocol):
    def build_source_snapshot(self, session_id: str) -> DreamSourceSnapshot: ...

    def create_proposal(self, selection: DreamSelection) -> DreamProposalView: ...

    def get_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView | None: ...

    def list_proposals(self, session_id: str) -> DreamProposalListView: ...

    def set_proposal_ready(
        self,
        proposal_id: str,
        items: tuple[DreamProposalItemDraft, ...],
    ) -> DreamProposalView: ...

    def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> DreamProposalView: ...

    def interrupt_generating(self) -> int: ...

    def update_proposal_items(
        self,
        session_id: str,
        proposal_id: str,
        updates: tuple[DreamProposalItemUpdate, ...],
    ) -> DreamProposalView: ...

    def reject_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView: ...

    def apply_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView: ...

    def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
    ) -> DreamMemoryListView: ...

    def restore_memory(
        self,
        session_id: str,
        memory_id: str,
    ) -> DreamMemoryView: ...
