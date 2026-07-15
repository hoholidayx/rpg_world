"""Typed persistence operations for workspace media and session media state."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database, IntegrityError, SQL

from rpg_data import models
from rpg_data.repositories._utils import (
    to_media_asset,
    to_media_blob,
    to_media_job,
    to_session_media_background,
    to_session_media_gallery_item,
)
from rpg_data.repositories.records import (
    MediaAssetRecord,
    MediaBlobRecord,
    MediaJobRecord,
    SessionMediaBackgroundRecord,
    SessionMediaGalleryItemRecord,
    SessionMessageRecord,
    bind_database,
)

__all__ = ["MediaRepository"]


class MediaRepository:
    def __init__(self, database: Database) -> None:
        self._database = database
        bind_database(database)

    def list_source_turns(self, session_id: str) -> list[models.MediaSourceTurn]:
        rows = (
            SessionMessageRecord
            .select()
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.turn_id > 0)
            )
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )
        grouped: dict[int, list[models.MediaSourceMessage]] = {}
        for row in rows:
            message = _to_source_message(row)
            grouped.setdefault(message.turn_id, []).append(message)
        return [
            models.MediaSourceTurn(turn_id=turn_id, messages=tuple(messages))
            for turn_id, messages in grouped.items()
        ]

    def get_source_turns(
        self,
        session_id: str,
        *,
        start_turn_id: int,
        end_turn_id: int,
    ) -> list[models.MediaSourceTurn]:
        rows = (
            SessionMessageRecord
            .select()
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.turn_id >= int(start_turn_id))
                & (SessionMessageRecord.turn_id <= int(end_turn_id))
            )
            .order_by(
                SessionMessageRecord.turn_id,
                SessionMessageRecord.seq_in_turn,
                SessionMessageRecord.id,
            )
        )
        grouped: dict[int, list[models.MediaSourceMessage]] = {}
        for row in rows:
            message = _to_source_message(row)
            grouped.setdefault(message.turn_id, []).append(message)
        return [
            models.MediaSourceTurn(turn_id=turn_id, messages=tuple(messages))
            for turn_id, messages in grouped.items()
        ]

    def get_blob(self, blob_id: str) -> models.MediaBlob | None:
        row = MediaBlobRecord.get_or_none(MediaBlobRecord.id == str(blob_id))
        return to_media_blob(row) if row is not None else None

    def get_blob_by_hash(
        self,
        workspace_id: str,
        sha256: str,
    ) -> models.MediaBlob | None:
        row = MediaBlobRecord.get_or_none(
            (MediaBlobRecord.workspace == str(workspace_id))
            & (MediaBlobRecord.sha256 == str(sha256))
        )
        return to_media_blob(row) if row is not None else None

    def create_or_get_blob(
        self,
        *,
        blob_id: str,
        workspace_id: str,
        sha256: str,
        canonical_ext: str,
        mime_type: str,
        byte_size: int,
        relative_path: str,
    ) -> tuple[models.MediaBlob, bool]:
        existing = self.get_blob_by_hash(workspace_id, sha256)
        if existing is not None:
            _validate_existing_blob(
                existing,
                canonical_ext=canonical_ext,
                mime_type=mime_type,
                byte_size=byte_size,
                relative_path=relative_path,
            )
            return existing, False
        try:
            row = MediaBlobRecord.create(
                id=str(blob_id),
                workspace=str(workspace_id),
                sha256=str(sha256),
                canonical_ext=str(canonical_ext),
                mime_type=str(mime_type),
                byte_size=int(byte_size),
                relative_path=str(relative_path),
            )
            return to_media_blob(row), True
        except IntegrityError:
            existing = self.get_blob_by_hash(workspace_id, sha256)
            if existing is None:
                raise
            _validate_existing_blob(
                existing,
                canonical_ext=canonical_ext,
                mime_type=mime_type,
                byte_size=byte_size,
                relative_path=relative_path,
            )
            return existing, False

    def get_asset(self, asset_id: str) -> models.MediaAsset | None:
        row = MediaAssetRecord.get_or_none(MediaAssetRecord.id == str(asset_id))
        return to_media_asset(row) if row is not None else None

    def create_asset(
        self,
        *,
        asset_id: str,
        workspace_id: str,
        blob_id: str,
        provider_key: str,
        visual_brief_json: str,
        provider_asset_id: str = "",
        generation_params_json: str = "{}",
        metadata_json: str = "{}",
    ) -> models.MediaAsset:
        row = MediaAssetRecord.create(
            id=str(asset_id),
            workspace=str(workspace_id),
            blob=str(blob_id),
            provider_key=str(provider_key),
            provider_asset_id=str(provider_asset_id),
            visual_brief_json=str(visual_brief_json),
            generation_params_json=str(generation_params_json),
            metadata_json=str(metadata_json),
        )
        return to_media_asset(row)

    def get_job(self, job_id: str) -> models.MediaJob | None:
        row = MediaJobRecord.get_or_none(MediaJobRecord.id == str(job_id))
        return to_media_job(row) if row is not None else None

    def get_session_job(self, session_id: str, job_id: str) -> models.MediaJob | None:
        row = MediaJobRecord.get_or_none(
            (MediaJobRecord.id == str(job_id))
            & (MediaJobRecord.session == str(session_id))
        )
        return to_media_job(row) if row is not None else None

    def list_jobs(
        self,
        session_id: str,
        *,
        statuses: Iterable[str] | None = None,
    ) -> list[models.MediaJob]:
        query = MediaJobRecord.select().where(
            MediaJobRecord.session == str(session_id)
        )
        normalized_statuses = tuple(str(status) for status in statuses or ())
        if normalized_statuses:
            query = query.where(MediaJobRecord.status.in_(normalized_statuses))
        return [
            to_media_job(row)
            for row in query.order_by(MediaJobRecord.created_at.desc(), MediaJobRecord.id.desc())
        ]

    def create_job(
        self,
        *,
        job_id: str,
        session_id: str,
        provider_key: str,
        source_start_turn_id: int,
        source_end_turn_id: int,
        source_fingerprint: str,
        source_snapshot_json: str,
        visual_brief_json: str,
        generation_params_json: str = "{}",
        retry_of_job_id: str | None = None,
    ) -> models.MediaJob:
        row = MediaJobRecord.create(
            id=str(job_id),
            session=str(session_id),
            provider_key=str(provider_key),
            status=models.MEDIA_JOB_STATUS_QUEUED,
            source_start_turn_id=int(source_start_turn_id),
            source_end_turn_id=int(source_end_turn_id),
            source_fingerprint=str(source_fingerprint),
            source_snapshot_json=str(source_snapshot_json),
            visual_brief_json=str(visual_brief_json),
            generation_params_json=str(generation_params_json),
            retry_of_job=str(retry_of_job_id) if retry_of_job_id else None,
        )
        return to_media_job(row)

    def claim_next_job(self) -> models.MediaJob | None:
        while True:
            candidate = (
                MediaJobRecord
                .select(MediaJobRecord.id)
                .where(MediaJobRecord.status == models.MEDIA_JOB_STATUS_QUEUED)
                .order_by(MediaJobRecord.created_at, MediaJobRecord.id)
                .first()
            )
            if candidate is None:
                return None
            updated = (
                MediaJobRecord
                .update(
                    status=models.MEDIA_JOB_STATUS_RUNNING,
                    started_at=SQL("CURRENT_TIMESTAMP"),
                    error_code="",
                    error_message="",
                    version=MediaJobRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(
                    (MediaJobRecord.id == str(candidate.id))
                    & (MediaJobRecord.status == models.MEDIA_JOB_STATUS_QUEUED)
                )
                .execute()
            )
            if updated:
                return self.get_job(str(candidate.id))

    def request_cancel(self, job_id: str) -> models.MediaJob | None:
        with self._database.atomic():
            row = MediaJobRecord.get_or_none(MediaJobRecord.id == str(job_id))
            if row is None:
                return None
            status = str(row.status)
            if status == models.MEDIA_JOB_STATUS_QUEUED:
                next_status = models.MEDIA_JOB_STATUS_CANCELLED
                finished_at: object = SQL("CURRENT_TIMESTAMP")
            elif status == models.MEDIA_JOB_STATUS_RUNNING:
                next_status = models.MEDIA_JOB_STATUS_CANCELLING
                finished_at = None
            else:
                return to_media_job(row)
            fields: dict[str, object] = {
                "status": next_status,
                "version": MediaJobRecord.version + 1,
                "updated_at": SQL("CURRENT_TIMESTAMP"),
            }
            if finished_at is not None:
                fields["finished_at"] = finished_at
            MediaJobRecord.update(**fields).where(MediaJobRecord.id == str(job_id)).execute()
        return self.get_job(job_id)

    def mark_cancelled(self, job_id: str) -> models.MediaJob | None:
        return self._finish_job(
            job_id,
            allowed_statuses={
                models.MEDIA_JOB_STATUS_RUNNING,
                models.MEDIA_JOB_STATUS_CANCELLING,
            },
            status=models.MEDIA_JOB_STATUS_CANCELLED,
        )

    def mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.MediaJob | None:
        return self._finish_job(
            job_id,
            allowed_statuses={models.MEDIA_JOB_STATUS_RUNNING},
            status=models.MEDIA_JOB_STATUS_FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    def interrupt_active_jobs(self) -> int:
        return int(
            MediaJobRecord
            .update(
                status=models.MEDIA_JOB_STATUS_INTERRUPTED,
                error_code="MEDIA_JOB_INTERRUPTED",
                error_message="Media service restarted before the job finished.",
                finished_at=SQL("CURRENT_TIMESTAMP"),
                version=MediaJobRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                MediaJobRecord.status.in_((
                    models.MEDIA_JOB_STATUS_RUNNING,
                    models.MEDIA_JOB_STATUS_CANCELLING,
                ))
            )
            .execute()
        )

    def complete_job(
        self,
        *,
        job_id: str,
        workspace_id: str,
        blob_id: str,
        sha256: str,
        canonical_ext: str,
        mime_type: str,
        byte_size: int,
        relative_path: str,
        asset_id: str,
        gallery_item_id: str,
        provider_asset_id: str = "",
        metadata_json: str = "{}",
    ) -> tuple[
        models.MediaJob,
        models.MediaAsset,
        models.MediaBlob,
        models.SessionMediaGalleryItem,
        bool,
    ] | None:
        with self._database.atomic():
            job_row = MediaJobRecord.get_or_none(MediaJobRecord.id == str(job_id))
            if job_row is None or str(job_row.status) != models.MEDIA_JOB_STATUS_RUNNING:
                return None
            blob, blob_created = self.create_or_get_blob(
                blob_id=blob_id,
                workspace_id=workspace_id,
                sha256=sha256,
                canonical_ext=canonical_ext,
                mime_type=mime_type,
                byte_size=byte_size,
                relative_path=relative_path,
            )
            asset = self.create_asset(
                asset_id=asset_id,
                workspace_id=workspace_id,
                blob_id=blob.id,
                provider_key=str(job_row.provider_key),
                provider_asset_id=provider_asset_id,
                visual_brief_json=str(job_row.visual_brief_json),
                generation_params_json=str(job_row.generation_params_json or "{}"),
                metadata_json=metadata_json,
            )
            gallery_row = SessionMediaGalleryItemRecord.create(
                id=str(gallery_item_id),
                session=str(job_row.session_id),
                asset=asset.id,
                job=str(job_row.id),
                source_start_turn_id=int(job_row.source_start_turn_id),
                source_end_turn_id=int(job_row.source_end_turn_id),
                source_fingerprint=str(job_row.source_fingerprint),
                source_snapshot_json=str(job_row.source_snapshot_json),
                visual_brief_json=str(job_row.visual_brief_json),
            )
            updated = (
                MediaJobRecord
                .update(
                    status=models.MEDIA_JOB_STATUS_SUCCEEDED,
                    output_asset=asset.id,
                    finished_at=SQL("CURRENT_TIMESTAMP"),
                    error_code="",
                    error_message="",
                    version=MediaJobRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(
                    (MediaJobRecord.id == str(job_id))
                    & (MediaJobRecord.status == models.MEDIA_JOB_STATUS_RUNNING)
                )
                .execute()
            )
            if not updated:
                raise RuntimeError(f"media job changed while completing: {job_id}")
            job = self.get_job(job_id)
            if job is None:
                raise RuntimeError(f"media job disappeared while completing: {job_id}")
            return (
                job,
                asset,
                blob,
                to_session_media_gallery_item(gallery_row),
                blob_created,
            )

    def list_gallery(self, session_id: str) -> list[models.SessionMediaGalleryItem]:
        return [
            to_session_media_gallery_item(row)
            for row in (
                SessionMediaGalleryItemRecord
                .select()
                .where(SessionMediaGalleryItemRecord.session == str(session_id))
                .order_by(
                    SessionMediaGalleryItemRecord.created_at.desc(),
                    SessionMediaGalleryItemRecord.id.desc(),
                )
            )
        ]

    def get_gallery_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.SessionMediaGalleryItem | None:
        row = SessionMediaGalleryItemRecord.get_or_none(
            (SessionMediaGalleryItemRecord.session == str(session_id))
            & (SessionMediaGalleryItemRecord.asset == str(asset_id))
        )
        return to_session_media_gallery_item(row) if row is not None else None

    def get_background(self, session_id: str) -> models.SessionMediaBackground | None:
        row = SessionMediaBackgroundRecord.get_or_none(
            SessionMediaBackgroundRecord.session == str(session_id)
        )
        return to_session_media_background(row) if row is not None else None

    def set_background(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.SessionMediaBackground:
        with self._database.atomic():
            row = SessionMediaBackgroundRecord.get_or_none(
                SessionMediaBackgroundRecord.session == str(session_id)
            )
            if row is None:
                SessionMediaBackgroundRecord.create(
                    session=str(session_id),
                    asset=str(asset_id),
                )
            else:
                (
                    SessionMediaBackgroundRecord
                    .update(
                        asset=str(asset_id),
                        version=SessionMediaBackgroundRecord.version + 1,
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                    )
                    .where(SessionMediaBackgroundRecord.session == str(session_id))
                    .execute()
                )
        background = self.get_background(session_id)
        if background is None:
            raise RuntimeError(f"failed to set session media background: {session_id}")
        return background

    def clear_background(self, session_id: str) -> int:
        return int(
            SessionMediaBackgroundRecord
            .delete()
            .where(SessionMediaBackgroundRecord.session == str(session_id))
            .execute()
        )

    def count_background_references(self, asset_id: str) -> int:
        return int(
            SessionMediaBackgroundRecord
            .select()
            .where(SessionMediaBackgroundRecord.asset == str(asset_id))
            .count()
        )

    def delete_asset(self, asset_id: str) -> models.MediaAssetDeleteResult | None:
        with self._database.atomic():
            asset = self.get_asset(asset_id)
            if asset is None:
                return None
            blob = self.get_blob(asset.blob_id)
            if blob is None:
                raise RuntimeError(f"media asset references a missing blob: {asset_id}")
            deleted = (
                MediaAssetRecord
                .delete()
                .where(MediaAssetRecord.id == str(asset_id))
                .execute()
            )
            if not deleted:
                return None
            blob_in_use = (
                MediaAssetRecord
                .select()
                .where(MediaAssetRecord.blob == blob.id)
                .exists()
            )
            blob_deleted = False
            if not blob_in_use:
                blob_deleted = bool(
                    MediaBlobRecord
                    .delete()
                    .where(MediaBlobRecord.id == blob.id)
                    .execute()
                )
        return models.MediaAssetDeleteResult(
            asset=asset,
            blob=blob,
            blob_deleted=blob_deleted,
        )

    def clear_session_runtime(self, session_id: str) -> models.SessionMediaResetResult:
        normalized_session_id = str(session_id)
        with self._database.atomic():
            backgrounds = self.clear_background(normalized_session_id)
            gallery_items = int(
                SessionMediaGalleryItemRecord
                .delete()
                .where(SessionMediaGalleryItemRecord.session == normalized_session_id)
                .execute()
            )
            jobs = int(
                MediaJobRecord
                .delete()
                .where(MediaJobRecord.session == normalized_session_id)
                .execute()
            )
        return models.SessionMediaResetResult(
            session_id=normalized_session_id,
            jobs_cleared=jobs,
            gallery_items_cleared=gallery_items,
            backgrounds_cleared=backgrounds,
        )

    def _finish_job(
        self,
        job_id: str,
        *,
        allowed_statuses: set[str],
        status: str,
        error_code: str = "",
        error_message: str = "",
    ) -> models.MediaJob | None:
        updated = (
            MediaJobRecord
            .update(
                status=str(status),
                error_code=str(error_code),
                error_message=str(error_message),
                finished_at=SQL("CURRENT_TIMESTAMP"),
                version=MediaJobRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (MediaJobRecord.id == str(job_id))
                & (MediaJobRecord.status.in_(tuple(allowed_statuses)))
            )
            .execute()
        )
        if not updated:
            return self.get_job(job_id)
        return self.get_job(job_id)


def _to_source_message(row: SessionMessageRecord) -> models.MediaSourceMessage:
    return models.MediaSourceMessage(
        id=int(row.id),
        version=int(row.version),
        role=str(row.role),
        content=str(row.content or ""),
        turn_id=int(row.turn_id),
        seq_in_turn=int(row.seq_in_turn),
    )


def _validate_existing_blob(
    blob: models.MediaBlob,
    *,
    canonical_ext: str,
    mime_type: str,
    byte_size: int,
    relative_path: str,
) -> None:
    expected = (
        str(canonical_ext),
        str(mime_type),
        int(byte_size),
        str(relative_path),
    )
    actual = (
        blob.canonical_ext,
        blob.mime_type,
        blob.byte_size,
        blob.relative_path,
    )
    if actual != expected:
        raise ValueError(
            f"media blob hash collision or inconsistent metadata for {blob.sha256}"
        )
