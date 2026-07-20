"""Business-neutral Dream and Persistent Memory data facade."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from peewee import Database, IntegrityError

from rpg_data import models
from rpg_data.errors import DataConditionalWriteError, DataIntegrityError
from rpg_data.repositories.dream_memory_repo import DreamMemoryRepository
from rpg_data.repositories.story_memory_repo import StoryMemoryRepository
from rpg_data.transaction import DataTransactionMode

__all__ = ["DreamMemoryDataService"]


class DreamMemoryDataService:
    """Expose typed Dream/Persistent CRUD, CAS, snapshots, and transactions."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._records = DreamMemoryRepository(database)
        self._story_memories = StoryMemoryRepository(database)

    @contextmanager
    def transaction(
        self,
        mode: DataTransactionMode = DataTransactionMode.DEFERRED,
    ) -> Iterator[None]:
        with self._database.atomic(mode.value):
            yield

    def require_session(self, session_id: str) -> None:
        if not self._records.session_exists(session_id):
            raise FileNotFoundError(f"Session not found: {session_id}")

    def list_messages(
        self,
        session_id: str,
        *,
        message_ids: Sequence[int] | None = None,
    ) -> tuple[models.SessionMessage, ...]:
        return self._records.list_messages(session_id, message_ids=message_ids)

    def list_story_memories(
        self,
        session_id: str,
    ) -> tuple[models.SessionStoryMemory, ...]:
        return self._records.list_story_memories(session_id)

    def create_proposal(
        self,
        values: models.DreamProposalCreateValues,
    ) -> models.DreamProposal:
        try:
            return self._records.create_proposal(values)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Dream proposal create violated persisted constraints"
            ) from exc

    def get_proposal(self, proposal_id: str) -> models.DreamProposal | None:
        return self._records.get_proposal(proposal_id)

    def list_proposals(self, session_id: str) -> tuple[models.DreamProposal, ...]:
        return self._records.list_proposals(session_id)

    def has_proposal_with_status(self, session_id: str, status: str) -> bool:
        return self._records.has_proposal_with_status(session_id, status)

    def replace_proposal_items(
        self,
        proposal_id: str,
        items: Sequence[models.DreamProposalItemRowValues],
    ) -> None:
        try:
            self._records.replace_proposal_items(proposal_id, items)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Dream proposal item write violated persisted constraints"
            ) from exc

    def update_proposal_items(
        self,
        proposal_id: str,
        items: Sequence[models.DreamProposalItemRowValues],
    ) -> None:
        try:
            changed = self._records.update_proposal_items(proposal_id, items)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Dream proposal item update violated persisted constraints"
            ) from exc
        if changed != len(items):
            raise DataConditionalWriteError(
                "One or more Dream proposal items changed during update"
            )

    def update_proposal(
        self,
        proposal_id: str,
        values: models.DreamProposalRowUpdate,
        *,
        expected_status: str,
        expected_version: int,
    ) -> models.DreamProposal:
        try:
            updated = self._records.update_proposal(
                proposal_id,
                values,
                expected_status=expected_status,
                expected_version=expected_version,
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Dream proposal update violated persisted constraints"
            ) from exc
        if updated is None:
            raise DataConditionalWriteError(
                f"Dream proposal changed during update: {proposal_id}"
            )
        return updated

    def transition_matching_proposals(
        self,
        *,
        expected_status: str,
        status: str,
        error_code: str,
        session_id: str | None = None,
        proposal_id: str | None = None,
    ) -> tuple[models.DreamProposal, ...]:
        try:
            return self._records.transition_matching_proposals(
                expected_status=expected_status,
                status=status,
                error_code=error_code,
                session_id=session_id,
                proposal_id=proposal_id,
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Dream proposal bulk update violated persisted constraints"
            ) from exc

    def get_state(self, session_id: str) -> models.DreamState | None:
        return self._records.get_state(session_id)

    def get_or_create_state(self, session_id: str) -> models.DreamState:
        state = self.get_state(session_id)
        if state is not None:
            return state
        try:
            return self._records.create_state(session_id)
        except IntegrityError as exc:
            state = self.get_state(session_id)
            if state is None:
                raise DataIntegrityError(
                    "Dream state create violated persisted constraints"
                ) from exc
            return state

    def update_state(
        self,
        session_id: str,
        values: models.DreamStateRowValues,
        *,
        expected_version: int,
    ) -> models.DreamState:
        try:
            updated = self._records.update_state(
                session_id,
                values,
                expected_version=expected_version,
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Dream state update violated persisted constraints"
            ) from exc
        if updated is None:
            raise DataConditionalWriteError(
                f"Dream state changed during update: {session_id}"
            )
        return updated

    def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
    ) -> tuple[models.PersistentMemoryBundle, ...]:
        return self._records.list_memories(session_id, lifecycle=lifecycle)

    def get_memory(self, memory_id: str) -> models.PersistentMemoryBundle | None:
        return self._records.get_memory(memory_id)

    def get_memory_by_dedupe_key(
        self,
        session_id: str,
        dedupe_key: str,
    ) -> models.PersistentMemoryBundle | None:
        return self._records.get_memory_by_dedupe_key(session_id, dedupe_key)

    def create_memory(
        self,
        values: models.PersistentMemoryCreateValues,
    ) -> models.PersistentMemory:
        try:
            return self._records.create_memory(values)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Persistent Memory create violated persisted constraints"
            ) from exc

    def update_memory(
        self,
        memory_id: str,
        values: models.PersistentMemoryRowUpdate,
        *,
        expected_version: int,
    ) -> models.PersistentMemory:
        try:
            updated = self._records.update_memory(
                memory_id,
                values,
                expected_version=expected_version,
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Persistent Memory update violated persisted constraints"
            ) from exc
        if updated is None:
            raise DataConditionalWriteError(
                f"Persistent Memory changed during update: {memory_id}"
            )
        return updated

    def create_revision(
        self,
        values: models.PersistentMemoryRevisionCreateValues,
    ) -> models.PersistentMemoryRevision:
        try:
            return self._records.create_revision(values)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Persistent Memory revision write violated persisted constraints"
            ) from exc

    def mark_story_memories_processed(
        self,
        session_id: str,
        memory_ids: Sequence[int],
    ) -> int:
        return self._story_memories.set_dream_processed(
            memory_ids,
            dream_processed=True,
            session_id=session_id,
        )

    def clear(self, session_id: str) -> models.DreamResetResult:
        with self.transaction():
            return self._records.clear(session_id)
