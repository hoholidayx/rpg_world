"""Typed persistence operations for workspace media and session media state."""

from __future__ import annotations

from collections.abc import Iterable

from peewee import Database, IntegrityError, SQL, fn

from rpg_data import models
from rpg_data.repositories._utils import (
    to_media_background_evaluation,
    to_media_asset,
    to_media_blob,
    to_media_job,
    to_media_library_item,
    to_session_media_background,
    to_session_media_background_state,
    to_session_media_gallery_item,
)
from rpg_data.repositories.records import (
    MediaBackgroundEvaluationRecord,
    MediaAssetRecord,
    MediaBlobRecord,
    MediaJobRecord,
    MediaLibraryItemRecord,
    MediaLibraryItemTagRecord,
    SessionMediaBackgroundRecord,
    SessionMediaBackgroundStateRecord,
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

    def get_latest_source_turns(
        self,
        session_id: str,
        *,
        through_turn_id: int,
        limit: int,
    ) -> list[models.MediaSourceTurn]:
        turn_rows = (
            SessionMessageRecord
            .select(SessionMessageRecord.turn_id)
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.turn_id > 0)
                & (SessionMessageRecord.turn_id <= int(through_turn_id))
            )
            .group_by(SessionMessageRecord.turn_id)
            .order_by(SessionMessageRecord.turn_id.desc())
            .limit(max(1, int(limit)))
        )
        turn_ids = sorted(int(row.turn_id) for row in turn_rows)
        if not turn_ids:
            return []
        rows = (
            SessionMessageRecord
            .select()
            .where(
                (SessionMessageRecord.session == str(session_id))
                & (SessionMessageRecord.turn_id.in_(turn_ids))
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
            models.MediaSourceTurn(turn_id=turn_id, messages=tuple(grouped[turn_id]))
            for turn_id in turn_ids
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

    def list_blobs(self, workspace_id: str) -> list[models.MediaBlob]:
        return [
            to_media_blob(row)
            for row in (
                MediaBlobRecord
                .select()
                .where(MediaBlobRecord.workspace == str(workspace_id))
                .order_by(MediaBlobRecord.created_at, MediaBlobRecord.id)
            )
        ]

    def purge_blob(self, blob_id: str) -> bool:
        """Remove an unusable blob index and every typed reference to its assets."""
        blob = self.get_blob(str(blob_id))
        if blob is None:
            return False
        result = self.reconcile_missing_blobs(
            workspace_id=blob.workspace_id,
            blob_ids=(blob.id,),
            scanned_blobs=1,
        )
        return result.removed_blobs > 0

    def reconcile_missing_blobs(
        self,
        *,
        workspace_id: str,
        blob_ids: tuple[str, ...],
        scanned_blobs: int,
    ) -> models.MediaLibraryReconcileResult:
        normalized_ids = tuple(dict.fromkeys(
            str(blob_id).strip()
            for blob_id in blob_ids
            if str(blob_id).strip()
        ))
        with self._database.atomic():
            existing_blob_ids = [
                str(row.id)
                for row in (
                    MediaBlobRecord
                    .select(MediaBlobRecord.id)
                    .where(
                        (MediaBlobRecord.workspace == str(workspace_id))
                        & (MediaBlobRecord.id.in_(normalized_ids))
                    )
                )
            ] if normalized_ids else []
            if not existing_blob_ids:
                return models.MediaLibraryReconcileResult(
                    workspace_id=str(workspace_id),
                    scanned_blobs=int(scanned_blobs),
                )
            asset_ids = [
                str(row.id)
                for row in (
                    MediaAssetRecord
                    .select(MediaAssetRecord.id)
                    .where(MediaAssetRecord.blob.in_(existing_blob_ids))
                )
            ]
            removed_library_items = int(
                MediaLibraryItemRecord
                .select()
                .where(MediaLibraryItemRecord.asset.in_(asset_ids))
                .count()
            ) if asset_ids else 0
            removed_gallery_items = int(
                SessionMediaGalleryItemRecord
                .select()
                .where(SessionMediaGalleryItemRecord.asset.in_(asset_ids))
                .count()
            ) if asset_ids else 0
            cleared_backgrounds = int(
                SessionMediaBackgroundRecord
                .delete()
                .where(SessionMediaBackgroundRecord.asset.in_(asset_ids))
                .execute()
            ) if asset_ids else 0
            removed_blobs = int(
                MediaBlobRecord
                .delete()
                .where(
                    (MediaBlobRecord.workspace == str(workspace_id))
                    & (MediaBlobRecord.id.in_(existing_blob_ids))
                )
                .execute()
            )
        return models.MediaLibraryReconcileResult(
            workspace_id=str(workspace_id),
            scanned_blobs=int(scanned_blobs),
            removed_blobs=removed_blobs,
            removed_assets=len(asset_ids),
            removed_library_items=removed_library_items,
            removed_gallery_items=removed_gallery_items,
            cleared_backgrounds=cleared_backgrounds,
        )

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
        origin_kind: str = models.MEDIA_ASSET_ORIGIN_GENERATED,
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
            origin_kind=str(origin_kind),
        )
        return to_media_asset(row)

    def get_library_item(self, item_id: str) -> models.MediaLibraryItem | None:
        row = MediaLibraryItemRecord.get_or_none(
            MediaLibraryItemRecord.id == str(item_id)
        )
        return to_media_library_item(row) if row is not None else None

    def get_library_item_by_asset(
        self,
        asset_id: str,
    ) -> models.MediaLibraryItem | None:
        row = MediaLibraryItemRecord.get_or_none(
            MediaLibraryItemRecord.asset == str(asset_id)
        )
        return to_media_library_item(row) if row is not None else None

    def list_library_items(
        self,
        workspace_id: str,
        *,
        scope: str | None = None,
        story_id: int | None = None,
        media_types: Iterable[str] | None = None,
    ) -> list[models.MediaLibraryItem]:
        query = MediaLibraryItemRecord.select().where(
            MediaLibraryItemRecord.workspace == str(workspace_id)
        )
        if scope is not None:
            query = query.where(MediaLibraryItemRecord.scope == str(scope))
        if story_id is not None:
            query = query.where(MediaLibraryItemRecord.story == int(story_id))
        normalized_types = tuple(str(value) for value in media_types or ())
        if normalized_types:
            query = query.where(MediaLibraryItemRecord.media_type.in_(normalized_types))
        return [
            to_media_library_item(row)
            for row in query.order_by(
                MediaLibraryItemRecord.is_default.desc(),
                MediaLibraryItemRecord.created_at.desc(),
                MediaLibraryItemRecord.id,
            )
        ]

    def list_library_items_page(
        self,
        workspace_id: str,
        *,
        query_text: str = "",
        media_types: Iterable[str] = (),
        tags: Iterable[str] = (),
        scope: str | None = None,
        story_id: int | None = None,
        origins: Iterable[str] = (),
        sort: str = "updated_desc",
        page: int = 1,
        page_size: int = 48,
    ) -> tuple[list[models.MediaLibraryItem], int]:
        query = (
            MediaLibraryItemRecord
            .select(MediaLibraryItemRecord)
            .join(MediaAssetRecord)
            .join(MediaBlobRecord)
            .where(MediaLibraryItemRecord.workspace == str(workspace_id))
        )
        normalized_types = tuple(str(value) for value in media_types)
        normalized_origins = tuple(str(value) for value in origins)
        if normalized_types:
            query = query.where(MediaLibraryItemRecord.media_type.in_(normalized_types))
        if normalized_origins:
            query = query.where(MediaAssetRecord.origin_kind.in_(normalized_origins))
        if scope is not None:
            query = query.where(MediaLibraryItemRecord.scope == str(scope))
        if story_id is not None:
            query = query.where(MediaLibraryItemRecord.story == int(story_id))
        for tag in tags:
            normalized_tag = str(tag).strip().casefold()
            if not normalized_tag:
                continue
            matching_items = (
                MediaLibraryItemTagRecord
                .select(MediaLibraryItemTagRecord.item)
                .where(MediaLibraryItemTagRecord.normalized_tag == normalized_tag)
            )
            query = query.where(MediaLibraryItemRecord.id.in_(matching_items))
        normalized_query = str(query_text).strip().casefold()
        if normalized_query:
            tag_matches = (
                MediaLibraryItemTagRecord
                .select(MediaLibraryItemTagRecord.item)
                .where(MediaLibraryItemTagRecord.normalized_tag.contains(normalized_query))
            )
            query = query.where(
                fn.LOWER(MediaLibraryItemRecord.title).contains(normalized_query)
                | fn.LOWER(MediaLibraryItemRecord.description).contains(normalized_query)
                | MediaLibraryItemRecord.id.in_(tag_matches)
            )
        total = int(query.count())
        orderings = {
            "updated_desc": (
                MediaLibraryItemRecord.updated_at.desc(),
                MediaLibraryItemRecord.id.desc(),
            ),
            "created_desc": (
                MediaLibraryItemRecord.created_at.desc(),
                MediaLibraryItemRecord.id.desc(),
            ),
            "title_asc": (
                fn.LOWER(MediaLibraryItemRecord.title).asc(),
                MediaLibraryItemRecord.id.asc(),
            ),
            "size_desc": (
                MediaBlobRecord.byte_size.desc(),
                MediaLibraryItemRecord.id.desc(),
            ),
        }
        rows = query.order_by(*orderings[str(sort)]).paginate(int(page), int(page_size))
        return [to_media_library_item(row) for row in rows], total

    def get_library_facets(self, workspace_id: str) -> models.MediaLibraryFacets:
        workspace = str(workspace_id)
        type_rows = (
            MediaLibraryItemRecord
            .select(
                MediaLibraryItemRecord.media_type,
                fn.COUNT(MediaLibraryItemRecord.id),
            )
            .where(MediaLibraryItemRecord.workspace == workspace)
            .group_by(MediaLibraryItemRecord.media_type)
            .tuples()
        )
        scope_rows = (
            MediaLibraryItemRecord
            .select(MediaLibraryItemRecord.scope, fn.COUNT(MediaLibraryItemRecord.id))
            .where(MediaLibraryItemRecord.workspace == workspace)
            .group_by(MediaLibraryItemRecord.scope)
            .tuples()
        )
        origin_rows = (
            MediaLibraryItemRecord
            .select(MediaAssetRecord.origin_kind, fn.COUNT(MediaLibraryItemRecord.id))
            .join(MediaAssetRecord)
            .where(MediaLibraryItemRecord.workspace == workspace)
            .group_by(MediaAssetRecord.origin_kind)
            .tuples()
        )
        tag_rows = (
            MediaLibraryItemTagRecord
            .select(
                fn.MIN(MediaLibraryItemTagRecord.tag),
                fn.COUNT(MediaLibraryItemTagRecord.item),
            )
            .join(MediaLibraryItemRecord)
            .where(MediaLibraryItemRecord.workspace == workspace)
            .group_by(MediaLibraryItemTagRecord.normalized_tag)
            .order_by(fn.COUNT(MediaLibraryItemTagRecord.item).desc())
            .tuples()
        )
        story_rows = (
            MediaLibraryItemRecord
            .select(MediaLibraryItemRecord.story, fn.COUNT(MediaLibraryItemRecord.id))
            .where(
                (MediaLibraryItemRecord.workspace == workspace)
                & (MediaLibraryItemRecord.story.is_null(False))
            )
            .group_by(MediaLibraryItemRecord.story)
            .tuples()
        )
        return models.MediaLibraryFacets(
            media_types=tuple(
                models.MediaLibraryFacetValue(value=str(value), count=int(count))
                for value, count in type_rows
            ),
            tags=tuple(
                models.MediaLibraryFacetValue(value=str(value), count=int(count))
                for value, count in tag_rows
            ),
            scopes=tuple(
                models.MediaLibraryFacetValue(value=str(value), count=int(count))
                for value, count in scope_rows
            ),
            origins=tuple(
                models.MediaLibraryFacetValue(value=str(value), count=int(count))
                for value, count in origin_rows
            ),
            stories=tuple(
                models.MediaLibraryStoryFacet(story_id=int(value), count=int(count))
                for value, count in story_rows
            ),
        )

    def get_library_usage(
        self,
        asset_ids: Iterable[str],
    ) -> dict[str, models.MediaLibraryUsage]:
        normalized_ids = tuple(dict.fromkeys(str(value) for value in asset_ids))
        if not normalized_ids:
            return {}
        background_counts = {
            str(asset_id): int(count)
            for asset_id, count in (
                SessionMediaBackgroundRecord
                .select(
                    SessionMediaBackgroundRecord.asset,
                    fn.COUNT(SessionMediaBackgroundRecord.session),
                )
                .where(SessionMediaBackgroundRecord.asset.in_(normalized_ids))
                .group_by(SessionMediaBackgroundRecord.asset)
                .tuples()
            )
        }
        gallery_counts = {
            str(asset_id): int(count)
            for asset_id, count in (
                SessionMediaGalleryItemRecord
                .select(
                    SessionMediaGalleryItemRecord.asset,
                    fn.COUNT(SessionMediaGalleryItemRecord.id),
                )
                .where(SessionMediaGalleryItemRecord.asset.in_(normalized_ids))
                .group_by(SessionMediaGalleryItemRecord.asset)
                .tuples()
            )
        }
        return {
            asset_id: models.MediaLibraryUsage(
                background_references=background_counts.get(asset_id, 0),
                gallery_references=gallery_counts.get(asset_id, 0),
            )
            for asset_id in normalized_ids
        }

    def get_story_default_library_item(
        self,
        story_id: int,
    ) -> models.MediaLibraryItem | None:
        row = MediaLibraryItemRecord.get_or_none(
            (MediaLibraryItemRecord.story == int(story_id))
            & (MediaLibraryItemRecord.scope == models.MEDIA_LIBRARY_SCOPE_STORY)
            & (MediaLibraryItemRecord.media_type == models.MEDIA_LIBRARY_TYPE_BACKGROUND)
            & (MediaLibraryItemRecord.is_default == True)  # noqa: E712
        )
        return to_media_library_item(row) if row is not None else None

    def list_library_item_tags(self, item_id: str) -> tuple[str, ...]:
        rows = (
            MediaLibraryItemTagRecord
            .select(MediaLibraryItemTagRecord.tag)
            .where(MediaLibraryItemTagRecord.item == str(item_id))
            .order_by(MediaLibraryItemTagRecord.normalized_tag)
        )
        return tuple(str(row.tag) for row in rows)

    def create_library_asset(
        self,
        *,
        item_id: str,
        asset_id: str,
        blob_id: str,
        workspace_id: str,
        sha256: str,
        canonical_ext: str,
        mime_type: str,
        byte_size: int,
        relative_path: str,
        scope: str,
        story_id: int | None,
        media_type: str,
        title: str,
        description: str,
        tags: tuple[str, ...],
        is_default: bool,
        visual_brief_json: str,
    ) -> tuple[models.MediaLibraryItem, models.MediaAsset, models.MediaBlob, bool]:
        with self._database.atomic():
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
                provider_key="",
                visual_brief_json=visual_brief_json,
                origin_kind=models.MEDIA_ASSET_ORIGIN_UPLOAD,
            )
            if is_default and story_id is not None:
                (
                    MediaLibraryItemRecord
                    .update(
                        is_default=False,
                        version=MediaLibraryItemRecord.version + 1,
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                    )
                    .where(
                        (MediaLibraryItemRecord.story == int(story_id))
                        & (
                            MediaLibraryItemRecord.media_type
                            == models.MEDIA_LIBRARY_TYPE_BACKGROUND
                        )
                    )
                    .execute()
                )
            row = MediaLibraryItemRecord.create(
                id=str(item_id),
                workspace=str(workspace_id),
                asset=asset.id,
                scope=str(scope),
                story=story_id,
                media_type=str(media_type),
                title=str(title),
                description=str(description),
                is_default=bool(is_default),
            )
            if tags:
                MediaLibraryItemTagRecord.insert_many([
                    {
                        "item": str(item_id),
                        "tag": tag,
                    }
                    for tag in tags
                ]).execute()
        return to_media_library_item(row), asset, blob, blob_created

    def update_library_item(
        self,
        item_id: str,
        *,
        scope: str,
        story_id: int | None,
        media_type: str,
        title: str,
        description: str,
        tags: tuple[str, ...],
        is_default: bool,
    ) -> models.MediaLibraryItem | None:
        with self._database.atomic():
            row = MediaLibraryItemRecord.get_or_none(
                MediaLibraryItemRecord.id == str(item_id)
            )
            if row is None:
                return None
            if is_default and story_id is not None:
                (
                    MediaLibraryItemRecord
                    .update(
                        is_default=False,
                        version=MediaLibraryItemRecord.version + 1,
                        updated_at=SQL("CURRENT_TIMESTAMP"),
                    )
                    .where(
                        (MediaLibraryItemRecord.story == int(story_id))
                        & (
                            MediaLibraryItemRecord.media_type
                            == models.MEDIA_LIBRARY_TYPE_BACKGROUND
                        )
                        & (MediaLibraryItemRecord.id != str(item_id))
                    )
                    .execute()
                )
            row.scope = str(scope)
            row.story = story_id
            row.media_type = str(media_type)
            row.title = str(title)
            row.description = str(description)
            row.is_default = bool(is_default)
            row.version = int(row.version) + 1
            row.updated_at = SQL("CURRENT_TIMESTAMP")
            row.save()
            (
                MediaLibraryItemTagRecord
                .delete()
                .where(MediaLibraryItemTagRecord.item == str(item_id))
                .execute()
            )
            if tags:
                MediaLibraryItemTagRecord.insert_many([
                    {
                        "item": str(item_id),
                        "tag": tag,
                    }
                    for tag in tags
                ]).execute()
        return self.get_library_item(item_id)

    def delete_library_item(self, item_id: str) -> str | None:
        with self._database.atomic():
            row = MediaLibraryItemRecord.get_or_none(
                MediaLibraryItemRecord.id == str(item_id)
            )
            if row is None:
                return None
            asset_id = str(row.asset_id)
            row.delete_instance()
        return asset_id

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
        library_item_id: str,
        story_id: int,
        library_title: str,
        library_description: str,
        library_tags: tuple[str, ...],
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
            MediaLibraryItemRecord.create(
                id=str(library_item_id),
                workspace=str(workspace_id),
                asset=asset.id,
                scope=models.MEDIA_LIBRARY_SCOPE_STORY,
                story=int(story_id),
                media_type=models.MEDIA_LIBRARY_TYPE_BACKGROUND,
                title=str(library_title),
                description=str(library_description),
                is_default=False,
            )
            MediaLibraryItemTagRecord.insert_many([
                {
                    "item": str(library_item_id),
                    "tag": tag,
                }
                for tag in library_tags
            ]).execute()
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

    def get_background_state(
        self,
        session_id: str,
    ) -> models.SessionMediaBackgroundState | None:
        row = SessionMediaBackgroundStateRecord.get_or_none(
            SessionMediaBackgroundStateRecord.session == str(session_id)
        )
        return to_session_media_background_state(row) if row is not None else None

    def ensure_background_state(
        self,
        session_id: str,
    ) -> models.SessionMediaBackgroundState:
        row, _ = SessionMediaBackgroundStateRecord.get_or_create(
            session=str(session_id)
        )
        return to_session_media_background_state(row)

    def update_background_state(
        self,
        session_id: str,
        **fields: object,
    ) -> models.SessionMediaBackgroundState:
        self.ensure_background_state(session_id)
        payload = dict(fields)
        payload["version"] = SessionMediaBackgroundStateRecord.version + 1
        payload["updated_at"] = SQL("CURRENT_TIMESTAMP")
        (
            SessionMediaBackgroundStateRecord
            .update(**payload)
            .where(SessionMediaBackgroundStateRecord.session == str(session_id))
            .execute()
        )
        state = self.get_background_state(session_id)
        if state is None:
            raise RuntimeError(f"failed to update media background state: {session_id}")
        return state

    def set_background(
        self,
        session_id: str,
        asset_id: str,
        *,
        source_mode: str = models.MEDIA_BACKGROUND_SOURCE_MANUAL,
    ) -> models.SessionMediaBackground:
        with self._database.atomic():
            row = SessionMediaBackgroundRecord.get_or_none(
                SessionMediaBackgroundRecord.session == str(session_id)
            )
            if row is None:
                SessionMediaBackgroundRecord.create(
                    session=str(session_id),
                    asset=str(asset_id),
                    source_mode=str(source_mode),
                )
            else:
                (
                    SessionMediaBackgroundRecord
                    .update(
                        asset=str(asset_id),
                        source_mode=str(source_mode),
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

    def get_background_evaluation(
        self,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        row = MediaBackgroundEvaluationRecord.get_or_none(
            MediaBackgroundEvaluationRecord.id == str(evaluation_id)
        )
        return to_media_background_evaluation(row) if row is not None else None

    def get_session_background_evaluation(
        self,
        session_id: str,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        row = MediaBackgroundEvaluationRecord.get_or_none(
            (MediaBackgroundEvaluationRecord.session == str(session_id))
            & (MediaBackgroundEvaluationRecord.id == str(evaluation_id))
        )
        return to_media_background_evaluation(row) if row is not None else None

    def get_latest_background_evaluation(
        self,
        session_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        row = (
            MediaBackgroundEvaluationRecord
            .select()
            .where(MediaBackgroundEvaluationRecord.session == str(session_id))
            .order_by(
                MediaBackgroundEvaluationRecord.created_at.desc(),
                MediaBackgroundEvaluationRecord.id.desc(),
            )
            .first()
        )
        return to_media_background_evaluation(row) if row is not None else None

    def get_queued_background_evaluation(
        self,
        session_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        row = (
            MediaBackgroundEvaluationRecord
            .select()
            .where(
                (MediaBackgroundEvaluationRecord.session == str(session_id))
                & (
                    MediaBackgroundEvaluationRecord.status
                    == models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED
                )
            )
            .order_by(MediaBackgroundEvaluationRecord.created_at.desc())
            .first()
        )
        return to_media_background_evaluation(row) if row is not None else None

    def get_active_background_evaluation(
        self,
        session_id: str,
        source_fingerprint: str,
    ) -> models.MediaBackgroundEvaluation | None:
        row = (
            MediaBackgroundEvaluationRecord
            .select()
            .where(
                (MediaBackgroundEvaluationRecord.session == str(session_id))
                & (
                    MediaBackgroundEvaluationRecord.source_fingerprint
                    == str(source_fingerprint)
                )
                & (
                    MediaBackgroundEvaluationRecord.status.in_((
                        models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
                        models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING,
                    ))
                )
            )
            .order_by(MediaBackgroundEvaluationRecord.created_at.desc())
            .first()
        )
        return to_media_background_evaluation(row) if row is not None else None

    def get_successful_background_evaluation(
        self,
        session_id: str,
        source_fingerprint: str,
    ) -> models.MediaBackgroundEvaluation | None:
        row = (
            MediaBackgroundEvaluationRecord
            .select()
            .where(
                (MediaBackgroundEvaluationRecord.session == str(session_id))
                & (
                    MediaBackgroundEvaluationRecord.status
                    == models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED
                )
                & (
                    MediaBackgroundEvaluationRecord.source_fingerprint
                    == str(source_fingerprint)
                )
            )
            .order_by(MediaBackgroundEvaluationRecord.created_at.desc())
            .first()
        )
        return to_media_background_evaluation(row) if row is not None else None

    def create_background_evaluation(
        self,
        *,
        evaluation_id: str,
        session_id: str,
        status: str,
        target_turn_id: int,
        source_fingerprint: str,
        source_snapshot_json: str,
        decision: str = "",
        selected_asset_id: str | None = None,
        reason: str = "",
    ) -> models.MediaBackgroundEvaluation:
        row = MediaBackgroundEvaluationRecord.create(
            id=str(evaluation_id),
            session=str(session_id),
            status=str(status),
            target_turn_id=int(target_turn_id),
            source_fingerprint=str(source_fingerprint),
            source_snapshot_json=str(source_snapshot_json),
            decision=str(decision),
            selected_asset=selected_asset_id,
            reason=str(reason),
            finished_at=(
                SQL("CURRENT_TIMESTAMP")
                if status not in {
                    models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
                    models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING,
                }
                else None
            ),
        )
        return to_media_background_evaluation(row)

    def update_queued_background_evaluation(
        self,
        evaluation_id: str,
        *,
        target_turn_id: int,
        source_fingerprint: str,
        source_snapshot_json: str,
    ) -> models.MediaBackgroundEvaluation | None:
        updated = (
            MediaBackgroundEvaluationRecord
            .update(
                target_turn_id=int(target_turn_id),
                source_fingerprint=str(source_fingerprint),
                source_snapshot_json=str(source_snapshot_json),
                version=MediaBackgroundEvaluationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (MediaBackgroundEvaluationRecord.id == str(evaluation_id))
                & (
                    MediaBackgroundEvaluationRecord.status
                    == models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED
                )
            )
            .execute()
        )
        return self.get_background_evaluation(evaluation_id) if updated else None

    def claim_next_background_evaluation(
        self,
    ) -> models.MediaBackgroundEvaluation | None:
        with self._database.atomic():
            row = (
                MediaBackgroundEvaluationRecord
                .select()
                .where(
                    MediaBackgroundEvaluationRecord.status
                    == models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED
                )
                .order_by(
                    MediaBackgroundEvaluationRecord.created_at,
                    MediaBackgroundEvaluationRecord.id,
                )
                .first()
            )
            if row is None:
                return None
            updated = (
                MediaBackgroundEvaluationRecord
                .update(
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING,
                    started_at=SQL("CURRENT_TIMESTAMP"),
                    finished_at=None,
                    version=MediaBackgroundEvaluationRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(
                    (MediaBackgroundEvaluationRecord.id == str(row.id))
                    & (
                        MediaBackgroundEvaluationRecord.status
                        == models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED
                    )
                )
                .execute()
            )
        return self.get_background_evaluation(str(row.id)) if updated else None

    def finish_background_evaluation(
        self,
        evaluation_id: str,
        *,
        status: str,
        decision: str = "",
        selected_asset_id: str | None = None,
        reason: str = "",
        error_code: str = "",
        error_message: str = "",
    ) -> models.MediaBackgroundEvaluation | None:
        updated = (
            MediaBackgroundEvaluationRecord
            .update(
                status=str(status),
                decision=str(decision),
                selected_asset=selected_asset_id,
                reason=str(reason),
                error_code=str(error_code),
                error_message=str(error_message),
                finished_at=SQL("CURRENT_TIMESTAMP"),
                version=MediaBackgroundEvaluationRecord.version + 1,
                updated_at=SQL("CURRENT_TIMESTAMP"),
            )
            .where(
                (MediaBackgroundEvaluationRecord.id == str(evaluation_id))
                & (
                    MediaBackgroundEvaluationRecord.status
                    == models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING
                )
            )
            .execute()
        )
        return self.get_background_evaluation(evaluation_id) if updated else None

    def interrupt_running_background_evaluations(
        self,
    ) -> list[models.MediaBackgroundEvaluation]:
        rows = list(
            MediaBackgroundEvaluationRecord
            .select()
            .where(
                MediaBackgroundEvaluationRecord.status
                == models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING
            )
        )
        if rows:
            (
                MediaBackgroundEvaluationRecord
                .update(
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_INTERRUPTED,
                    error_code="MEDIA_BACKGROUND_EVALUATION_INTERRUPTED",
                    error_message="Media service restarted during background evaluation.",
                    finished_at=SQL("CURRENT_TIMESTAMP"),
                    version=MediaBackgroundEvaluationRecord.version + 1,
                    updated_at=SQL("CURRENT_TIMESTAMP"),
                )
                .where(
                    MediaBackgroundEvaluationRecord.status
                    == models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING
                )
                .execute()
            )
        return [to_media_background_evaluation(row) for row in rows]

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
            (
                MediaBackgroundEvaluationRecord
                .delete()
                .where(MediaBackgroundEvaluationRecord.session == normalized_session_id)
                .execute()
            )
            (
                SessionMediaBackgroundStateRecord
                .delete()
                .where(SessionMediaBackgroundStateRecord.session == normalized_session_id)
                .execute()
            )
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
