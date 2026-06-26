"""Repository for session records."""

from __future__ import annotations

import secrets
import string

from peewee import JOIN
from peewee import IntegrityError
from peewee import Database

from rpg_data import models
from rpg_data.repositories.records import SessionProfileRecord, SessionRecord, bind_database
from rpg_data.repositories._utils import to_session, update_timestamp


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def create(
        self,
        workspace_id: str,
        story_id: int,
        *,
        session_id: str | None = None,
        title: str = "",
        description: str = "",
        state_json: str = "{}",
        last_story_turn_index: int = 0,
        metadata_json: str = "{}",
    ) -> models.Session:
        created_id = session_id or _new_session_id()
        while True:
            try:
                with self._database.atomic():
                    row = SessionRecord.create(
                        id=created_id,
                        workspace=workspace_id,
                        story=story_id,
                        state_json=state_json,
                        last_story_turn_index=last_story_turn_index,
                    )
                    SessionProfileRecord.create(
                        session=created_id,
                        title=title,
                        description=description,
                        metadata_json=metadata_json,
                    )
                break
            except IntegrityError:
                # 自动生成的短 ID 理论上可能碰撞；显式传入 ID 则应把冲突暴露给调用方。
                if session_id is not None:
                    raise
                created_id = _new_session_id()
        return self.get(created_id) or to_session(row)

    def list(
        self,
        *,
        workspace_id: str | None = None,
        story_id: int | None = None,
    ) -> list[models.Session]:
        query = (
            SessionRecord
            .select(SessionRecord, SessionProfileRecord)
            .join(SessionProfileRecord, JOIN.LEFT_OUTER)
        )
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

    def get(self, session_id: str) -> models.Session | None:
        row = (
            SessionRecord
            .select(SessionRecord, SessionProfileRecord)
            .join(SessionProfileRecord, JOIN.LEFT_OUTER)
            .where(SessionRecord.id == session_id)
            .first()
        )
        return to_session(row) if row is not None else None

    def update_timestamp(self, session_id: str) -> models.Session | None:
        row = update_timestamp(SessionRecord, session_id)
        return to_session(row) if row is not None else None


_SESSION_ID_ALPHABET = string.ascii_lowercase + string.digits
_SESSION_ID_RANDOM_LENGTH = 10


def _new_session_id() -> str:
    # 使用短 ID 作为 Play WebUI 公开路径，同时保持 rpg_core 当前 session_id 字符规则兼容。
    suffix = "".join(secrets.choice(_SESSION_ID_ALPHABET) for _ in range(_SESSION_ID_RANDOM_LENGTH))
    return f"s_{suffix}"
