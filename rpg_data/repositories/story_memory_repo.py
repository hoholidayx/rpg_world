"""Typed persistence operations for Session Story Memory rows."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from peewee import Database, SQL, fn

from rpg_data.model import memory as models
from rpg_data.model.session import SessionMessage
from rpg_data.repositories._utils import (
    get_or_none,
    to_memory_evidence,
    to_session_message,
    to_session_story_memory,
)
from rpg_data.repositories.records import (
    SessionMessageRecord,
    SessionRecord,
    SessionStoryMemoryEvidenceRecord,
    SessionStoryMemoryRecord,
    bind_database,
)


class StoryMemoryRepository:
    """Perform row-level Story Memory CRUD without domain merge policy."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def session_exists(self, session_id: str) -> bool:
        return bool(
            SessionRecord.select().where(SessionRecord.id == str(session_id)).exists()
        )

    def list(
        self,
        session_id: str,
        *,
        dream_processed: bool | None = None,
    ) -> tuple[models.SessionStoryMemory, ...]:
        where_clause = SessionStoryMemoryRecord.session == str(session_id)
        if dream_processed is not None:
            where_clause &= (
                SessionStoryMemoryRecord.dream_processed == bool(dream_processed)
            )
        rows = tuple(
            SessionStoryMemoryRecord.select()
            .where(where_clause)
            .order_by(SessionStoryMemoryRecord.id)
        )
        return self._to_story_memories(rows)

    def list_page(
        self,
        session_id: str,
        *,
        page: int,
        page_size: int,
        memory_kind: str | None,
        dream_processed: bool | None,
    ) -> models.SessionStoryMemoryPage:
        session_clause = SessionStoryMemoryRecord.session == str(session_id)
        filtered_clause = session_clause
        if memory_kind:
            filtered_clause &= SessionStoryMemoryRecord.memory_kind == memory_kind
        if dream_processed is not None:
            filtered_clause &= (
                SessionStoryMemoryRecord.dream_processed == bool(dream_processed)
            )

        filtered_query = SessionStoryMemoryRecord.select().where(filtered_clause)
        total = filtered_query.count()
        rows = tuple(
            filtered_query.order_by(
                SessionStoryMemoryRecord.updated_at.desc(),
                SessionStoryMemoryRecord.id.desc(),
            ).paginate(page, page_size)
        )
        total_facts = SessionStoryMemoryRecord.select().where(session_clause).count()
        dream_processed_facts = (
            SessionStoryMemoryRecord.select()
            .where(session_clause & SessionStoryMemoryRecord.dream_processed)
            .count()
        )
        latest_updated_at = (
            SessionStoryMemoryRecord.select(fn.MAX(SessionStoryMemoryRecord.updated_at))
            .where(session_clause)
            .scalar()
        )
        return models.SessionStoryMemoryPage(
            items=self._to_story_memories(rows),
            page=page,
            page_size=page_size,
            total=total,
            stats=models.SessionStoryMemoryStats(
                total_facts=total_facts,
                dream_processed_facts=dream_processed_facts,
                pending_dream_facts=total_facts - dream_processed_facts,
                latest_updated_at=str(latest_updated_at or ""),
            ),
        )

    def get(self, memory_id: int) -> models.SessionStoryMemory | None:
        row = get_or_none(SessionStoryMemoryRecord, int(memory_id))
        return self._to_story_memory(row) if row is not None else None

    def get_by_dedupe_key(
        self,
        session_id: str,
        dedupe_key: str,
    ) -> models.SessionStoryMemory | None:
        row = (
            SessionStoryMemoryRecord.select()
            .where(
                (SessionStoryMemoryRecord.session == str(session_id))
                & (SessionStoryMemoryRecord.dedupe_key == dedupe_key)
            )
            .first()
        )
        return self._to_story_memory(row) if row is not None else None

    def create(
        self,
        session_id: str,
        values: models.StoryMemoryRowValues,
    ) -> models.SessionStoryMemory:
        row = SessionStoryMemoryRecord.create(
            session=str(session_id),
            **_row_payload(values),
        )
        created = self.get(int(row.id))
        if created is None:
            raise RuntimeError("Story Memory row disappeared after creation")
        return created

    def update(
        self,
        memory_id: int,
        values: models.StoryMemoryRowValues,
        *,
        expected_version: int,
    ) -> models.SessionStoryMemory | None:
        changed = (
            SessionStoryMemoryRecord.update(
                **_row_payload(values),
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionStoryMemoryRecord.id == int(memory_id))
                & (SessionStoryMemoryRecord.version == int(expected_version))
            )
            .execute()
        )
        return self.get(memory_id) if changed else None

    def replace_evidence(
        self,
        story_memory_id: int,
        evidence: Sequence[models.MemoryEvidence],
    ) -> None:
        SessionStoryMemoryEvidenceRecord.delete().where(
            SessionStoryMemoryEvidenceRecord.story_memory == int(story_memory_id)
        ).execute()
        for item in evidence:
            SessionStoryMemoryEvidenceRecord.create(
                story_memory=int(story_memory_id),
                message_id=item.message_id,
                turn_id=item.turn_id,
                message_version=item.message_version,
                content_hash=item.content_hash,
                created_at=SQL("CURRENT_TIMESTAMP"),
            )

    def list_source_messages(
        self,
        session_id: str,
        message_ids: Sequence[int],
    ) -> tuple[SessionMessage, ...]:
        if not message_ids:
            return ()
        rows = (
            SessionMessageRecord.select()
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.id.in_(message_ids))
            )
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )
        return tuple(to_session_message(row) for row in rows)

    def mark_messages_processed(
        self,
        session_id: str,
        message_ids: Sequence[int],
    ) -> int:
        if not message_ids:
            return 0
        return int(
            SessionMessageRecord.update(
                story_memory_processed=True,
                story_memory_processed_at=SQL("CURRENT_TIMESTAMP"),
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.id.in_(message_ids))
            )
            .execute()
        )

    def clear(self, session_id: str) -> int:
        return int(
            SessionStoryMemoryRecord.delete()
            .where(SessionStoryMemoryRecord.session == str(session_id))
            .execute()
        )

    def set_dream_processed(
        self,
        memory_ids: Sequence[int],
        *,
        dream_processed: bool,
        session_id: str | None = None,
    ) -> int:
        if not memory_ids:
            return 0
        where_clause = SessionStoryMemoryRecord.id.in_(memory_ids)
        if session_id is not None:
            where_clause &= SessionStoryMemoryRecord.session == str(session_id)
        return int(
            SessionStoryMemoryRecord.update(
                dream_processed=bool(dream_processed),
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(where_clause)
            .execute()
        )

    def _to_story_memory(
        self,
        row: SessionStoryMemoryRecord,
    ) -> models.SessionStoryMemory:
        evidence_rows = (
            SessionStoryMemoryEvidenceRecord.select()
            .where(SessionStoryMemoryEvidenceRecord.story_memory == int(row.id))
            .order_by(
                SessionStoryMemoryEvidenceRecord.turn_id,
                SessionStoryMemoryEvidenceRecord.message_id,
            )
        )
        return to_session_story_memory(
            row,
            evidence=tuple(to_memory_evidence(item) for item in evidence_rows),
        )

    def _to_story_memories(
        self,
        rows: Iterable[SessionStoryMemoryRecord],
    ) -> tuple[models.SessionStoryMemory, ...]:
        items = tuple(rows)
        if not items:
            return ()
        memory_ids = tuple(int(row.id) for row in items)
        evidence_by_memory: dict[int, list[models.MemoryEvidence]] = {}
        evidence_rows = (
            SessionStoryMemoryEvidenceRecord.select()
            .where(SessionStoryMemoryEvidenceRecord.story_memory.in_(memory_ids))
            .order_by(
                SessionStoryMemoryEvidenceRecord.story_memory,
                SessionStoryMemoryEvidenceRecord.turn_id,
                SessionStoryMemoryEvidenceRecord.message_id,
            )
        )
        for evidence_row in evidence_rows:
            evidence_by_memory.setdefault(
                int(evidence_row.story_memory_id),
                [],
            ).append(to_memory_evidence(evidence_row))
        return tuple(
            to_session_story_memory(
                row,
                evidence=tuple(evidence_by_memory.get(int(row.id), ())),
            )
            for row in items
        )


def _row_payload(values: models.StoryMemoryRowValues) -> dict[str, object]:
    return {
        "turn_id": values.turn_id,
        "text": values.text,
        "memory_kind": values.memory_kind,
        "epistemic_status": values.epistemic_status,
        "salience": values.salience,
        "source_turn_start": values.source_turn_start,
        "source_turn_end": values.source_turn_end,
        "dedupe_key": values.dedupe_key,
        "dream_processed": values.dream_processed,
        "metadata_schema_version": values.metadata_schema_version,
        "metadata_json": values.metadata_json,
        "version": values.version,
    }
