"""Typed SQL-backed persistent-memory ledger and Dream proposal workflow."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from uuid import uuid4

from peewee import Database, IntegrityError, SQL

from commons.text_identity import stable_text_identity_key
from rpg_data import models
from rpg_data.repositories._utils import to_session_message, to_session_story_memory
from rpg_data.repositories.records import (
    SessionDreamProposalItemEvidenceRecord,
    SessionDreamProposalItemRecord,
    SessionDreamProposalRecord,
    SessionDreamStateRecord,
    SessionMessageRecord,
    SessionPersistentMemoryEvidenceRecord,
    SessionPersistentMemoryRecord,
    SessionPersistentMemoryRevisionRecord,
    SessionRecord,
    SessionStoryMemoryRecord,
    bind_database,
)

__all__ = [
    "DreamActiveMemoryLimitError",
    "DreamDataError",
    "DreamEvidenceInvalidError",
    "DreamMemoryService",
    "DreamProposalConflictError",
    "DreamProposalStaleError",
    "DreamProposalStateError",
]

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_CONTEXT_KIND_ORDER = {
    kind: index
    for index, kind in enumerate(
        (
            "character",
            "relationship",
            "commitment",
            "clue",
            "world_fact",
            "event",
            "state_change",
        )
    )
}
_EVIDENCE_ROLES = frozenset(
    {models.MESSAGE_ROLE_USER, models.MESSAGE_ROLE_ASSISTANT}
)
_EVIDENCE_MODES = frozenset({models.TURN_MODE_IC, models.TURN_MODE_GM})


class DreamDataError(RuntimeError):
    """Base class for deterministic Dream data-workflow failures."""


class DreamProposalConflictError(DreamDataError):
    """Raised when a Session already has a generating proposal."""


class DreamProposalStateError(DreamDataError):
    """Raised when an operation is invalid for the current proposal state."""


class DreamProposalStaleError(DreamDataError):
    """Raised after a proposal is marked stale by a snapshot guard."""


class DreamActiveMemoryLimitError(DreamDataError):
    """Raised when applying/restoring would exceed the active-memory limit."""


class DreamEvidenceInvalidError(DreamDataError):
    """Raised when immutable evidence no longer matches mutable history."""


class DreamMemoryService:
    """Manage Session Dream proposals and the revisioned persistent ledger."""

    def __init__(
        self,
        database: Database,
        *,
        max_active_memories: int = models.DREAM_MAX_ACTIVE_MEMORIES,
    ) -> None:
        if isinstance(max_active_memories, bool):
            raise ValueError(
                "max_active_memories must be an integer between 1 and "
                f"{models.DREAM_MAX_ACTIVE_MEMORIES}"
            )
        normalized_limit = int(max_active_memories)
        if not 1 <= normalized_limit <= models.DREAM_MAX_ACTIVE_MEMORIES:
            raise ValueError(
                "max_active_memories must be an integer between 1 and "
                f"{models.DREAM_MAX_ACTIVE_MEMORIES}"
            )
        self._database = database
        self._max_active_memories = normalized_limit
        bind_database(database)

    @property
    def max_active_memories(self) -> int:
        return self._max_active_memories

    def create_proposal(
        self,
        session_id: str,
        *,
        depth: str,
        scope: str,
        history_fingerprint: str,
        source_fingerprint: str,
        next_messages_manifest_json: str | Mapping[str, object] = "{}",
        next_story_memories_manifest_json: str | Mapping[str, object] = "{}",
        next_summary_batches_manifest_json: str | Mapping[str, object] = "{}",
        source_story_memory_ids: Iterable[int] = (),
        proposal_id: str | None = None,
    ) -> models.DreamProposal:
        normalized_session_id = str(session_id)
        normalized_depth = _choice(depth, models.DREAM_DEPTHS, "Dream depth")
        normalized_scope = _choice(scope, models.DREAM_SCOPES, "Dream scope")
        normalized_history = _fingerprint(history_fingerprint, "history_fingerprint")
        normalized_source = _fingerprint(source_fingerprint, "source_fingerprint")
        normalized_ids = _positive_ids(source_story_memory_ids, "story_memory_id")
        normalized_proposal_id = str(proposal_id or uuid4())
        if not normalized_proposal_id:
            raise ValueError("proposal_id must not be empty")

        actual_history = self._history_fingerprint(normalized_session_id)
        if actual_history != normalized_history:
            raise DreamProposalStaleError(
                "Dream proposal history fingerprint does not match current history"
            )

        with self._database.atomic():
            self._require_session(normalized_session_id)
            self._require_story_memories(normalized_session_id, normalized_ids)
            state = self._get_or_create_state_record(normalized_session_id)
            if (
                SessionDreamProposalRecord.select()
                .where(
                    (SessionDreamProposalRecord.session == normalized_session_id)
                    & (
                        SessionDreamProposalRecord.status
                        == models.DREAM_PROPOSAL_STATUS_GENERATING
                    )
                )
                .exists()
            ):
                raise DreamProposalConflictError(
                    f"Session already has a generating Dream proposal: {normalized_session_id}"
                )
            try:
                SessionDreamProposalRecord.create(
                    id=normalized_proposal_id,
                    session=normalized_session_id,
                    depth=normalized_depth,
                    scope=normalized_scope,
                    status=models.DREAM_PROPOSAL_STATUS_GENERATING,
                    history_fingerprint=normalized_history,
                    source_fingerprint=normalized_source,
                    ledger_revision=int(state.ledger_revision),
                    next_messages_manifest_json=_canonical_json_object(
                        next_messages_manifest_json,
                        "next_messages_manifest_json",
                    ),
                    next_story_memories_manifest_json=_canonical_json_object(
                        next_story_memories_manifest_json,
                        "next_story_memories_manifest_json",
                    ),
                    next_summary_batches_manifest_json=_canonical_json_object(
                        next_summary_batches_manifest_json,
                        "next_summary_batches_manifest_json",
                    ),
                    source_story_memory_ids_json=json.dumps(normalized_ids),
                )
            except IntegrityError as exc:
                raise DreamProposalConflictError(
                    f"Unable to create Dream proposal for Session: {normalized_session_id}"
                ) from exc
        proposal = self.get_proposal(normalized_proposal_id)
        if proposal is None:
            raise RuntimeError("Dream proposal disappeared after creation")
        return proposal

    def get_proposal(self, proposal_id: str) -> models.DreamProposal | None:
        row = (
            SessionDreamProposalRecord.select()
            .where(SessionDreamProposalRecord.id == str(proposal_id))
            .first()
        )
        return self._to_proposal(row) if row is not None else None

    def list_proposals(self, session_id: str) -> list[models.DreamProposal]:
        rows = (
            SessionDreamProposalRecord.select()
            .where(SessionDreamProposalRecord.session == str(session_id))
            .order_by(
                SessionDreamProposalRecord.created_at.desc(),
                SessionDreamProposalRecord.id.desc(),
            )
        )
        return [self._to_proposal(row) for row in rows]

    def set_proposal_ready(
        self,
        proposal_id: str,
        items: Sequence[models.DreamProposalItemDraft],
    ) -> models.DreamProposal:
        if len(items) > models.DREAM_MAX_PROPOSAL_ITEMS:
            raise ValueError(
                "Dream proposal may contain at most "
                f"{models.DREAM_MAX_PROPOSAL_ITEMS} items"
            )
        drafts = tuple(self._normalize_item_draft(item) for item in items)
        with self._database.atomic():
            proposal = self._require_proposal_record(proposal_id)
            self._require_proposal_status(
                proposal,
                {models.DREAM_PROPOSAL_STATUS_GENERATING},
            )
            SessionDreamProposalItemRecord.delete().where(
                SessionDreamProposalItemRecord.proposal == proposal.id
            ).execute()
            for draft in drafts:
                target = self._validate_draft_target(proposal, draft)
                item_id = str(uuid4())
                SessionDreamProposalItemRecord.create(
                    id=item_id,
                    proposal=proposal.id,
                    action=draft.action,
                    target_memory=draft.target_memory_id,
                    base_revision_number=draft.base_revision_number,
                    dedupe_key=(
                        str(target.dedupe_key)
                        if target is not None
                        and draft.action in {
                            models.DREAM_ACTION_REVISE,
                            models.DREAM_ACTION_RETIRE,
                        }
                        else draft.dedupe_key
                    ),
                    selected=draft.selected,
                    text=draft.text,
                    memory_kind=draft.memory_kind,
                    epistemic_status=draft.epistemic_status,
                    salience=draft.salience,
                    reason=draft.reason,
                    sort_order=draft.sort_order,
                )
                for evidence in draft.evidence:
                    SessionDreamProposalItemEvidenceRecord.create(
                        proposal_item=item_id,
                        message_id=evidence.message_id,
                        turn_id=evidence.turn_id,
                        message_version=evidence.message_version,
                        content_hash=evidence.content_hash,
                    )
            self._validate_selected_target_uniqueness(proposal.id)
            self._update_proposal_status(
                proposal,
                models.DREAM_PROPOSAL_STATUS_READY,
                finished=True,
            )
        ready = self.get_proposal(str(proposal_id))
        if ready is None:
            raise RuntimeError("Dream proposal disappeared after becoming ready")
        return ready

    def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.DreamProposal:
        with self._database.atomic():
            proposal = self._require_proposal_record(proposal_id)
            self._require_proposal_status(
                proposal,
                {models.DREAM_PROPOSAL_STATUS_GENERATING},
            )
            proposal.error_code = str(error_code or "DREAM_GENERATION_FAILED")
            proposal.error_message = str(error_message or "")
            self._update_proposal_status(
                proposal,
                models.DREAM_PROPOSAL_STATUS_FAILED,
                finished=True,
            )
        failed = self.get_proposal(str(proposal_id))
        if failed is None:
            raise RuntimeError("Dream proposal disappeared after failure")
        return failed

    def interrupt_generating(self, session_id: str | None = None) -> int:
        where_clause = (
            SessionDreamProposalRecord.status
            == models.DREAM_PROPOSAL_STATUS_GENERATING
        )
        if session_id is not None:
            where_clause &= SessionDreamProposalRecord.session == str(session_id)
        return int(
            SessionDreamProposalRecord.update(
                status=models.DREAM_PROPOSAL_STATUS_INTERRUPTED,
                error_code="DREAM_GENERATION_INTERRUPTED",
                finished_at=SQL("CURRENT_TIMESTAMP"),
                updated_at=SQL("CURRENT_TIMESTAMP"),
                version=SessionDreamProposalRecord.version + 1,
            )
            .where(where_clause)
            .execute()
        )

    def update_proposal_items(
        self,
        proposal_id: str,
        patches: Sequence[models.DreamProposalItemPatch],
    ) -> models.DreamProposal:
        if len(patches) > models.DREAM_MAX_PROPOSAL_ITEMS:
            raise ValueError(
                "Dream proposal update may contain at most "
                f"{models.DREAM_MAX_PROPOSAL_ITEMS} items"
            )
        normalized = tuple(self._normalize_item_patch(patch) for patch in patches)
        if len({patch.item_id for patch in normalized}) != len(normalized):
            raise ValueError("Dream proposal item patches must have unique item_id values")
        with self._database.atomic():
            proposal = self._require_proposal_record(proposal_id)
            self._require_proposal_status(
                proposal,
                {models.DREAM_PROPOSAL_STATUS_READY},
            )
            for patch in normalized:
                item = (
                    SessionDreamProposalItemRecord.select()
                    .where(
                        (SessionDreamProposalItemRecord.id == patch.item_id)
                        & (SessionDreamProposalItemRecord.proposal == proposal.id)
                    )
                    .first()
                )
                if item is None:
                    raise FileNotFoundError(
                        f"Dream proposal item not found: {patch.item_id}"
                    )
                if patch.selected is not None:
                    item.selected = patch.selected
                if patch.text is not None:
                    item.text = _memory_text(patch.text, allow_empty=item.action == models.DREAM_ACTION_RETIRE)
                if patch.memory_kind is not None:
                    item.memory_kind = _choice(
                        patch.memory_kind,
                        models.STORY_MEMORY_KINDS,
                        "memory_kind",
                    )
                if patch.epistemic_status is not None:
                    item.epistemic_status = _choice(
                        patch.epistemic_status,
                        models.STORY_MEMORY_EPISTEMIC_STATUSES,
                        "epistemic_status",
                    )
                if patch.salience is not None:
                    item.salience = _salience(patch.salience)
                if str(item.action) in {
                    models.DREAM_ACTION_ADD,
                    models.DREAM_ACTION_SUPERSEDE,
                }:
                    item.dedupe_key = stable_text_identity_key(
                        item.memory_kind,
                        item.epistemic_status,
                        item.text,
                    )
                item.updated_at = SQL("CURRENT_TIMESTAMP")
                item.save()
            self._validate_selected_target_uniqueness(proposal.id)
            proposal.updated_at = SQL("CURRENT_TIMESTAMP")
            proposal.version = int(proposal.version) + 1
            proposal.save()
        updated = self.get_proposal(str(proposal_id))
        if updated is None:
            raise RuntimeError("Dream proposal disappeared after item update")
        return updated

    def reject_proposal(self, proposal_id: str) -> models.DreamProposal:
        with self._database.atomic():
            proposal = self._require_proposal_record(proposal_id)
            self._require_proposal_status(
                proposal,
                {models.DREAM_PROPOSAL_STATUS_READY},
            )
            proposal.status = models.DREAM_PROPOSAL_STATUS_REJECTED
            proposal.rejected_at = SQL("CURRENT_TIMESTAMP")
            proposal.finished_at = SQL("CURRENT_TIMESTAMP")
            proposal.updated_at = SQL("CURRENT_TIMESTAMP")
            proposal.version = int(proposal.version) + 1
            proposal.save()
        rejected = self.get_proposal(str(proposal_id))
        if rejected is None:
            raise RuntimeError("Dream proposal disappeared after rejection")
        return rejected

    def apply_proposal(
        self,
        proposal_id: str,
        *,
        history_fingerprint: str,
        source_fingerprint: str,
    ) -> models.DreamApplyResult:
        supplied_history = _fingerprint(history_fingerprint, "history_fingerprint")
        supplied_source = _fingerprint(source_fingerprint, "source_fingerprint")
        stale_reason = ""
        evidence_error = ""
        created_ids: list[str] = []
        revised_ids: list[str] = []
        retired_ids: list[str] = []
        superseded_ids: list[str] = []
        active_count = 0
        next_ledger_revision = 0

        with self._database.atomic():
            proposal = self._require_proposal_record(proposal_id)
            self._require_proposal_status(
                proposal,
                {models.DREAM_PROPOSAL_STATUS_READY},
            )
            state = self._get_or_create_state_record(str(proposal.session_id))
            actual_history = self._history_fingerprint(str(proposal.session_id))
            if (
                supplied_history != str(proposal.history_fingerprint)
                or actual_history != str(proposal.history_fingerprint)
            ):
                stale_reason = "Dream history changed after proposal generation"
            elif supplied_source != str(proposal.source_fingerprint):
                stale_reason = "Dream derived sources changed after proposal generation"
            elif int(state.ledger_revision) != int(proposal.ledger_revision):
                stale_reason = "Persistent-memory ledger changed after proposal generation"
            elif not self._proposal_story_memory_sources_match(proposal):
                stale_reason = "Dream story-memory sources changed after proposal generation"

            items = self._item_records(str(proposal.id), selected_only=True)
            if not stale_reason:
                evidence_error = self._first_invalid_proposal_evidence(
                    str(proposal.session_id),
                    items,
                )
            if stale_reason or evidence_error:
                proposal.error_code = (
                    "DREAM_EVIDENCE_INVALID" if evidence_error else "DREAM_PROPOSAL_STALE"
                )
                proposal.error_message = evidence_error or stale_reason
                self._update_proposal_status(
                    proposal,
                    models.DREAM_PROPOSAL_STATUS_STALE,
                    finished=True,
                )
            else:
                active_count = self._validate_apply_and_project_active_count(
                    str(proposal.session_id),
                    items,
                )
                for item in items:
                    if item.action == models.DREAM_ACTION_ADD:
                        memory_id = self._create_memory_from_item(proposal, item)
                        created_ids.append(memory_id)
                    elif item.action == models.DREAM_ACTION_REVISE:
                        memory_id = self._revise_memory_from_item(proposal, item)
                        revised_ids.append(memory_id)
                    elif item.action == models.DREAM_ACTION_SUPERSEDE:
                        old_id, new_id = self._supersede_memory_from_item(proposal, item)
                        superseded_ids.append(old_id)
                        created_ids.append(new_id)
                    elif item.action == models.DREAM_ACTION_RETIRE:
                        retired_ids.append(self._retire_memory_from_item(item))
                    else:  # pragma: no cover - protected by schema and normalization
                        raise DreamProposalStateError(
                            f"Unsupported Dream action: {item.action}"
                        )

                next_ledger_revision = int(state.ledger_revision) + 1
                state.ledger_revision = next_ledger_revision
                state.messages_manifest_json = str(
                    proposal.next_messages_manifest_json or "{}"
                )
                state.story_memories_manifest_json = str(
                    proposal.next_story_memories_manifest_json or "{}"
                )
                state.summary_batches_manifest_json = str(
                    proposal.next_summary_batches_manifest_json or "{}"
                )
                state.version = int(state.version) + 1
                state.updated_at = SQL("CURRENT_TIMESTAMP")
                state.save()
                self._mark_source_story_memories_processed(proposal)
                proposal.status = models.DREAM_PROPOSAL_STATUS_APPLIED
                proposal.applied_at = SQL("CURRENT_TIMESTAMP")
                proposal.finished_at = SQL("CURRENT_TIMESTAMP")
                proposal.updated_at = SQL("CURRENT_TIMESTAMP")
                proposal.version = int(proposal.version) + 1
                proposal.save()

        if evidence_error:
            raise DreamEvidenceInvalidError(evidence_error)
        if stale_reason:
            raise DreamProposalStaleError(stale_reason)
        applied = self.get_proposal(str(proposal_id))
        if applied is None:
            raise RuntimeError("Dream proposal disappeared after apply")
        return models.DreamApplyResult(
            proposal=applied,
            ledger_revision=next_ledger_revision,
            active_memory_count=active_count,
            created_memory_ids=tuple(created_ids),
            revised_memory_ids=tuple(revised_ids),
            retired_memory_ids=tuple(retired_ids),
            superseded_memory_ids=tuple(superseded_ids),
        )

    def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
        include_invalid_evidence: bool = True,
    ) -> list[models.PersistentMemoryBundle]:
        with self._database.atomic():
            return self._list_memories(
                session_id,
                lifecycle=lifecycle,
                include_invalid_evidence=include_invalid_evidence,
            )

    def _list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None,
        include_invalid_evidence: bool,
    ) -> list[models.PersistentMemoryBundle]:
        normalized_session_id = str(session_id)
        where_clause = SessionPersistentMemoryRecord.session == normalized_session_id
        if lifecycle is not None:
            normalized_lifecycle = _choice(
                lifecycle,
                models.DREAM_LIFECYCLES,
                "memory lifecycle",
            )
            where_clause &= (
                SessionPersistentMemoryRecord.lifecycle == normalized_lifecycle
            )
        rows = (
            SessionPersistentMemoryRecord.select()
            .where(where_clause)
            .order_by(
                SessionPersistentMemoryRecord.created_at,
                SessionPersistentMemoryRecord.id,
            )
        )
        bundles = [self._to_memory_bundle(row) for row in rows]
        if include_invalid_evidence:
            return bundles
        return [bundle for bundle in bundles if bundle.evidence_valid]

    def list_context_memories(
        self,
        session_id: str,
    ) -> list[models.PersistentMemoryBundle]:
        with self._database.atomic():
            return self._list_context_memories(session_id)

    def _list_context_memories(
        self,
        session_id: str,
    ) -> list[models.PersistentMemoryBundle]:
        normalized_session_id = str(session_id)
        memory_rows = list(
            SessionPersistentMemoryRecord.select()
            .where(
                (SessionPersistentMemoryRecord.session == normalized_session_id)
                & (
                    SessionPersistentMemoryRecord.lifecycle
                    == models.DREAM_LIFECYCLE_ACTIVE
                )
            )
        )
        if not memory_rows:
            return []

        revision_rows = list(
            SessionPersistentMemoryRevisionRecord.select()
            .join(
                SessionPersistentMemoryRecord,
                on=(
                    SessionPersistentMemoryRevisionRecord.memory
                    == SessionPersistentMemoryRecord.id
                ),
            )
            .where(
                (SessionPersistentMemoryRecord.session == normalized_session_id)
                & (
                    SessionPersistentMemoryRecord.lifecycle
                    == models.DREAM_LIFECYCLE_ACTIVE
                )
                & (
                    SessionPersistentMemoryRevisionRecord.revision_number
                    == SessionPersistentMemoryRecord.current_revision_number
                )
            )
        )
        revision_by_memory = {
            str(row.memory_id): row for row in revision_rows
        }
        revision_ids = [int(row.id) for row in revision_rows]
        evidence_rows = list(
            SessionPersistentMemoryEvidenceRecord.select()
            .where(
                SessionPersistentMemoryEvidenceRecord.revision.in_(revision_ids)
            )
            .order_by(
                SessionPersistentMemoryEvidenceRecord.revision,
                SessionPersistentMemoryEvidenceRecord.turn_id,
                SessionPersistentMemoryEvidenceRecord.message_id,
            )
        ) if revision_ids else []
        evidence_by_revision: dict[int, list[SessionPersistentMemoryEvidenceRecord]] = {}
        for row in evidence_rows:
            evidence_by_revision.setdefault(int(row.revision_id), []).append(row)

        message_ids = sorted({int(row.message_id) for row in evidence_rows})
        message_by_id = {
            int(row.id): row
            for row in (
                SessionMessageRecord.select()
                .where(
                    (SessionMessageRecord.session == normalized_session_id)
                    & (SessionMessageRecord.id.in_(message_ids))
                )
            )
        } if message_ids else {}

        bundles: list[models.PersistentMemoryBundle] = []
        for memory_row in memory_rows:
            revision_row = revision_by_memory.get(str(memory_row.id))
            if revision_row is None:
                continue
            evidence = tuple(
                _persistent_evidence(row)
                for row in evidence_by_revision.get(int(revision_row.id), [])
            )
            if not evidence or not all(
                _evidence_matches_row(message_by_id.get(item.message_id), item)
                for item in evidence
            ):
                continue
            revision = _persistent_revision(revision_row, evidence=evidence)
            memory = _persistent_memory(memory_row)
            bundles.append(
                models.PersistentMemoryBundle(
                    memory=memory,
                    current_revision=revision,
                    revisions=(revision,),
                    evidence_valid=True,
                )
            )
        return sorted(
            bundles,
            key=lambda bundle: (
                _CONTEXT_KIND_ORDER.get(bundle.memory_kind, len(_CONTEXT_KIND_ORDER)),
                bundle.memory.id,
            ),
        )

    def restore_memory(
        self,
        session_id: str,
        memory_id: str,
    ) -> models.PersistentMemoryBundle:
        normalized_session_id = str(session_id)
        with self._database.atomic():
            memory = (
                SessionPersistentMemoryRecord.select()
                .where(
                    (SessionPersistentMemoryRecord.id == str(memory_id))
                    & (SessionPersistentMemoryRecord.session == normalized_session_id)
                )
                .first()
            )
            if memory is None:
                raise FileNotFoundError(f"Persistent memory not found: {memory_id}")
            if str(memory.lifecycle) != models.DREAM_LIFECYCLE_RETIRED:
                raise DreamProposalStateError(
                    "Only retired persistent memories can be restored"
                )
            bundle = self._to_memory_bundle(memory)
            if not bundle.evidence_valid:
                raise DreamEvidenceInvalidError(
                    "Retired persistent memory evidence no longer matches current history"
                )
            active_count = self._active_count(normalized_session_id)
            if active_count >= self._max_active_memories:
                raise DreamActiveMemoryLimitError(
                    f"Session may have at most {self._max_active_memories} active memories"
                )
            memory.lifecycle = models.DREAM_LIFECYCLE_ACTIVE
            memory.version = int(memory.version) + 1
            memory.updated_at = SQL("CURRENT_TIMESTAMP")
            memory.save()
            state = self._get_or_create_state_record(normalized_session_id)
            state.ledger_revision = int(state.ledger_revision) + 1
            state.version = int(state.version) + 1
            state.updated_at = SQL("CURRENT_TIMESTAMP")
            state.save()
        restored = next(
            (
                item
                for item in self.list_memories(normalized_session_id)
                if item.memory.id == str(memory_id)
            ),
            None,
        )
        if restored is None:
            raise RuntimeError("Persistent memory disappeared after restore")
        return restored

    def get_state(self, session_id: str) -> models.DreamState:
        normalized_session_id = str(session_id)
        self._require_session(normalized_session_id)
        row = (
            SessionDreamStateRecord.select()
            .where(SessionDreamStateRecord.session == normalized_session_id)
            .first()
        )
        if row is None:
            return models.DreamState(session_id=normalized_session_id)
        return _to_state(row)

    def build_source_snapshot(self, session_id: str) -> models.DreamSourceSnapshot:
        with self._database.atomic():
            return self._build_source_snapshot(session_id)

    def _build_source_snapshot(self, session_id: str) -> models.DreamSourceSnapshot:
        normalized_session_id = str(session_id)
        self._require_session(normalized_session_id)
        message_rows = list(
            SessionMessageRecord.select()
            .where(SessionMessageRecord.session == normalized_session_id)
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )
        story_rows = list(
            SessionStoryMemoryRecord.select()
            .where(SessionStoryMemoryRecord.session == normalized_session_id)
            .order_by(SessionStoryMemoryRecord.id)
        )
        return models.DreamSourceSnapshot(
            session_id=normalized_session_id,
            messages=tuple(to_session_message(row) for row in message_rows),
            story_memories=tuple(to_session_story_memory(row) for row in story_rows),
            active_memories=tuple(
                self.list_memories(
                    normalized_session_id,
                    lifecycle=models.DREAM_LIFECYCLE_ACTIVE,
                )
            ),
            state=self.get_state(normalized_session_id),
            history_fingerprint=_history_fingerprint_from_rows(message_rows),
            story_memory_fingerprint=_story_memory_fingerprint_from_rows(story_rows),
        )

    def clear(self, session_id: str) -> models.DreamResetResult:
        normalized_session_id = str(session_id)
        with self._database.atomic():
            memories = int(
                SessionPersistentMemoryRecord.delete()
                .where(SessionPersistentMemoryRecord.session == normalized_session_id)
                .execute()
            )
            proposals = int(
                SessionDreamProposalRecord.delete()
                .where(SessionDreamProposalRecord.session == normalized_session_id)
                .execute()
            )
            states = int(
                SessionDreamStateRecord.delete()
                .where(SessionDreamStateRecord.session == normalized_session_id)
                .execute()
            )
        return models.DreamResetResult(
            session_id=normalized_session_id,
            memories_cleared=memories,
            proposals_cleared=proposals,
            states_cleared=states,
        )

    def _to_proposal(
        self,
        row: SessionDreamProposalRecord,
    ) -> models.DreamProposal:
        items = tuple(self._to_item(item) for item in self._item_records(str(row.id)))
        try:
            raw_ids = json.loads(str(row.source_story_memory_ids_json or "[]"))
        except json.JSONDecodeError:
            raw_ids = []
        source_ids = tuple(
            int(value)
            for value in raw_ids
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        ) if isinstance(raw_ids, list) else ()
        return models.DreamProposal(
            id=str(row.id),
            session_id=str(row.session_id),
            depth=str(row.depth),
            scope=str(row.scope),
            status=str(row.status),
            history_fingerprint=str(row.history_fingerprint),
            source_fingerprint=str(row.source_fingerprint),
            ledger_revision=int(row.ledger_revision),
            next_messages_manifest_json=str(row.next_messages_manifest_json or "{}"),
            next_story_memories_manifest_json=str(
                row.next_story_memories_manifest_json or "{}"
            ),
            next_summary_batches_manifest_json=str(
                row.next_summary_batches_manifest_json or "{}"
            ),
            source_story_memory_ids=source_ids,
            error_code=str(row.error_code or ""),
            error_message=str(row.error_message or ""),
            items=items,
            applied_at=str(row.applied_at or ""),
            rejected_at=str(row.rejected_at or ""),
            finished_at=str(row.finished_at or ""),
            version=int(row.version),
            created_at=str(row.created_at),
            updated_at=str(row.updated_at),
        )

    def _to_item(
        self,
        row: SessionDreamProposalItemRecord,
    ) -> models.DreamProposalItem:
        evidence_rows = (
            SessionDreamProposalItemEvidenceRecord.select()
            .where(
                SessionDreamProposalItemEvidenceRecord.proposal_item == str(row.id)
            )
            .order_by(
                SessionDreamProposalItemEvidenceRecord.turn_id,
                SessionDreamProposalItemEvidenceRecord.message_id,
            )
        )
        return models.DreamProposalItem(
            id=str(row.id),
            proposal_id=str(row.proposal_id),
            action=str(row.action),
            target_memory_id=(
                str(row.target_memory_id)
                if row.target_memory_id is not None
                else None
            ),
            base_revision_number=(
                int(row.base_revision_number)
                if row.base_revision_number is not None
                else None
            ),
            dedupe_key=str(row.dedupe_key),
            selected=bool(row.selected),
            text=str(row.text or ""),
            memory_kind=str(row.memory_kind),
            epistemic_status=str(row.epistemic_status),
            salience=float(row.salience),
            reason=str(row.reason or ""),
            sort_order=int(row.sort_order),
            evidence=tuple(
                models.DreamProposalItemEvidence(
                    id=int(evidence.id),
                    proposal_item_id=str(evidence.proposal_item_id),
                    message_id=int(evidence.message_id),
                    turn_id=int(evidence.turn_id),
                    message_version=int(evidence.message_version),
                    content_hash=str(evidence.content_hash),
                    created_at=str(evidence.created_at),
                )
                for evidence in evidence_rows
            ),
            created_at=str(row.created_at),
            updated_at=str(row.updated_at),
        )

    def _to_memory_bundle(
        self,
        row: SessionPersistentMemoryRecord,
    ) -> models.PersistentMemoryBundle:
        revision_rows = list(
            SessionPersistentMemoryRevisionRecord.select()
            .where(SessionPersistentMemoryRevisionRecord.memory == str(row.id))
            .order_by(SessionPersistentMemoryRevisionRecord.revision_number)
        )
        revisions = tuple(self._to_revision(revision) for revision in revision_rows)
        current = next(
            (
                revision
                for revision in revisions
                if revision.revision_number == int(row.current_revision_number)
            ),
            None,
        )
        if current is None:
            raise RuntimeError(
                f"Persistent memory current revision is missing: {row.id}"
            )
        memory = models.PersistentMemory(
            id=str(row.id),
            session_id=str(row.session_id),
            dedupe_key=str(row.dedupe_key),
            lifecycle=str(row.lifecycle),
            current_revision_number=int(row.current_revision_number),
            superseded_by_memory_id=(
                str(row.superseded_by_memory_id)
                if row.superseded_by_memory_id is not None
                else None
            ),
            created_from_proposal_id=(
                str(row.created_from_proposal_id)
                if row.created_from_proposal_id is not None
                else None
            ),
            version=int(row.version),
            created_at=str(row.created_at),
            updated_at=str(row.updated_at),
        )
        return models.PersistentMemoryBundle(
            memory=memory,
            current_revision=current,
            revisions=revisions,
            evidence_valid=self._revision_evidence_valid(str(row.session_id), current),
        )

    def _to_revision(
        self,
        row: SessionPersistentMemoryRevisionRecord,
    ) -> models.PersistentMemoryRevision:
        evidence_rows = (
            SessionPersistentMemoryEvidenceRecord.select()
            .where(SessionPersistentMemoryEvidenceRecord.revision == int(row.id))
            .order_by(
                SessionPersistentMemoryEvidenceRecord.turn_id,
                SessionPersistentMemoryEvidenceRecord.message_id,
            )
        )
        return models.PersistentMemoryRevision(
            id=int(row.id),
            memory_id=str(row.memory_id),
            revision_number=int(row.revision_number),
            text=str(row.text),
            memory_kind=str(row.memory_kind),
            epistemic_status=str(row.epistemic_status),
            salience=float(row.salience),
            source_proposal_id=(
                str(row.source_proposal_id)
                if row.source_proposal_id is not None
                else None
            ),
            evidence=tuple(
                models.PersistentMemoryEvidence(
                    id=int(evidence.id),
                    revision_id=int(evidence.revision_id),
                    message_id=int(evidence.message_id),
                    turn_id=int(evidence.turn_id),
                    message_version=int(evidence.message_version),
                    content_hash=str(evidence.content_hash),
                    created_at=str(evidence.created_at),
                )
                for evidence in evidence_rows
            ),
            created_at=str(row.created_at),
        )

    def _normalize_item_draft(
        self,
        draft: models.DreamProposalItemDraft,
    ) -> models.DreamProposalItemDraft:
        if not isinstance(draft, models.DreamProposalItemDraft):
            raise TypeError("Dream proposal items must be DreamProposalItemDraft values")
        action = _choice(draft.action, models.DREAM_ACTIONS, "Dream action")
        evidence = tuple(_normalize_evidence(item) for item in draft.evidence)
        if len(evidence) > models.DREAM_MAX_EVIDENCE_PER_ITEM:
            raise ValueError(
                "Dream proposal item may cite at most "
                f"{models.DREAM_MAX_EVIDENCE_PER_ITEM} evidence messages"
            )
        if len({item.message_id for item in evidence}) != len(evidence):
            raise ValueError("Dream proposal item evidence message IDs must be unique")
        if action != models.DREAM_ACTION_RETIRE and not evidence:
            raise ValueError(f"Dream {action} item must have evidence")
        text = _memory_text(
            draft.text,
            allow_empty=action == models.DREAM_ACTION_RETIRE,
        )
        memory_kind = _choice(
            draft.memory_kind,
            models.STORY_MEMORY_KINDS,
            "memory_kind",
        )
        epistemic_status = _choice(
            draft.epistemic_status,
            models.STORY_MEMORY_EPISTEMIC_STATUSES,
            "epistemic_status",
        )
        if action in {
            models.DREAM_ACTION_ADD,
            models.DREAM_ACTION_SUPERSEDE,
        }:
            dedupe_key = stable_text_identity_key(
                memory_kind,
                epistemic_status,
                text,
            )
        else:
            dedupe_key = _fingerprint(draft.dedupe_key, "dedupe_key")
        return models.DreamProposalItemDraft(
            action=action,
            target_memory_id=(
                str(draft.target_memory_id) if draft.target_memory_id else None
            ),
            base_revision_number=(
                _positive_int(draft.base_revision_number, "base_revision_number")
                if draft.base_revision_number is not None
                else None
            ),
            dedupe_key=dedupe_key,
            selected=bool(draft.selected),
            text=text,
            memory_kind=memory_kind,
            epistemic_status=epistemic_status,
            salience=_salience(draft.salience),
            reason=_bounded_text(
                draft.reason,
                name="Dream proposal reason",
                max_chars=models.DREAM_MAX_REASON_CHARS,
                allow_empty=True,
            ),
            sort_order=int(draft.sort_order),
            evidence=evidence,
        )

    def _normalize_item_patch(
        self,
        patch: models.DreamProposalItemPatch,
    ) -> models.DreamProposalItemPatch:
        if not isinstance(patch, models.DreamProposalItemPatch):
            raise TypeError("Dream item updates must be DreamProposalItemPatch values")
        item_id = str(patch.item_id)
        if not item_id:
            raise ValueError("Dream item patch item_id must not be empty")
        return models.DreamProposalItemPatch(
            item_id=item_id,
            selected=(bool(patch.selected) if patch.selected is not None else None),
            text=patch.text,
            memory_kind=patch.memory_kind,
            epistemic_status=patch.epistemic_status,
            salience=patch.salience,
        )

    def _validate_draft_target(
        self,
        proposal: SessionDreamProposalRecord,
        draft: models.DreamProposalItemDraft,
    ) -> SessionPersistentMemoryRecord | None:
        target_actions = {
            models.DREAM_ACTION_REVISE,
            models.DREAM_ACTION_SUPERSEDE,
            models.DREAM_ACTION_RETIRE,
        }
        if draft.action == models.DREAM_ACTION_ADD:
            if draft.target_memory_id is not None or draft.base_revision_number is not None:
                raise ValueError("Dream add items cannot have a target memory")
            return None
        if draft.action not in target_actions or draft.target_memory_id is None:
            raise ValueError(f"Dream {draft.action} item requires target_memory_id")
        target = (
            SessionPersistentMemoryRecord.select()
            .where(
                (SessionPersistentMemoryRecord.id == draft.target_memory_id)
                & (SessionPersistentMemoryRecord.session == proposal.session_id)
            )
            .first()
        )
        if target is None:
            raise FileNotFoundError(
                f"Dream target memory not found: {draft.target_memory_id}"
            )
        if draft.base_revision_number != int(target.current_revision_number):
            raise DreamProposalStaleError(
                f"Dream target memory revision changed: {draft.target_memory_id}"
            )
        return target

    def _validate_selected_target_uniqueness(self, proposal_id: str) -> None:
        proposal = self._require_proposal_record(proposal_id)
        seen_targets: set[str] = set()
        seen_new_keys: set[str] = set()
        for item in self._item_records(proposal_id, selected_only=True):
            if item.target_memory_id is not None:
                target = str(item.target_memory_id)
                if target in seen_targets:
                    raise DreamProposalStateError(
                        "A Dream proposal cannot apply multiple actions to memory: "
                        f"{target}"
                    )
                seen_targets.add(target)
            if str(item.action) not in {
                models.DREAM_ACTION_ADD,
                models.DREAM_ACTION_SUPERSEDE,
            }:
                continue
            dedupe_key = str(item.dedupe_key)
            if dedupe_key in seen_new_keys:
                raise DreamProposalStateError(
                    f"Dream proposal creates duplicate memory key: {dedupe_key}"
                )
            seen_new_keys.add(dedupe_key)
            if (
                SessionPersistentMemoryRecord.select()
                .where(
                    (SessionPersistentMemoryRecord.session == proposal.session_id)
                    & (SessionPersistentMemoryRecord.dedupe_key == dedupe_key)
                )
                .exists()
            ):
                raise DreamProposalStateError(
                    f"Persistent memory key already exists: {dedupe_key}"
                )

    def _validate_apply_and_project_active_count(
        self,
        session_id: str,
        items: Sequence[SessionDreamProposalItemRecord],
    ) -> int:
        active_count = self._active_count(session_id)
        new_dedupe_keys: set[str] = set()
        targeted: set[str] = set()
        for item in items:
            action = str(item.action)
            target = None
            if item.target_memory_id is not None:
                target_id = str(item.target_memory_id)
                if target_id in targeted:
                    raise DreamProposalStateError(
                        f"Proposal targets memory more than once: {target_id}"
                    )
                targeted.add(target_id)
                target = (
                    SessionPersistentMemoryRecord.select()
                    .where(
                        (SessionPersistentMemoryRecord.id == target_id)
                        & (SessionPersistentMemoryRecord.session == session_id)
                    )
                    .first()
                )
                if target is None:
                    raise DreamProposalStaleError(
                        f"Dream target memory no longer exists: {target_id}"
                    )
                if str(target.lifecycle) != models.DREAM_LIFECYCLE_ACTIVE:
                    raise DreamProposalStaleError(
                        f"Dream target memory is no longer active: {target_id}"
                    )
                if int(target.current_revision_number) != int(item.base_revision_number or 0):
                    raise DreamProposalStaleError(
                        f"Dream target memory revision changed: {target_id}"
                    )
            if action in {models.DREAM_ACTION_ADD, models.DREAM_ACTION_SUPERSEDE}:
                dedupe_key = str(item.dedupe_key)
                if dedupe_key in new_dedupe_keys:
                    raise DreamProposalStateError(
                        f"Proposal creates duplicate memory key: {dedupe_key}"
                    )
                new_dedupe_keys.add(dedupe_key)
                existing = (
                    SessionPersistentMemoryRecord.select()
                    .where(
                        (SessionPersistentMemoryRecord.session == session_id)
                        & (SessionPersistentMemoryRecord.dedupe_key == dedupe_key)
                    )
                    .first()
                )
                if existing is not None:
                    raise DreamProposalStateError(
                        f"Persistent memory key already exists: {dedupe_key}"
                    )
            if action == models.DREAM_ACTION_ADD:
                active_count += 1
            elif action == models.DREAM_ACTION_RETIRE:
                active_count -= 1
            elif action == models.DREAM_ACTION_SUPERSEDE:
                # One active target is replaced by one new active memory.
                pass
        if active_count > self._max_active_memories:
            raise DreamActiveMemoryLimitError(
                f"Session may have at most {self._max_active_memories} active memories; "
                f"proposal would create {active_count}"
            )
        return active_count

    def _create_memory_from_item(
        self,
        proposal: SessionDreamProposalRecord,
        item: SessionDreamProposalItemRecord,
    ) -> str:
        memory_id = str(uuid4())
        SessionPersistentMemoryRecord.create(
            id=memory_id,
            session=proposal.session_id,
            dedupe_key=str(item.dedupe_key),
            lifecycle=models.DREAM_LIFECYCLE_ACTIVE,
            current_revision_number=1,
            created_from_proposal=proposal.id,
        )
        self._create_revision(proposal, item, memory_id, 1)
        return memory_id

    def _revise_memory_from_item(
        self,
        proposal: SessionDreamProposalRecord,
        item: SessionDreamProposalItemRecord,
    ) -> str:
        memory = self._require_target_memory(proposal, item)
        revision_number = int(memory.current_revision_number) + 1
        self._create_revision(proposal, item, str(memory.id), revision_number)
        memory.current_revision_number = revision_number
        memory.version = int(memory.version) + 1
        memory.updated_at = SQL("CURRENT_TIMESTAMP")
        memory.save()
        return str(memory.id)

    def _supersede_memory_from_item(
        self,
        proposal: SessionDreamProposalRecord,
        item: SessionDreamProposalItemRecord,
    ) -> tuple[str, str]:
        old = self._require_target_memory(proposal, item)
        new_id = self._create_memory_from_item(proposal, item)
        old.lifecycle = models.DREAM_LIFECYCLE_SUPERSEDED
        old.superseded_by_memory = new_id
        old.version = int(old.version) + 1
        old.updated_at = SQL("CURRENT_TIMESTAMP")
        old.save()
        return str(old.id), new_id

    def _retire_memory_from_item(
        self,
        item: SessionDreamProposalItemRecord,
    ) -> str:
        memory = SessionPersistentMemoryRecord.get_by_id(str(item.target_memory_id))
        memory.lifecycle = models.DREAM_LIFECYCLE_RETIRED
        memory.version = int(memory.version) + 1
        memory.updated_at = SQL("CURRENT_TIMESTAMP")
        memory.save()
        return str(memory.id)

    def _create_revision(
        self,
        proposal: SessionDreamProposalRecord,
        item: SessionDreamProposalItemRecord,
        memory_id: str,
        revision_number: int,
    ) -> None:
        revision = SessionPersistentMemoryRevisionRecord.create(
            memory=memory_id,
            revision_number=revision_number,
            text=str(item.text),
            memory_kind=str(item.memory_kind),
            epistemic_status=str(item.epistemic_status),
            salience=float(item.salience),
            source_proposal=proposal.id,
        )
        evidence_rows = (
            SessionDreamProposalItemEvidenceRecord.select()
            .where(SessionDreamProposalItemEvidenceRecord.proposal_item == item.id)
            .order_by(SessionDreamProposalItemEvidenceRecord.id)
        )
        for evidence in evidence_rows:
            SessionPersistentMemoryEvidenceRecord.create(
                revision=revision.id,
                message_id=int(evidence.message_id),
                turn_id=int(evidence.turn_id),
                message_version=int(evidence.message_version),
                content_hash=str(evidence.content_hash),
            )

    def _require_target_memory(
        self,
        proposal: SessionDreamProposalRecord,
        item: SessionDreamProposalItemRecord,
    ) -> SessionPersistentMemoryRecord:
        memory = (
            SessionPersistentMemoryRecord.select()
            .where(
                (SessionPersistentMemoryRecord.id == str(item.target_memory_id))
                & (SessionPersistentMemoryRecord.session == proposal.session_id)
            )
            .first()
        )
        if memory is None:
            raise DreamProposalStaleError(
                f"Dream target memory no longer exists: {item.target_memory_id}"
            )
        return memory

    def _revision_evidence_valid(
        self,
        session_id: str,
        revision: models.PersistentMemoryRevision,
    ) -> bool:
        if not revision.evidence:
            return False
        return all(
            self._evidence_matches(
                session_id,
                evidence.message_id,
                evidence.turn_id,
                evidence.message_version,
                evidence.content_hash,
            )
            for evidence in revision.evidence
        )

    def _first_invalid_proposal_evidence(
        self,
        session_id: str,
        items: Sequence[SessionDreamProposalItemRecord],
    ) -> str:
        for item in items:
            if str(item.action) == models.DREAM_ACTION_RETIRE:
                continue
            evidence_rows = list(
                SessionDreamProposalItemEvidenceRecord.select()
                .where(SessionDreamProposalItemEvidenceRecord.proposal_item == item.id)
            )
            if not evidence_rows:
                return f"Dream proposal item has no evidence: {item.id}"
            for evidence in evidence_rows:
                if not self._evidence_matches(
                    session_id,
                    int(evidence.message_id),
                    int(evidence.turn_id),
                    int(evidence.message_version),
                    str(evidence.content_hash),
                ):
                    return (
                        "Dream evidence no longer matches current history: "
                        f"item={item.id}, message={evidence.message_id}"
                    )
        return ""

    def _evidence_matches(
        self,
        session_id: str,
        message_id: int,
        turn_id: int,
        message_version: int,
        content_hash: str,
    ) -> bool:
        message = (
            SessionMessageRecord.select()
            .where(
                (SessionMessageRecord.id == int(message_id))
                & (SessionMessageRecord.session == str(session_id))
            )
            .first()
        )
        return bool(
            message is not None
            and str(message.role) in _EVIDENCE_ROLES
            and str(message.mode) in _EVIDENCE_MODES
            and int(message.turn_id) == int(turn_id)
            and int(message.version) == int(message_version)
            and _content_hash(str(message.content or "")) == str(content_hash)
        )

    def _proposal_story_memory_sources_match(
        self,
        proposal: SessionDreamProposalRecord,
    ) -> bool:
        ids = self._proposal_story_memory_ids(proposal)
        if not ids:
            return True
        rows = list(
            SessionStoryMemoryRecord.select()
            .where(
                (SessionStoryMemoryRecord.session == proposal.session_id)
                & (SessionStoryMemoryRecord.id.in_(ids))
            )
        )
        if len(rows) != len(ids):
            return False
        try:
            manifest = json.loads(
                str(proposal.next_story_memories_manifest_json or "{}")
            )
        except json.JSONDecodeError:
            return False
        if not isinstance(manifest, dict):
            return False
        for row in rows:
            entry = manifest.get(str(row.id))
            if not isinstance(entry, dict):
                return False
            expected = str(entry.get("fingerprint") or "")
            actual = (
                f"{int(row.version)}:{_content_hash(str(row.text or ''))}:"
                f"{int(row.source_turn_start)}:{int(row.source_turn_end)}"
            )
            if expected != actual:
                return False
        return True

    def _mark_source_story_memories_processed(
        self,
        proposal: SessionDreamProposalRecord,
    ) -> None:
        ids = self._proposal_story_memory_ids(proposal)
        if not ids:
            return
        SessionStoryMemoryRecord.update(
            dream_processed=True,
            updated_at=SQL("CURRENT_TIMESTAMP"),
        ).where(
            (SessionStoryMemoryRecord.session == proposal.session_id)
            & (SessionStoryMemoryRecord.id.in_(ids))
        ).execute()

    def _proposal_story_memory_ids(
        self,
        proposal: SessionDreamProposalRecord,
    ) -> tuple[int, ...]:
        try:
            raw = json.loads(str(proposal.source_story_memory_ids_json or "[]"))
        except json.JSONDecodeError:
            return ()
        if not isinstance(raw, list):
            return ()
        return tuple(
            int(value)
            for value in raw
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
        )

    def _item_records(
        self,
        proposal_id: str,
        *,
        selected_only: bool = False,
    ) -> list[SessionDreamProposalItemRecord]:
        where_clause = SessionDreamProposalItemRecord.proposal == str(proposal_id)
        if selected_only:
            where_clause &= SessionDreamProposalItemRecord.selected == True  # noqa: E712
        return list(
            SessionDreamProposalItemRecord.select()
            .where(where_clause)
            .order_by(
                SessionDreamProposalItemRecord.sort_order,
                SessionDreamProposalItemRecord.id,
            )
        )

    def _active_count(self, session_id: str) -> int:
        return int(
            SessionPersistentMemoryRecord.select()
            .where(
                (SessionPersistentMemoryRecord.session == str(session_id))
                & (
                    SessionPersistentMemoryRecord.lifecycle
                    == models.DREAM_LIFECYCLE_ACTIVE
                )
            )
            .count()
        )

    def _get_or_create_state_record(self, session_id: str) -> SessionDreamStateRecord:
        row = (
            SessionDreamStateRecord.select()
            .where(SessionDreamStateRecord.session == str(session_id))
            .first()
        )
        if row is None:
            row = SessionDreamStateRecord.create(session=str(session_id))
        return row

    def _history_fingerprint(self, session_id: str) -> str:
        rows = list(
            SessionMessageRecord.select()
            .where(SessionMessageRecord.session == str(session_id))
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )
        if not rows:
            self._require_session(session_id)
        return _history_fingerprint_from_rows(rows)

    def _require_session(self, session_id: str) -> None:
        if not SessionRecord.select().where(SessionRecord.id == str(session_id)).exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

    def _require_story_memories(
        self,
        session_id: str,
        memory_ids: Sequence[int],
    ) -> None:
        if not memory_ids:
            return
        matched = int(
            SessionStoryMemoryRecord.select()
            .where(
                (SessionStoryMemoryRecord.session == str(session_id))
                & (SessionStoryMemoryRecord.id.in_(memory_ids))
            )
            .count()
        )
        if matched != len(memory_ids):
            raise ValueError("Dream source story memories must belong to the Session")

    def _require_proposal_record(
        self,
        proposal_id: str,
    ) -> SessionDreamProposalRecord:
        row = (
            SessionDreamProposalRecord.select()
            .where(SessionDreamProposalRecord.id == str(proposal_id))
            .first()
        )
        if row is None:
            raise FileNotFoundError(f"Dream proposal not found: {proposal_id}")
        return row

    @staticmethod
    def _require_proposal_status(
        proposal: SessionDreamProposalRecord,
        allowed: set[str],
    ) -> None:
        if str(proposal.status) not in allowed:
            raise DreamProposalStateError(
                f"Dream proposal {proposal.id} is {proposal.status}; expected {sorted(allowed)}"
            )

    @staticmethod
    def _update_proposal_status(
        proposal: SessionDreamProposalRecord,
        status: str,
        *,
        finished: bool,
    ) -> None:
        proposal.status = status
        if finished:
            proposal.finished_at = SQL("CURRENT_TIMESTAMP")
        proposal.updated_at = SQL("CURRENT_TIMESTAMP")
        proposal.version = int(proposal.version) + 1
        proposal.save()


def _to_state(row: SessionDreamStateRecord) -> models.DreamState:
    return models.DreamState(
        session_id=str(row.session_id),
        ledger_revision=int(row.ledger_revision),
        messages_manifest_json=str(row.messages_manifest_json or "{}"),
        story_memories_manifest_json=str(row.story_memories_manifest_json or "{}"),
        summary_batches_manifest_json=str(row.summary_batches_manifest_json or "{}"),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _persistent_memory(
    row: SessionPersistentMemoryRecord,
) -> models.PersistentMemory:
    return models.PersistentMemory(
        id=str(row.id),
        session_id=str(row.session_id),
        dedupe_key=str(row.dedupe_key),
        lifecycle=str(row.lifecycle),
        current_revision_number=int(row.current_revision_number),
        superseded_by_memory_id=(
            str(row.superseded_by_memory_id)
            if row.superseded_by_memory_id is not None
            else None
        ),
        created_from_proposal_id=(
            str(row.created_from_proposal_id)
            if row.created_from_proposal_id is not None
            else None
        ),
        version=int(row.version),
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _persistent_evidence(
    row: SessionPersistentMemoryEvidenceRecord,
) -> models.PersistentMemoryEvidence:
    return models.PersistentMemoryEvidence(
        id=int(row.id),
        revision_id=int(row.revision_id),
        message_id=int(row.message_id),
        turn_id=int(row.turn_id),
        message_version=int(row.message_version),
        content_hash=str(row.content_hash),
        created_at=str(row.created_at),
    )


def _persistent_revision(
    row: SessionPersistentMemoryRevisionRecord,
    *,
    evidence: tuple[models.PersistentMemoryEvidence, ...],
) -> models.PersistentMemoryRevision:
    return models.PersistentMemoryRevision(
        id=int(row.id),
        memory_id=str(row.memory_id),
        revision_number=int(row.revision_number),
        text=str(row.text),
        memory_kind=str(row.memory_kind),
        epistemic_status=str(row.epistemic_status),
        salience=float(row.salience),
        source_proposal_id=(
            str(row.source_proposal_id)
            if row.source_proposal_id is not None
            else None
        ),
        evidence=evidence,
        created_at=str(row.created_at),
    )


def _evidence_matches_row(
    message: SessionMessageRecord | None,
    evidence: models.PersistentMemoryEvidence,
) -> bool:
    return bool(
        message is not None
        and str(message.role) in _EVIDENCE_ROLES
        and str(message.mode) in _EVIDENCE_MODES
        and int(message.turn_id) == evidence.turn_id
        and int(message.version) == evidence.message_version
        and _content_hash(str(message.content or "")) == evidence.content_hash
    )


def _normalize_evidence(value: models.DreamEvidenceDraft) -> models.DreamEvidenceDraft:
    if not isinstance(value, models.DreamEvidenceDraft):
        raise TypeError("Dream evidence must be DreamEvidenceDraft")
    return models.DreamEvidenceDraft(
        message_id=_positive_int(value.message_id, "message_id"),
        turn_id=_positive_int(value.turn_id, "turn_id"),
        message_version=_positive_int(value.message_version, "message_version"),
        content_hash=_fingerprint(value.content_hash, "content_hash"),
    )


def _history_fingerprint_from_rows(rows: Sequence[SessionMessageRecord]) -> str:
    payload = [
        {
            "id": int(row.id),
            "version": int(row.version),
            "role": str(row.role),
            "mode": str(row.mode),
            "turn_id": int(row.turn_id),
            "seq_in_turn": int(row.seq_in_turn),
            "content_hash": _content_hash(str(row.content or "")),
        }
        for row in rows
    ]
    return _json_fingerprint(payload)


def _story_memory_fingerprint_from_rows(
    rows: Sequence[SessionStoryMemoryRecord],
) -> str:
    payload = [
        {
            "id": int(row.id),
            "version": int(row.version),
            "dedupe_key": str(row.dedupe_key),
            "turn_id": int(row.turn_id),
            "source_turn_start": int(row.source_turn_start),
            "source_turn_end": int(row.source_turn_end),
            "text_hash": _content_hash(str(row.text or "")),
        }
        for row in rows
    ]
    return _json_fingerprint(payload)


def _json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _canonical_json_object(
    value: str | Mapping[str, object],
    name: str,
) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} must be a JSON object") from exc
    else:
        decoded = dict(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"{name} must be a JSON object")
    return json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise ValueError(f"Unsupported {name}: {normalized}")
    return normalized


def _fingerprint(value: object, name: str) -> str:
    normalized = str(value or "").strip().lower()
    if _SHA256_RE.fullmatch(normalized) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return normalized


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if normalized <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return normalized


def _positive_ids(values: Iterable[int], name: str) -> tuple[int, ...]:
    normalized = tuple(sorted({_positive_int(value, name) for value in values}))
    return normalized


def _salience(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("salience must be within [0, 1]")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("salience must be within [0, 1]") from exc
    if not 0.0 <= normalized <= 1.0:
        raise ValueError("salience must be within [0, 1]")
    return normalized


def _memory_text(value: object, *, allow_empty: bool) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized and not allow_empty:
        raise ValueError("persistent memory text must not be empty")
    if len(normalized) > models.DREAM_MAX_MEMORY_TEXT_CHARS:
        raise ValueError(
            "persistent memory text must contain at most "
            f"{models.DREAM_MAX_MEMORY_TEXT_CHARS} characters"
        )
    return normalized


def _bounded_text(
    value: object,
    *,
    name: str,
    max_chars: int,
    allow_empty: bool,
) -> str:
    normalized = str(value or "").strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > max_chars:
        raise ValueError(f"{name} must contain at most {max_chars} characters")
    return normalized
