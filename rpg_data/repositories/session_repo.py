"""Repository for session records."""

from __future__ import annotations

from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import SessionRecord, bind_database
from rpg_data.repositories._utils import get_or_none, to_session, update_timestamp


class SessionRepository:
    def __init__(self, database: Database) -> None:
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        session_key: str,
        *,
        title: str = "",
        state_json: str = "{}",
        last_story_turn_index: int = 0,
        metadata_json: str = "{}",
    ) -> models.Session:
        return to_session(SessionRecord.create(
            workspace=workspace_id,
            story=story_id,
            session_key=session_key,
            title=title,
            state_json=state_json,
            last_story_turn_index=last_story_turn_index,
            metadata_json=metadata_json,
        ))

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[models.Session]:
        query = SessionRecord.select()
        if workspace_id is not None:
            query = query.where(SessionRecord.workspace == workspace_id)
        if story_id is not None:
            query = query.where(SessionRecord.story == story_id)
        return [
            to_session(row)
            for row in query.order_by(
                SessionRecord.created_at,
                SessionRecord.id,
            )
        ]

    def get(self, session_id: int) -> models.Session | None:
        row = get_or_none(SessionRecord, session_id)
        return to_session(row) if row is not None else None

    def get_by_locator(
        self,
        workspace_id: str,
        story_id: int,
        session_key: str,
    ) -> models.Session | None:
        row = (
            SessionRecord.select()
            .where(
                SessionRecord.workspace == workspace_id,
                SessionRecord.story == story_id,
                SessionRecord.session_key == session_key,
            )
            .first()
        )
        return to_session(row) if row is not None else None

    def update_timestamp(self, session_id: int) -> models.Session | None:
        row = update_timestamp(SessionRecord, session_id)
        return to_session(row) if row is not None else None
