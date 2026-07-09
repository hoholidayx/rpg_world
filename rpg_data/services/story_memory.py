"""Session story memory service backed by rpg_data."""

from __future__ import annotations

import json
from collections.abc import Iterable

from peewee import Database, SQL

from commons.errors import InvalidTurnMetadataError
from rpg_data import models
from rpg_data.repositories._utils import get_or_none, to_session_story_memory
from rpg_data.repositories.records import SessionRecord, SessionStoryMemoryRecord, bind_database

__all__ = ["StoryMemoryService"]


class StoryMemoryService:
    """Manage persisted story-memory details for sessions."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def list(
        self,
        session_id: str,
        *,
        dream_processed: bool | None = None,
    ) -> list[models.SessionStoryMemory]:
        where_clause = SessionStoryMemoryRecord.session == session_id
        if dream_processed is not None:
            where_clause &= SessionStoryMemoryRecord.dream_processed == bool(dream_processed)
        query = (
            SessionStoryMemoryRecord
            .select()
            .where(where_clause)
            .order_by(SessionStoryMemoryRecord.id)
        )
        return [to_session_story_memory(row) for row in query]

    def get(self, memory_id: int) -> models.SessionStoryMemory | None:
        row = get_or_none(SessionStoryMemoryRecord, memory_id)
        return to_session_story_memory(row) if row is not None else None

    def add_detail(
        self,
        session_id: str,
        text: str,
        *,
        turn_id: int,
        dream_processed: bool = False,
        metadata_json: str = "{}",
    ) -> models.SessionStoryMemory:
        normalized_turn_id = _required_positive_int(turn_id, "turn_id")
        row = SessionStoryMemoryRecord.create(
            session=session_id,
            turn_id=normalized_turn_id,
            text=str(text or ""),
            dream_processed=bool(dream_processed),
            metadata_json=str(metadata_json or "{}"),
        )
        return to_session_story_memory(row)

    def set_details(
        self,
        session_id: str,
        details: Iterable[models.SessionStoryMemory | dict[str, object]],
    ) -> list[models.SessionStoryMemory]:
        payloads = [_coerce_detail(detail) for detail in details]
        with self._database.atomic():
            self.clear(session_id)
            return [
                self.add_detail(session_id, **payload)
                for payload in payloads
            ]

    def clear(self, session_id: str) -> int:
        return int(
            SessionStoryMemoryRecord
            .delete()
            .where(SessionStoryMemoryRecord.session == session_id)
            .execute()
        )

    def set_dream_processed(
        self,
        memory_ids: Iterable[int],
        *,
        dream_processed: bool = True,
    ) -> int:
        ids = [int(memory_id) for memory_id in memory_ids]
        if not ids:
            return 0
        return int(
            SessionStoryMemoryRecord
            .update(
                dream_processed=bool(dream_processed),
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(SessionStoryMemoryRecord.id.in_(ids))
            .execute()
        )

    def require_session(self, session_id: str) -> None:
        if not SessionRecord.select().where(SessionRecord.id == session_id).exists():
            raise FileNotFoundError(f"Session not found: {session_id}")


def _coerce_detail(
    detail: models.SessionStoryMemory | dict[str, object],
) -> dict[str, object]:
    if isinstance(detail, models.SessionStoryMemory):
        return {
            "text": detail.text,
            "turn_id": detail.turn_id,
            "dream_processed": detail.dream_processed,
            "metadata_json": detail.metadata_json,
        }

    metadata_json = detail.get("metadata_json", "")
    if not metadata_json and "metadata" in detail:
        metadata_json = json.dumps(detail.get("metadata") or {}, ensure_ascii=False)
    return {
        "text": str(detail.get("text", "") or ""),
        "turn_id": _required_positive_int(detail.get("turn_id"), "turn_id"),
        "dream_processed": bool(detail.get("dream_processed", False)),
        "metadata_json": str(metadata_json or "{}"),
    }


def _required_positive_int(value: object | None, field_name: str) -> int:
    if value is None or value == "" or isinstance(value, bool):
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer") from exc
    if parsed <= 0:
        raise InvalidTurnMetadataError(f"{field_name} must be a positive integer")
    return parsed
