"""Typed persistence boundary for SessionRoom text-to-speech."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from peewee import Database, IntegrityError, SQL

from rpg_data import models
from rpg_data.repositories.records import (
    SessionMessageRecord,
    SessionRecord,
    TTSAudioPartRecord,
    TTSBlobRecord,
    TTSCacheEntryRecord,
    TTSJobRecord,
    WorkspaceRecord,
    bind_database,
)


@dataclass(frozen=True)
class TTSCompletedPart:
    sha256: str
    byte_size: int
    relative_path: str


class TTSDataService:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def get_message_source(
        self,
        session_id: str,
        message_id: int,
    ) -> models.TTSMessageSource:
        row = (
            SessionMessageRecord
            .select(SessionMessageRecord, SessionRecord, WorkspaceRecord)
            .join(SessionRecord)
            .join(WorkspaceRecord)
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.id == int(message_id))
            )
            .first()
        )
        if row is None:
            raise FileNotFoundError(f"TTS source message not found: {message_id}")
        if row.role != models.MESSAGE_ROLE_ASSISTANT:
            raise ValueError("TTS only supports persisted assistant messages")
        if not str(row.content).strip():
            raise ValueError("TTS source message is empty")
        session = row.session
        workspace = session.workspace
        return models.TTSMessageSource(
            session_id=str(session.id),
            message_id=int(row.id),
            workspace_id=str(workspace.id),
            workspace_root=str(workspace.root_path),
            content=str(row.content),
        )

    def get_workspace_root(self, workspace_id: str) -> str:
        row = WorkspaceRecord.get_or_none(WorkspaceRecord.id == str(workspace_id))
        if row is None:
            raise FileNotFoundError(f"TTS workspace not found: {workspace_id}")
        return str(row.root_path)

    def list_blobs(self, workspace_id: str) -> list[models.TTSBlob]:
        return [
            _to_blob(row)
            for row in (
                TTSBlobRecord
                .select()
                .where(TTSBlobRecord.workspace == str(workspace_id))
                .order_by(TTSBlobRecord.created_at, TTSBlobRecord.id)
            )
        ]

    def invalidate_blob(self, blob_id: str) -> bool:
        row = TTSBlobRecord.get_or_none(TTSBlobRecord.id == str(blob_id))
        if row is None:
            return False
        cache_ids = [
            str(part.cache_entry_id)
            for part in TTSAudioPartRecord.select(TTSAudioPartRecord.cache_entry).where(
                TTSAudioPartRecord.blob == row.id
            )
        ]
        with self._database.atomic():
            if cache_ids:
                (
                    TTSJobRecord
                    .update(
                        status=models.TTS_JOB_STATUS_FAILED,
                        cache_entry=None,
                        error_code="TTS_CACHE_MISSING",
                        error_message="Cached TTS audio is missing or corrupt",
                        finished_at=SQL("CURRENT_TIMESTAMP"),
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                        version=TTSJobRecord.version + 1,
                    )
                    .where(TTSJobRecord.cache_entry.in_(cache_ids))
                    .execute()
                )
                TTSCacheEntryRecord.delete().where(
                    TTSCacheEntryRecord.id.in_(cache_ids)
                ).execute()
            TTSBlobRecord.delete().where(TTSBlobRecord.id == row.id).execute()
        return True

    def invalidate_cache(self, cache_entry_id: str) -> bool:
        row = TTSCacheEntryRecord.get_or_none(
            TTSCacheEntryRecord.id == str(cache_entry_id)
        )
        if row is None:
            return False
        with self._database.atomic():
            (
                TTSJobRecord
                .update(
                    status=models.TTS_JOB_STATUS_FAILED,
                    cache_entry=None,
                    error_code="TTS_CACHE_MISSING",
                    error_message="Cached TTS audio is missing or corrupt",
                    finished_at=SQL("CURRENT_TIMESTAMP"),
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                    version=TTSJobRecord.version + 1,
                )
                .where(TTSJobRecord.cache_entry == row.id)
                .execute()
            )
            TTSCacheEntryRecord.delete().where(
                TTSCacheEntryRecord.id == row.id
            ).execute()
        return True

    def blob_is_referenced(self, blob_id: str) -> bool:
        return bool(
            TTSAudioPartRecord
            .select(TTSAudioPartRecord.id)
            .where(TTSAudioPartRecord.blob == str(blob_id))
            .limit(1)
            .first()
        )

    def create_or_get_job(
        self,
        *,
        session_id: str,
        message_id: int,
        source_fingerprint: str,
        config_fingerprint: str,
        normalization_revision: str,
    ) -> models.TTSJob:
        source = self.get_message_source(session_id, message_id)
        existing = self._job_query(
            session_id=session_id,
            message_id=message_id,
            source_fingerprint=source_fingerprint,
            config_fingerprint=config_fingerprint,
            normalization_revision=normalization_revision,
        ).first()
        if existing is not None:
            return _to_job(existing)
        cache = self._cache_query(
            workspace_id=source.workspace_id,
            source_fingerprint=source_fingerprint,
            config_fingerprint=config_fingerprint,
            normalization_revision=normalization_revision,
        ).first()
        status = (
            models.TTS_JOB_STATUS_SUCCEEDED
            if cache is not None
            else models.TTS_JOB_STATUS_QUEUED
        )
        try:
            row = TTSJobRecord.create(
                id=uuid.uuid4().hex,
                session=session_id,
                message=message_id,
                status=status,
                source_fingerprint=source_fingerprint,
                config_fingerprint=config_fingerprint,
                normalization_revision=normalization_revision,
                cache_entry=cache.id if cache is not None else None,
                finished_at=SQL("CURRENT_TIMESTAMP") if cache is not None else None,
            )
            row = TTSJobRecord.get_by_id(row.id)
        except IntegrityError:
            row = self._job_query(
                session_id=session_id,
                message_id=message_id,
                source_fingerprint=source_fingerprint,
                config_fingerprint=config_fingerprint,
                normalization_revision=normalization_revision,
            ).get()
        return _to_job(row)

    def get_job(self, session_id: str, job_id: str) -> models.TTSJob | None:
        row = TTSJobRecord.get_or_none(
            (TTSJobRecord.id == str(job_id))
            & (TTSJobRecord.session == str(session_id))
        )
        return _to_job(row) if row is not None else None

    def get_job_for_worker(self, job_id: str) -> models.TTSJob | None:
        row = TTSJobRecord.get_or_none(TTSJobRecord.id == str(job_id))
        return _to_job(row) if row is not None else None

    def claim_next_job(self) -> models.TTSJob | None:
        with self._database.atomic():
            row = (
                TTSJobRecord
                .select()
                .where(TTSJobRecord.status == models.TTS_JOB_STATUS_QUEUED)
                .order_by(TTSJobRecord.created_at, TTSJobRecord.id)
                .first()
            )
            if row is None:
                return None
            updated = (
                TTSJobRecord
                .update(
                    status=models.TTS_JOB_STATUS_RUNNING,
                    started_at=SQL("CURRENT_TIMESTAMP"),
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                    version=TTSJobRecord.version + 1,
                )
                .where(
                    (TTSJobRecord.id == row.id)
                    & (TTSJobRecord.status == models.TTS_JOB_STATUS_QUEUED)
                )
                .execute()
            )
            if updated != 1:
                return None
        return self.get_job_for_worker(str(row.id))

    def retry_job(self, session_id: str, job_id: str) -> models.TTSJob | None:
        updated = (
            TTSJobRecord
            .update(
                status=models.TTS_JOB_STATUS_QUEUED,
                error_code="",
                error_message="",
                started_at=None,
                finished_at=None,
                updated_at=SQL("CURRENT_TIMESTAMP"),
                version=TTSJobRecord.version + 1,
            )
            .where(
                (TTSJobRecord.id == str(job_id))
                & (TTSJobRecord.session == str(session_id))
                & (TTSJobRecord.status.in_([
                    models.TTS_JOB_STATUS_FAILED,
                    models.TTS_JOB_STATUS_INTERRUPTED,
                ]))
            )
            .execute()
        )
        if updated != 1:
            return self.get_job(session_id, job_id)
        return self.get_job(session_id, job_id)

    def interrupt_active_jobs(self) -> int:
        return int(
            TTSJobRecord
            .update(
                status=models.TTS_JOB_STATUS_INTERRUPTED,
                error_code="TTS_JOB_INTERRUPTED",
                error_message="TTS service stopped while the job was running",
                finished_at=SQL("CURRENT_TIMESTAMP"),
                updated_at=SQL("CURRENT_TIMESTAMP"),
                version=TTSJobRecord.version + 1,
            )
            .where(TTSJobRecord.status == models.TTS_JOB_STATUS_RUNNING)
            .execute()
        )

    def mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.TTSJob | None:
        (
            TTSJobRecord
            .update(
                status=models.TTS_JOB_STATUS_FAILED,
                error_code=str(error_code),
                error_message=str(error_message),
                finished_at=SQL("CURRENT_TIMESTAMP"),
                updated_at=SQL("CURRENT_TIMESTAMP"),
                version=TTSJobRecord.version + 1,
            )
            .where(
                (TTSJobRecord.id == str(job_id))
                & (TTSJobRecord.status == models.TTS_JOB_STATUS_RUNNING)
            )
            .execute()
        )
        return self.get_job_for_worker(job_id)

    def complete_job(
        self,
        job_id: str,
        parts: tuple[TTSCompletedPart, ...],
    ) -> models.TTSJob | None:
        job = self.get_job_for_worker(job_id)
        if job is None or job.status != models.TTS_JOB_STATUS_RUNNING:
            return job
        source = self.get_message_source(job.session_id, job.message_id)
        with self._database.atomic():
            cache = self._cache_query(
                workspace_id=source.workspace_id,
                source_fingerprint=job.source_fingerprint,
                config_fingerprint=job.config_fingerprint,
                normalization_revision=job.normalization_revision,
            ).first()
            if cache is None:
                cache, cache_created = TTSCacheEntryRecord.get_or_create(
                    workspace=source.workspace_id,
                    source_fingerprint=job.source_fingerprint,
                    config_fingerprint=job.config_fingerprint,
                    normalization_revision=job.normalization_revision,
                    defaults={
                        "id": uuid.uuid4().hex,
                        "part_count": len(parts),
                    },
                )
                if cache_created:
                    for index, part in enumerate(parts):
                        blob, _blob_created = TTSBlobRecord.get_or_create(
                            workspace=source.workspace_id,
                            sha256=part.sha256,
                            defaults={
                                "id": uuid.uuid4().hex,
                                "mime_type": "audio/mpeg",
                                "byte_size": part.byte_size,
                                "relative_path": part.relative_path,
                            },
                        )
                        TTSAudioPartRecord.create(
                            id=uuid.uuid4().hex,
                            cache_entry=cache.id,
                            blob=blob.id,
                            part_index=index,
                        )
            (
                TTSJobRecord
                .update(
                    status=models.TTS_JOB_STATUS_SUCCEEDED,
                    cache_entry=cache.id,
                    error_code="",
                    error_message="",
                    finished_at=SQL("CURRENT_TIMESTAMP"),
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                    version=TTSJobRecord.version + 1,
                )
                .where(
                    (TTSJobRecord.id == job.id)
                    & (TTSJobRecord.status == models.TTS_JOB_STATUS_RUNNING)
                )
                .execute()
            )
        return self.get_job_for_worker(job.id)

    def list_parts(
        self,
        session_id: str,
        job_id: str,
    ) -> list[tuple[models.TTSAudioPart, models.TTSBlob]]:
        job = self.get_job(session_id, job_id)
        if job is None or job.status != models.TTS_JOB_STATUS_SUCCEEDED or not job.cache_entry_id:
            return []
        rows = (
            TTSAudioPartRecord
            .select(TTSAudioPartRecord, TTSBlobRecord)
            .join(TTSBlobRecord)
            .where(TTSAudioPartRecord.cache_entry == job.cache_entry_id)
            .order_by(TTSAudioPartRecord.part_index)
        )
        return [(_to_part(row), _to_blob(row.blob)) for row in rows]

    def _job_query(
        self,
        *,
        session_id: str,
        message_id: int,
        source_fingerprint: str,
        config_fingerprint: str,
        normalization_revision: str,
    ):  # noqa: ANN202
        return TTSJobRecord.select().where(
            (TTSJobRecord.session == session_id)
            & (TTSJobRecord.message == message_id)
            & (TTSJobRecord.source_fingerprint == source_fingerprint)
            & (TTSJobRecord.config_fingerprint == config_fingerprint)
            & (TTSJobRecord.normalization_revision == normalization_revision)
        )

    def _cache_query(
        self,
        *,
        workspace_id: str,
        source_fingerprint: str,
        config_fingerprint: str,
        normalization_revision: str,
    ):  # noqa: ANN202
        return TTSCacheEntryRecord.select().where(
            (TTSCacheEntryRecord.workspace == workspace_id)
            & (TTSCacheEntryRecord.source_fingerprint == source_fingerprint)
            & (TTSCacheEntryRecord.config_fingerprint == config_fingerprint)
            & (TTSCacheEntryRecord.normalization_revision == normalization_revision)
        )


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _to_job(row: TTSJobRecord) -> models.TTSJob:
    return models.TTSJob(
        id=str(row.id),
        session_id=str(row.session_id),
        message_id=int(row.message_id),
        status=str(row.status),
        source_fingerprint=str(row.source_fingerprint),
        config_fingerprint=str(row.config_fingerprint),
        normalization_revision=str(row.normalization_revision),
        cache_entry_id=str(row.cache_entry_id) if row.cache_entry_id else None,
        error_code=str(row.error_code or ""),
        error_message=str(row.error_message or ""),
        started_at=_text(row.started_at),
        finished_at=_text(row.finished_at),
        version=int(row.version),
        created_at=_text(row.created_at),
        updated_at=_text(row.updated_at),
    )


def _to_part(row: TTSAudioPartRecord) -> models.TTSAudioPart:
    return models.TTSAudioPart(
        id=str(row.id),
        cache_entry_id=str(row.cache_entry_id),
        blob_id=str(row.blob_id),
        part_index=int(row.part_index),
        created_at=_text(row.created_at),
    )


def _to_blob(row: TTSBlobRecord) -> models.TTSBlob:
    return models.TTSBlob(
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        sha256=str(row.sha256),
        mime_type=str(row.mime_type),
        byte_size=int(row.byte_size),
        relative_path=str(row.relative_path),
        created_at=_text(row.created_at),
    )
