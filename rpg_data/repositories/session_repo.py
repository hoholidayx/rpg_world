"""Repository for session records."""

from __future__ import annotations

from peewee import Database

from rpg_data.orm import Session, bind_database
from rpg_data.repositories._utils import get_or_none, update_timestamp


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = bind_database(database)

    def create(
        self,
        workspace_id: str,
        session_key: str,
        *,
        story_id: int | None = None,
        title: str = "",
        state_json: str = "{}",
        last_story_turn_index: int = 0,
        metadata_json: str = "{}",
    ) -> Session:
        return Session.create(
            workspace=workspace_id,
            story=story_id,
            session_key=session_key,
            title=title,
            state_json=state_json,
            last_story_turn_index=last_story_turn_index,
            metadata_json=metadata_json,
        )

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[Session]:
        query = Session.select()
        if workspace_id is not None:
            query = query.where(Session.workspace == workspace_id)
        if story_id is not None:
            query = query.where(Session.story == story_id)
        return list(query.order_by(Session.created_at, Session.id))

    def get(self, session_id: int) -> Session | None:
        return get_or_none(Session, session_id)

    def update_timestamp(self, session_id: int) -> Session | None:
        return update_timestamp(Session, session_id)

