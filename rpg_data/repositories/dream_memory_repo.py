"""Row-level persistence for Dream proposals and Persistent Memory."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TypeVar

from peewee import Database, SQL

from rpg_data import models
from rpg_data.repositories._utils import to_session_message
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
    bind_database,
)
from rpg_data.repositories.story_memory_repo import StoryMemoryRepository

_SQLITE_IN_CHUNK_SIZE = 500
_T = TypeVar("_T")


class DreamMemoryRepository:
    """Perform explicit Dream/Persistent row reads and writes without policy."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._story_memories = StoryMemoryRepository(database)
        bind_database(database)

    def session_exists(self, session_id: str) -> bool:
        return bool(
            SessionRecord.select().where(SessionRecord.id == str(session_id)).exists()
        )

    def list_messages(
        self,
        session_id: str,
        *,
        message_ids: Sequence[int] | None = None,
    ) -> tuple[models.SessionMessage, ...]:
        where_clause = SessionMessageRecord.session == str(session_id)
        if message_ids is not None:
            if not message_ids:
                return ()
            where_clause &= SessionMessageRecord.id.in_(message_ids)
        rows = (
            SessionMessageRecord.select()
            .where(where_clause)
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )
        return tuple(to_session_message(row) for row in rows)

    def list_story_memories(
        self,
        session_id: str,
    ) -> tuple[models.SessionStoryMemory, ...]:
        return self._story_memories.list(session_id)

    def create_proposal(
        self,
        values: models.DreamProposalCreateValues,
    ) -> models.DreamProposal:
        SessionDreamProposalRecord.create(
            id=values.id,
            session=values.session_id,
            depth=values.depth,
            scope=values.scope,
            status=values.status,
            history_fingerprint=values.history_fingerprint,
            source_fingerprint=values.source_fingerprint,
            ledger_revision=values.ledger_revision,
            next_messages_manifest_json=values.next_messages_manifest_json,
            next_story_memories_manifest_json=(
                values.next_story_memories_manifest_json
            ),
            next_summary_batches_manifest_json=(
                values.next_summary_batches_manifest_json
            ),
            source_story_memory_ids_json=json.dumps(
                values.source_story_memory_ids,
                separators=(",", ":"),
            ),
        )
        proposal = self.get_proposal(values.id)
        if proposal is None:
            raise RuntimeError("Dream proposal disappeared after creation")
        return proposal

    def get_proposal(self, proposal_id: str) -> models.DreamProposal | None:
        row = (
            SessionDreamProposalRecord.select()
            .where(SessionDreamProposalRecord.id == str(proposal_id))
            .first()
        )
        return self._proposal_rows((row,))[0] if row is not None else None

    def list_proposals(self, session_id: str) -> tuple[models.DreamProposal, ...]:
        rows = tuple(
            SessionDreamProposalRecord.select()
            .where(SessionDreamProposalRecord.session == str(session_id))
            .order_by(
                SessionDreamProposalRecord.created_at.desc(),
                SessionDreamProposalRecord.id.desc(),
            )
        )
        return self._proposal_rows(rows)

    def has_proposal_with_status(self, session_id: str, status: str) -> bool:
        return bool(
            SessionDreamProposalRecord.select()
            .where(
                (SessionDreamProposalRecord.session == str(session_id))
                & (SessionDreamProposalRecord.status == status)
            )
            .exists()
        )

    def replace_proposal_items(
        self,
        proposal_id: str,
        items: Sequence[models.DreamProposalItemRowValues],
    ) -> None:
        SessionDreamProposalItemRecord.delete().where(
            SessionDreamProposalItemRecord.proposal == str(proposal_id)
        ).execute()
        for item in items:
            self._create_proposal_item(proposal_id, item)

    def update_proposal_items(
        self,
        proposal_id: str,
        items: Sequence[models.DreamProposalItemRowValues],
    ) -> int:
        updated = 0
        for item in items:
            changed = (
                SessionDreamProposalItemRecord.update(
                    action=item.action,
                    target_memory=item.target_memory_id,
                    base_revision_number=item.base_revision_number,
                    dedupe_key=item.dedupe_key,
                    selected=item.selected,
                    text=item.text,
                    memory_kind=item.memory_kind,
                    epistemic_status=item.epistemic_status,
                    salience=item.salience,
                    reason=item.reason,
                    sort_order=item.sort_order,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(
                    (SessionDreamProposalItemRecord.id == item.id)
                    & (SessionDreamProposalItemRecord.proposal == str(proposal_id))
                )
                .execute()
            )
            updated += int(changed)
        return updated

    def update_proposal(
        self,
        proposal_id: str,
        values: models.DreamProposalRowUpdate,
        *,
        expected_status: str,
        expected_version: int,
    ) -> models.DreamProposal | None:
        payload: dict[object, object] = {
            SessionDreamProposalRecord.status: values.status,
            SessionDreamProposalRecord.error_code: values.error_code,
            SessionDreamProposalRecord.error_message: values.error_message,
            SessionDreamProposalRecord.version: values.version,
            SessionDreamProposalRecord.updated_at: SQL("CURRENT_TIMESTAMP"),
        }
        if values.set_applied_at:
            payload[SessionDreamProposalRecord.applied_at] = SQL("CURRENT_TIMESTAMP")
        if values.set_rejected_at:
            payload[SessionDreamProposalRecord.rejected_at] = SQL("CURRENT_TIMESTAMP")
        if values.set_finished_at:
            payload[SessionDreamProposalRecord.finished_at] = SQL("CURRENT_TIMESTAMP")
        changed = (
            SessionDreamProposalRecord.update(payload)
            .where(
                (SessionDreamProposalRecord.id == str(proposal_id))
                & (SessionDreamProposalRecord.status == expected_status)
                & (SessionDreamProposalRecord.version == int(expected_version))
            )
            .execute()
        )
        return self.get_proposal(proposal_id) if changed else None

    def transition_matching_proposals(
        self,
        *,
        expected_status: str,
        status: str,
        error_code: str,
        session_id: str | None,
        proposal_id: str | None,
    ) -> tuple[models.DreamProposal, ...]:
        where_clause = SessionDreamProposalRecord.status == expected_status
        if session_id is not None:
            where_clause &= SessionDreamProposalRecord.session == str(session_id)
        if proposal_id is not None:
            where_clause &= SessionDreamProposalRecord.id == str(proposal_id)
        proposal_ids = tuple(
            str(row.id)
            for row in SessionDreamProposalRecord.select(
                SessionDreamProposalRecord.id
            )
            .where(where_clause)
            .order_by(
                SessionDreamProposalRecord.created_at,
                SessionDreamProposalRecord.id,
            )
        )
        if not proposal_ids:
            return ()
        (
            SessionDreamProposalRecord.update(
                status=status,
                error_code=error_code,
                finished_at=SQL("CURRENT_TIMESTAMP"),
                updated_at=SQL("CURRENT_TIMESTAMP"),
                version=SessionDreamProposalRecord.version + 1,
            )
            .where(where_clause)
            .execute()
        )
        proposals: dict[str, models.DreamProposal] = {}
        for offset in range(0, len(proposal_ids), _SQLITE_IN_CHUNK_SIZE):
            chunk = proposal_ids[offset : offset + _SQLITE_IN_CHUNK_SIZE]
            rows = tuple(
                SessionDreamProposalRecord.select().where(
                    SessionDreamProposalRecord.id.in_(chunk)
                )
            )
            proposals.update(
                {item.id: item for item in self._proposal_rows(rows)}
            )
        return tuple(
            proposals[item_id]
            for item_id in proposal_ids
            if item_id in proposals
        )

    def get_state(self, session_id: str) -> models.DreamState | None:
        row = (
            SessionDreamStateRecord.select()
            .where(SessionDreamStateRecord.session == str(session_id))
            .first()
        )
        return _to_state(row) if row is not None else None

    def create_state(self, session_id: str) -> models.DreamState:
        SessionDreamStateRecord.create(session=str(session_id))
        state = self.get_state(session_id)
        if state is None:
            raise RuntimeError("Dream state disappeared after creation")
        return state

    def update_state(
        self,
        session_id: str,
        values: models.DreamStateRowValues,
        *,
        expected_version: int,
    ) -> models.DreamState | None:
        changed = (
            SessionDreamStateRecord.update(
                ledger_revision=values.ledger_revision,
                messages_manifest_json=values.messages_manifest_json,
                story_memories_manifest_json=values.story_memories_manifest_json,
                summary_batches_manifest_json=values.summary_batches_manifest_json,
                version=values.version,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionDreamStateRecord.session == str(session_id))
                & (SessionDreamStateRecord.version == int(expected_version))
            )
            .execute()
        )
        return self.get_state(session_id) if changed else None

    def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
    ) -> tuple[models.PersistentMemoryBundle, ...]:
        where_clause = SessionPersistentMemoryRecord.session == str(session_id)
        if lifecycle is not None:
            where_clause &= SessionPersistentMemoryRecord.lifecycle == lifecycle
        rows = tuple(
            SessionPersistentMemoryRecord.select()
            .where(where_clause)
            .order_by(
                SessionPersistentMemoryRecord.created_at,
                SessionPersistentMemoryRecord.id,
            )
        )
        return self._memory_bundles(rows)

    def get_memory(self, memory_id: str) -> models.PersistentMemoryBundle | None:
        row = (
            SessionPersistentMemoryRecord.select()
            .where(SessionPersistentMemoryRecord.id == str(memory_id))
            .first()
        )
        if row is None:
            return None
        return self._memory_bundles((row,))[0]

    def get_memory_by_dedupe_key(
        self,
        session_id: str,
        dedupe_key: str,
    ) -> models.PersistentMemoryBundle | None:
        row = (
            SessionPersistentMemoryRecord.select()
            .where(
                (SessionPersistentMemoryRecord.session == str(session_id))
                & (SessionPersistentMemoryRecord.dedupe_key == dedupe_key)
            )
            .first()
        )
        if row is None:
            return None
        return self._memory_bundles((row,))[0]

    def create_memory(
        self,
        values: models.PersistentMemoryCreateValues,
    ) -> models.PersistentMemory:
        SessionPersistentMemoryRecord.create(
            id=values.id,
            session=values.session_id,
            dedupe_key=values.dedupe_key,
            lifecycle=values.lifecycle,
            current_revision_number=values.current_revision_number,
            superseded_by_memory=values.superseded_by_memory_id,
            created_from_proposal=values.created_from_proposal_id,
        )
        row = (
            SessionPersistentMemoryRecord.select()
            .where(SessionPersistentMemoryRecord.id == values.id)
            .first()
        )
        if row is None:
            raise RuntimeError("Persistent Memory row disappeared after creation")
        return _persistent_memory(row)

    def update_memory(
        self,
        memory_id: str,
        values: models.PersistentMemoryRowUpdate,
        *,
        expected_version: int,
    ) -> models.PersistentMemory | None:
        changed = (
            SessionPersistentMemoryRecord.update(
                lifecycle=values.lifecycle,
                current_revision_number=values.current_revision_number,
                superseded_by_memory=values.superseded_by_memory_id,
                version=values.version,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionPersistentMemoryRecord.id == str(memory_id))
                & (SessionPersistentMemoryRecord.version == int(expected_version))
            )
            .execute()
        )
        if not changed:
            return None
        bundle = self.get_memory(memory_id)
        return bundle.memory if bundle is not None else None

    def create_revision(
        self,
        values: models.PersistentMemoryRevisionCreateValues,
    ) -> models.PersistentMemoryRevision:
        row = SessionPersistentMemoryRevisionRecord.create(
            memory=values.memory_id,
            revision_number=values.revision_number,
            text=values.text,
            memory_kind=values.memory_kind,
            epistemic_status=values.epistemic_status,
            salience=values.salience,
            source_proposal=values.source_proposal_id,
        )
        for evidence in values.evidence:
            SessionPersistentMemoryEvidenceRecord.create(
                revision=int(row.id),
                message_id=evidence.message_id,
                turn_id=evidence.turn_id,
                message_version=evidence.message_version,
                content_hash=evidence.content_hash,
            )
        persisted = (
            SessionPersistentMemoryRevisionRecord.select()
            .where(SessionPersistentMemoryRevisionRecord.id == int(row.id))
            .get()
        )
        return self._revision_with_evidence(persisted)

    def clear(self, session_id: str) -> models.DreamResetResult:
        memories = int(
            SessionPersistentMemoryRecord.delete()
            .where(SessionPersistentMemoryRecord.session == str(session_id))
            .execute()
        )
        proposals = int(
            SessionDreamProposalRecord.delete()
            .where(SessionDreamProposalRecord.session == str(session_id))
            .execute()
        )
        states = int(
            SessionDreamStateRecord.delete()
            .where(SessionDreamStateRecord.session == str(session_id))
            .execute()
        )
        return models.DreamResetResult(
            session_id=str(session_id),
            memories_cleared=memories,
            proposals_cleared=proposals,
            states_cleared=states,
        )

    def _create_proposal_item(
        self,
        proposal_id: str,
        item: models.DreamProposalItemRowValues,
    ) -> None:
        SessionDreamProposalItemRecord.create(
            id=item.id,
            proposal=str(proposal_id),
            action=item.action,
            target_memory=item.target_memory_id,
            base_revision_number=item.base_revision_number,
            dedupe_key=item.dedupe_key,
            selected=item.selected,
            text=item.text,
            memory_kind=item.memory_kind,
            epistemic_status=item.epistemic_status,
            salience=item.salience,
            reason=item.reason,
            sort_order=item.sort_order,
        )
        for evidence in item.evidence:
            SessionDreamProposalItemEvidenceRecord.create(
                proposal_item=item.id,
                message_id=evidence.message_id,
                turn_id=evidence.turn_id,
                message_version=evidence.message_version,
                content_hash=evidence.content_hash,
            )

    def _proposal_rows(
        self,
        rows: Sequence[SessionDreamProposalRecord],
    ) -> tuple[models.DreamProposal, ...]:
        if not rows:
            return ()
        proposal_ids = tuple(str(row.id) for row in rows)
        item_rows: list[SessionDreamProposalItemRecord] = []
        for chunk in _chunks(proposal_ids):
            item_rows.extend(
                SessionDreamProposalItemRecord.select()
                .where(SessionDreamProposalItemRecord.proposal.in_(chunk))
                .order_by(
                    SessionDreamProposalItemRecord.proposal,
                    SessionDreamProposalItemRecord.sort_order,
                    SessionDreamProposalItemRecord.id,
                )
            )
        evidence_by_item: dict[str, list[models.DreamProposalItemEvidence]] = {}
        item_ids = tuple(str(row.id) for row in item_rows)
        for chunk in _chunks(item_ids):
            evidence_rows = (
                SessionDreamProposalItemEvidenceRecord.select()
                .where(
                    SessionDreamProposalItemEvidenceRecord.proposal_item.in_(chunk)
                )
                .order_by(
                    SessionDreamProposalItemEvidenceRecord.proposal_item,
                    SessionDreamProposalItemEvidenceRecord.turn_id,
                    SessionDreamProposalItemEvidenceRecord.message_id,
                )
            )
            for evidence in evidence_rows:
                evidence_by_item.setdefault(
                    str(evidence.proposal_item_id),
                    [],
                ).append(_proposal_item_evidence(evidence))
        items_by_proposal: dict[str, list[models.DreamProposalItem]] = {}
        for item in item_rows:
            items_by_proposal.setdefault(str(item.proposal_id), []).append(
                self._to_item(
                    item,
                    evidence=tuple(evidence_by_item.get(str(item.id), ())),
                )
            )
        return tuple(
            self._to_proposal(
                row,
                items=tuple(items_by_proposal.get(str(row.id), ())),
            )
            for row in rows
        )

    def _to_proposal(
        self,
        row: SessionDreamProposalRecord,
        *,
        items: tuple[models.DreamProposalItem, ...],
    ) -> models.DreamProposal:
        try:
            raw_ids = json.loads(str(row.source_story_memory_ids_json or "[]"))
        except json.JSONDecodeError:
            raw_ids = []
        source_ids = (
            tuple(
                int(value)
                for value in raw_ids
                if isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
            )
            if isinstance(raw_ids, list)
            else ()
        )
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
        *,
        evidence: tuple[models.DreamProposalItemEvidence, ...],
    ) -> models.DreamProposalItem:
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
            evidence=evidence,
            created_at=str(row.created_at),
            updated_at=str(row.updated_at),
        )

    def _memory_bundles(
        self,
        memory_rows: Sequence[SessionPersistentMemoryRecord],
    ) -> tuple[models.PersistentMemoryBundle, ...]:
        if not memory_rows:
            return ()
        memory_ids = tuple(str(row.id) for row in memory_rows)
        revision_rows: list[SessionPersistentMemoryRevisionRecord] = []
        for chunk in _chunks(memory_ids):
            revision_rows.extend(
                SessionPersistentMemoryRevisionRecord.select()
                .where(SessionPersistentMemoryRevisionRecord.memory.in_(chunk))
                .order_by(
                    SessionPersistentMemoryRevisionRecord.memory,
                    SessionPersistentMemoryRevisionRecord.revision_number,
                )
            )
        revision_ids = tuple(int(row.id) for row in revision_rows)
        evidence_by_revision: dict[int, list[models.PersistentMemoryEvidence]] = {}
        for chunk in _chunks(revision_ids):
            evidence_rows = (
                SessionPersistentMemoryEvidenceRecord.select()
                .where(SessionPersistentMemoryEvidenceRecord.revision.in_(chunk))
                .order_by(
                    SessionPersistentMemoryEvidenceRecord.revision,
                    SessionPersistentMemoryEvidenceRecord.turn_id,
                    SessionPersistentMemoryEvidenceRecord.message_id,
                )
            )
            for row in evidence_rows:
                evidence_by_revision.setdefault(int(row.revision_id), []).append(
                    _persistent_evidence(row)
                )
        revisions_by_memory: dict[str, list[models.PersistentMemoryRevision]] = {}
        for row in revision_rows:
            revisions_by_memory.setdefault(str(row.memory_id), []).append(
                _persistent_revision(
                    row,
                    evidence=tuple(evidence_by_revision.get(int(row.id), ())),
                )
            )
        bundles: list[models.PersistentMemoryBundle] = []
        for row in memory_rows:
            revisions = tuple(revisions_by_memory.get(str(row.id), ()))
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
                    f"Persistent Memory current revision is missing: {row.id}"
                )
            bundles.append(
                models.PersistentMemoryBundle(
                    memory=_persistent_memory(row),
                    current_revision=current,
                    revisions=revisions,
                )
            )
        return tuple(bundles)

    def _revision_with_evidence(
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
        return _persistent_revision(
            row,
            evidence=tuple(_persistent_evidence(item) for item in evidence_rows),
        )


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


def _proposal_item_evidence(
    row: SessionDreamProposalItemEvidenceRecord,
) -> models.DreamProposalItemEvidence:
    return models.DreamProposalItemEvidence(
        id=int(row.id),
        proposal_item_id=str(row.proposal_item_id),
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


def _chunks(values: Sequence[_T]) -> tuple[Sequence[_T], ...]:
    return tuple(
        values[offset : offset + _SQLITE_IN_CHUNK_SIZE]
        for offset in range(0, len(values), _SQLITE_IN_CHUNK_SIZE)
    )
