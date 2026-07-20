"""Business-neutral Story Memory data facade."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from peewee import Database, IntegrityError

from rpg_data import models
from rpg_data.errors import DataConditionalWriteError, DataIntegrityError
from rpg_data.repositories.story_memory_repo import StoryMemoryRepository
from rpg_data.transaction import DataTransactionMode

__all__ = ["StoryMemoryDataService"]


class StoryMemoryDataService:
    """Expose typed Story Memory CRUD, Evidence, progress, and transactions."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._records = StoryMemoryRepository(database)

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

    def list(
        self,
        session_id: str,
        *,
        dream_processed: bool | None = None,
    ) -> tuple[models.SessionStoryMemory, ...]:
        return self._records.list(session_id, dream_processed=dream_processed)

    def list_page(
        self,
        session_id: str,
        *,
        page: int,
        page_size: int,
        memory_kind: str | None,
        dream_processed: bool | None,
    ) -> models.SessionStoryMemoryPage:
        if page <= 0:
            raise ValueError("Story Memory page must be positive")
        if page_size <= 0 or page_size > 100:
            raise ValueError("Story Memory page_size must be between 1 and 100")
        return self._records.list_page(
            session_id,
            page=page,
            page_size=page_size,
            memory_kind=memory_kind,
            dream_processed=dream_processed,
        )

    def get(self, memory_id: int) -> models.SessionStoryMemory | None:
        return self._records.get(memory_id)

    def get_by_dedupe_key(
        self,
        session_id: str,
        dedupe_key: str,
    ) -> models.SessionStoryMemory | None:
        return self._records.get_by_dedupe_key(session_id, dedupe_key)

    def create(
        self,
        session_id: str,
        values: models.StoryMemoryRowValues,
    ) -> models.SessionStoryMemory:
        try:
            return self._records.create(session_id, values)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Story Memory create violated persisted constraints"
            ) from exc

    def update(
        self,
        memory_id: int,
        values: models.StoryMemoryRowValues,
        *,
        expected_version: int,
    ) -> models.SessionStoryMemory:
        try:
            updated = self._records.update(
                memory_id,
                values,
                expected_version=expected_version,
            )
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Story Memory update violated persisted constraints"
            ) from exc
        if updated is None:
            raise DataConditionalWriteError(
                f"Story Memory row changed during update: {memory_id}"
            )
        return updated

    def replace_evidence(
        self,
        story_memory_id: int,
        evidence: Sequence[models.MemoryEvidence],
    ) -> None:
        try:
            self._records.replace_evidence(story_memory_id, evidence)
        except IntegrityError as exc:
            raise DataIntegrityError(
                "Story Memory Evidence write violated persisted constraints"
            ) from exc

    def list_source_messages(
        self,
        session_id: str,
        message_ids: Sequence[int],
    ) -> tuple[models.SessionMessage, ...]:
        return self._records.list_source_messages(session_id, message_ids)

    def mark_messages_processed(
        self,
        session_id: str,
        message_ids: Sequence[int],
    ) -> int:
        return self._records.mark_messages_processed(session_id, message_ids)

    def clear(self, session_id: str) -> int:
        return self._records.clear(session_id)

    def set_dream_processed(
        self,
        memory_ids: Sequence[int],
        *,
        dream_processed: bool = True,
        session_id: str | None = None,
    ) -> int:
        return self._records.set_dream_processed(
            memory_ids,
            dream_processed=dream_processed,
            session_id=session_id,
        )
