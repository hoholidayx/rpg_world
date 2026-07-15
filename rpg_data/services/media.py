"""Media persistence facade shared by the media process and Agent reset flow."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from peewee import Database

from rpg_data import models
from rpg_data.repositories.media_repo import MediaRepository
from rpg_data.repositories.session_repo import SessionRepository

__all__ = [
    "MediaAssetInUseError",
    "MediaDataService",
    "MediaSourceRangeError",
]

MAX_MEDIA_SOURCE_TURNS = 20


class MediaSourceRangeError(ValueError):
    """Raised when a source selection is not a valid committed turn range."""


class MediaAssetInUseError(ValueError):
    """Raised when a typed media binding still references an asset."""


class MediaDataService:
    """Expose typed media storage without leaking Peewee records."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._repository = MediaRepository(database)
        self._sessions = SessionRepository(database)

    def list_source_turns(self, session_id: str) -> list[models.MediaSourceTurn]:
        self._require_session(session_id)
        return self._repository.list_source_turns(str(session_id))

    def get_source_turns(
        self,
        session_id: str,
        *,
        start_turn_id: int,
        end_turn_id: int,
    ) -> list[models.MediaSourceTurn]:
        self._require_session(session_id)
        start = int(start_turn_id)
        end = int(end_turn_id)
        if start <= 0 or end < start:
            raise MediaSourceRangeError("media source turn range is invalid")
        count = end - start + 1
        if count > MAX_MEDIA_SOURCE_TURNS:
            raise MediaSourceRangeError(
                f"media source may contain at most {MAX_MEDIA_SOURCE_TURNS} turns"
            )
        turns = self._repository.get_source_turns(
            str(session_id),
            start_turn_id=start,
            end_turn_id=end,
        )
        actual_ids = [turn.turn_id for turn in turns]
        expected_ids = list(range(start, end + 1))
        if actual_ids != expected_ids:
            raise MediaSourceRangeError(
                "media source must be a contiguous range of committed turns"
            )
        return turns

    def create_job(
        self,
        *,
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
        self.get_source_turns(
            session_id,
            start_turn_id=source_start_turn_id,
            end_turn_id=source_end_turn_id,
        )
        if not str(provider_key).strip():
            raise ValueError("media provider key is required")
        if len(str(source_fingerprint)) != 64:
            raise ValueError("media source fingerprint must be a SHA-256 hex digest")
        if retry_of_job_id is not None:
            retry_source = self._repository.get_session_job(
                str(session_id),
                str(retry_of_job_id),
            )
            if retry_source is None:
                raise FileNotFoundError(f"Media job not found: {retry_of_job_id}")
        return self._repository.create_job(
            job_id=uuid.uuid4().hex,
            session_id=str(session_id),
            provider_key=str(provider_key),
            source_start_turn_id=int(source_start_turn_id),
            source_end_turn_id=int(source_end_turn_id),
            source_fingerprint=str(source_fingerprint),
            source_snapshot_json=str(source_snapshot_json),
            visual_brief_json=str(visual_brief_json),
            generation_params_json=str(generation_params_json),
            retry_of_job_id=str(retry_of_job_id) if retry_of_job_id else None,
        )

    def get_job(self, session_id: str, job_id: str) -> models.MediaJob | None:
        self._require_session(session_id)
        return self._repository.get_session_job(str(session_id), str(job_id))

    def get_job_for_worker(self, job_id: str) -> models.MediaJob | None:
        return self._repository.get_job(str(job_id))

    def list_jobs(
        self,
        session_id: str,
        *,
        statuses: Iterable[str] | None = None,
    ) -> list[models.MediaJob]:
        self._require_session(session_id)
        return self._repository.list_jobs(str(session_id), statuses=statuses)

    def claim_next_job(self) -> models.MediaJob | None:
        return self._repository.claim_next_job()

    def request_cancel(self, session_id: str, job_id: str) -> models.MediaJob | None:
        job = self._repository.get_session_job(str(session_id), str(job_id))
        if job is None:
            return None
        return self._repository.request_cancel(job.id)

    def mark_cancelled(self, job_id: str) -> models.MediaJob | None:
        return self._repository.mark_cancelled(str(job_id))

    def mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.MediaJob | None:
        return self._repository.mark_failed(
            str(job_id),
            error_code=str(error_code),
            error_message=str(error_message),
        )

    def interrupt_active_jobs(self) -> int:
        return self._repository.interrupt_active_jobs()

    def complete_job(
        self,
        *,
        job_id: str,
        sha256: str,
        canonical_ext: str,
        mime_type: str,
        byte_size: int,
        relative_path: str,
        provider_asset_id: str = "",
        metadata_json: str = "{}",
    ) -> models.MediaJobCompletion | None:
        job = self._repository.get_job(str(job_id))
        if job is None:
            return None
        session = self._sessions.get(job.session_id)
        if session is None:
            return None
        completed = self._repository.complete_job(
            job_id=job.id,
            workspace_id=session.workspace_id,
            blob_id=uuid.uuid4().hex,
            sha256=str(sha256),
            canonical_ext=str(canonical_ext),
            mime_type=str(mime_type),
            byte_size=int(byte_size),
            relative_path=str(relative_path),
            asset_id=uuid.uuid4().hex,
            gallery_item_id=uuid.uuid4().hex,
            provider_asset_id=str(provider_asset_id),
            metadata_json=str(metadata_json),
        )
        if completed is None:
            return None
        completed_job, asset, blob, gallery_item, blob_created = completed
        return models.MediaJobCompletion(
            job=completed_job,
            asset=asset,
            blob=blob,
            gallery_item=gallery_item,
            blob_created=blob_created,
        )

    def list_gallery(self, session_id: str) -> list[models.SessionMediaAssetBundle]:
        self._require_session(session_id)
        bundles: list[models.SessionMediaAssetBundle] = []
        for item in self._repository.list_gallery(str(session_id)):
            asset = self._repository.get_asset(item.asset_id)
            if asset is None:
                continue
            blob = self._repository.get_blob(asset.blob_id)
            if blob is None:
                continue
            bundles.append(
                models.SessionMediaAssetBundle(
                    gallery_item=item,
                    asset=asset,
                    blob=blob,
                )
            )
        return bundles

    def get_session_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.SessionMediaAssetBundle | None:
        self._require_session(session_id)
        item = self._repository.get_gallery_asset(str(session_id), str(asset_id))
        if item is None:
            return None
        asset = self._repository.get_asset(item.asset_id)
        if asset is None:
            return None
        blob = self._repository.get_blob(asset.blob_id)
        if blob is None:
            return None
        return models.SessionMediaAssetBundle(
            gallery_item=item,
            asset=asset,
            blob=blob,
        )

    def get_workspace_blob_by_hash(
        self,
        workspace_id: str,
        sha256: str,
    ) -> models.MediaBlob | None:
        return self._repository.get_blob_by_hash(str(workspace_id), str(sha256))

    def get_background(self, session_id: str) -> models.SessionMediaBackground | None:
        self._require_session(session_id)
        return self._repository.get_background(str(session_id))

    def set_background(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.SessionMediaBackground:
        self._require_session(session_id)
        if self._repository.get_gallery_asset(str(session_id), str(asset_id)) is None:
            raise FileNotFoundError(
                f"Media asset is not in the session gallery: {asset_id}"
            )
        return self._repository.set_background(str(session_id), str(asset_id))

    def clear_background(self, session_id: str) -> int:
        self._require_session(session_id)
        return self._repository.clear_background(str(session_id))

    def delete_session_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.MediaAssetDeleteResult | None:
        self._require_session(session_id)
        if self._repository.get_gallery_asset(str(session_id), str(asset_id)) is None:
            return None
        if self._repository.count_background_references(str(asset_id)):
            raise MediaAssetInUseError(
                f"media asset is referenced by a session background: {asset_id}"
            )
        return self._repository.delete_asset(str(asset_id))

    def clear_session_runtime(self, session_id: str) -> models.SessionMediaResetResult:
        self._require_session(session_id)
        return self._repository.clear_session_runtime(str(session_id))

    def _require_session(self, session_id: str) -> models.Session:
        session = self._sessions.get(str(session_id))
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session
