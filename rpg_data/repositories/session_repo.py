"""Repository for session records."""

from __future__ import annotations

import secrets
import string

from peewee import JOIN
from peewee import IntegrityError
from peewee import Database
from peewee import SQL

from rpg_data import models
from rpg_data.repositories.records import SessionProfileRecord, SessionRecord, bind_database
from rpg_data.repositories._utils import (
    to_session,
    update_timestamp,
)


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
        player_character_id: int | None = None,
        player_character_snapshot_json: str = "{}",
        metadata_json: str = "{}",
        lifecycle: str = models.SESSION_LIFECYCLE_READY,
    ) -> models.Session:
        if lifecycle not in {
            models.SESSION_LIFECYCLE_PROVISIONING,
            models.SESSION_LIFECYCLE_READY,
        }:
            raise ValueError(f"Unsupported session lifecycle: {lifecycle}")
        created_id = session_id or _new_session_id()
        while True:
            try:
                with self._database.atomic():
                    row = SessionRecord.create(
                        id=created_id,
                        workspace=workspace_id,
                        story=story_id,
                        state_json=state_json,
                        lifecycle=lifecycle,
                    )
                    SessionProfileRecord.create(
                        session=created_id,
                        title=title,
                        description=description,
                        player_character_id=player_character_id,
                        player_character_snapshot_json=player_character_snapshot_json,
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
        lifecycle: str | None = None,
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
        if lifecycle is not None:
            query = query.where(SessionRecord.lifecycle == lifecycle)
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

    def delete(self, session_id: str) -> bool:
        """Delete one session and all database-owned children via FK cascades."""

        return bool(
            SessionRecord.delete()
            .where(SessionRecord.id == str(session_id))
            .execute()
        )

    def delete_ready_without_active_derivation(self, session_id: str) -> bool:
        """Atomically delete a public-ready session only when no job owns it."""

        cursor = self._database.execute_sql(
            """
            DELETE FROM rpg_sessions
            WHERE id = ?
              AND lifecycle = ?
              AND NOT EXISTS (
                    SELECT 1
                    FROM rpg_session_derivation_jobs
                    WHERE status IN (?, ?)
                      AND (source_session_id = ? OR target_session_id = ?)
              )
            """,
            (
                str(session_id),
                models.SESSION_LIFECYCLE_READY,
                models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
                models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
                str(session_id),
                str(session_id),
            ),
        )
        return bool(cursor.rowcount)

    def delete_provisioning_for_derivation(
        self,
        session_id: str,
        job_id: str,
    ) -> bool:
        """Atomically delete only the running job's provisioning target."""

        cursor = self._database.execute_sql(
            """
            DELETE FROM rpg_sessions
            WHERE id = ?
              AND lifecycle = ?
              AND EXISTS (
                    SELECT 1
                    FROM rpg_session_derivation_jobs
                    WHERE id = ?
                      AND target_session_id = ?
                      AND status = ?
              )
            """,
            (
                str(session_id),
                models.SESSION_LIFECYCLE_PROVISIONING,
                str(job_id),
                str(session_id),
                models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
            ),
        )
        return bool(cursor.rowcount)

    def update_timestamp(self, session_id: str) -> models.Session | None:
        row = update_timestamp(SessionRecord, session_id)
        return to_session(row) if row is not None else None

    def set_lifecycle(self, session_id: str, lifecycle: str) -> models.Session | None:
        if lifecycle not in {
            models.SESSION_LIFECYCLE_PROVISIONING,
            models.SESSION_LIFECYCLE_READY,
        }:
            raise ValueError(f"Unsupported session lifecycle: {lifecycle}")
        updated = (
            SessionRecord.update(
                lifecycle=lifecycle,
                version=SessionRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(SessionRecord.id == session_id)
            .execute()
        )
        return self.get(session_id) if updated else None

    def set_main_llm_provider_key(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> models.Session | None:
        with self._database.atomic():
            if not SessionRecord.select().where(SessionRecord.id == session_id).exists():
                return None
            SessionProfileRecord.get_or_create(session=session_id)
            (
                SessionProfileRecord
                .update(
                    main_llm_provider_key=provider_key,
                    version=SessionProfileRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(SessionProfileRecord.session == session_id)
                .execute()
            )
            (
                SessionRecord
                .update(updated_at=SQL("CURRENT_TIMESTAMP"))
                .where(SessionRecord.id == session_id)
                .execute()
            )
        return self.get(session_id)

    def update_player_character(
        self,
        session_id: str,
        *,
        player_character_id: int | None,
        player_character_snapshot_json: str,
    ) -> models.Session | None:
        with self._database.atomic():
            if not SessionRecord.select().where(SessionRecord.id == session_id).exists():
                return None
            SessionProfileRecord.get_or_create(session=session_id)
            (
                SessionProfileRecord
                .update(
                    player_character_id=player_character_id,
                    player_character_snapshot_json=player_character_snapshot_json,
                    version=SessionProfileRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(SessionProfileRecord.session == session_id)
                .execute()
            )
            (
                SessionRecord
                .update(updated_at=SQL("CURRENT_TIMESTAMP"))
                .where(SessionRecord.id == session_id)
                .execute()
            )
        return self.get(session_id)

_SESSION_ID_ALPHABET = string.ascii_lowercase + string.digits
_SESSION_ID_RANDOM_LENGTH = 10


def _new_session_id() -> str:
    # 使用短 ID 作为 Play WebUI 公开路径，同时保持 rpg_core 当前 session_id 字符规则兼容。
    suffix = "".join(secrets.choice(_SESSION_ID_ALPHABET) for _ in range(_SESSION_ID_RANDOM_LENGTH))
    return f"s_{suffix}"
