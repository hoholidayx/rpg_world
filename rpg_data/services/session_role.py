"""Typed persistence facade for Session player-role data."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from peewee import Database

from rpg_data import models
from rpg_data.repositories._utils import to_story_opening
from rpg_data.repositories.records import (
    CharacterRecord,
    StoryCharacterRecord,
    StoryOpeningRecord,
    bind_database,
)
from rpg_data.repositories.session_repo import SessionRepository

__all__ = ["SessionRoleDataService"]


class SessionRoleDataService:
    """Expose role-related reads and explicit Session profile writes."""

    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)
        self._sessions = SessionRepository(database)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._database.atomic():
            yield

    def get_session(self, session_id: str) -> models.Session | None:
        return self._sessions.get(str(session_id))

    def list_character_mounts(
        self,
        session_id: str,
    ) -> list[models.SessionCharacterMount]:
        session = self._require_session(session_id)
        rows = (
            StoryCharacterRecord
            .select(StoryCharacterRecord, CharacterRecord)
            .join(CharacterRecord)
            .where(
                (StoryCharacterRecord.workspace == session.workspace_id)
                & (StoryCharacterRecord.story == session.story_id)
            )
            .order_by(StoryCharacterRecord.sort_order, StoryCharacterRecord.id)
        )
        return [
            models.SessionCharacterMount(
                workspace_id=str(row.workspace_id),
                story_id=int(row.story_id),
                mount_id=int(row.id),
                character_id=int(row.character_id),
                name=str(row.character.name),
                personality=str(row.character.personality or ""),
                content=str(row.character.content or ""),
                metadata_json=str(row.character.metadata_json or "{}"),
                character_updated_at=str(row.character.updated_at),
            )
            for row in rows
        ]

    def list_story_openings(self, session_id: str) -> list[models.StoryOpening]:
        session = self._require_session(session_id)
        rows = (
            StoryOpeningRecord
            .select()
            .where(StoryOpeningRecord.story == int(session.story_id))
            .order_by(StoryOpeningRecord.sort_order, StoryOpeningRecord.id)
        )
        return [to_story_opening(row) for row in rows]

    def update_player_character(
        self,
        session_id: str,
        *,
        player_character_id: int,
        player_character_snapshot_json: str,
    ) -> models.Session | None:
        return self._sessions.update_player_character(
            str(session_id),
            player_character_id=int(player_character_id),
            player_character_snapshot_json=str(player_character_snapshot_json),
        )

    def update_player_character_and_opening(
        self,
        session_id: str,
        *,
        player_character_id: int,
        player_character_snapshot_json: str,
        story_opening_id: int | None,
    ) -> models.Session | None:
        return self._sessions.update_player_character_and_opening(
            str(session_id),
            player_character_id=int(player_character_id),
            player_character_snapshot_json=str(player_character_snapshot_json),
            story_opening_id=(
                int(story_opening_id)
                if story_opening_id is not None
                else None
            ),
        )

    def update_story_opening(
        self,
        session_id: str,
        story_opening_id: int | None,
    ) -> models.Session | None:
        return self._sessions.update_story_opening(
            str(session_id),
            int(story_opening_id) if story_opening_id is not None else None,
        )

    def _require_session(self, session_id: str) -> models.Session:
        session = self._sessions.get(str(session_id))
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session
