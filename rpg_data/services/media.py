"""Media persistence facade shared by the media process and Agent reset flow."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import ContextManager

from peewee import Database

from rpg_data import models
from rpg_data.repositories.media_repo import MediaRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

__all__ = [
    "MediaDataService",
]


class MediaDataService:
    """Expose typed media storage without leaking Peewee records."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._repository = MediaRepository(database)
        self._sessions = SessionRepository(database)
        self._stories = StoryRepository(database)
        self._workspaces = WorkspaceRepository(database)

    def transaction(self) -> ContextManager[None]:
        """Expose a short database transaction for caller-selected media writes."""

        return self._database.atomic()

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
        return self._repository.get_source_turns(
            str(session_id),
            start_turn_id=int(start_turn_id),
            end_turn_id=int(end_turn_id),
        )

    def get_latest_source_turns(
        self,
        session_id: str,
        *,
        through_turn_id: int,
        limit: int = 3,
    ) -> list[models.MediaSourceTurn]:
        self._require_session(session_id)
        return self._repository.get_latest_source_turns(
            str(session_id),
            through_turn_id=int(through_turn_id),
            limit=max(1, int(limit)),
        )

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
        self._require_session(session_id)
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

    def transition_jobs(
        self,
        *,
        from_statuses: Iterable[str],
        to_status: str,
        error_code: str = "",
        error_message: str = "",
    ) -> int:
        return self._repository.transition_jobs(
            from_statuses=from_statuses,
            to_status=to_status,
            error_code=error_code,
            error_message=error_message,
        )

    def complete_job(
        self,
        *,
        job_id: str,
        write: models.MediaJobCompletionWrite,
    ) -> models.MediaJobCompletion | None:
        job = self._repository.get_job(str(job_id))
        if job is None:
            return None
        session = self._sessions.get(job.session_id)
        if session is None:
            return None
        if (
            write.workspace_id != session.workspace_id
            or write.story_id != session.story_id
        ):
            raise ValueError("media completion owner does not match the job session")
        completed = self._repository.complete_job(
            job_id=job.id,
            workspace_id=write.workspace_id,
            blob_id=uuid.uuid4().hex,
            sha256=write.sha256,
            canonical_ext=write.canonical_ext,
            mime_type=write.mime_type,
            byte_size=write.byte_size,
            relative_path=write.relative_path,
            asset_id=uuid.uuid4().hex,
            gallery_item_id=uuid.uuid4().hex,
            library_item_id=uuid.uuid4().hex,
            story_id=write.story_id,
            library_title=write.library_title,
            library_description=write.library_description,
            library_tags=write.library_tags,
            provider_asset_id=write.provider_asset_id,
            metadata_json=write.metadata_json,
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

    def purge_missing_blob(self, blob_id: str) -> bool:
        return self._repository.purge_blob(str(blob_id))

    def list_workspace_blobs(self, workspace_id: str) -> list[models.MediaBlob]:
        self._require_workspace(workspace_id)
        return self._repository.list_blobs(str(workspace_id))

    def reconcile_missing_blobs(
        self,
        workspace_id: str,
        *,
        blob_ids: tuple[str, ...],
        scanned_blobs: int,
    ) -> models.MediaLibraryReconcileResult:
        self._require_workspace(workspace_id)
        return self._repository.reconcile_missing_blobs(
            workspace_id=str(workspace_id),
            blob_ids=blob_ids,
            scanned_blobs=int(scanned_blobs),
        )

    def create_library_asset(
        self,
        *,
        workspace_id: str,
        scope: str,
        story_id: int | None,
        media_type: str = models.MEDIA_LIBRARY_TYPE_BACKGROUND,
        title: str,
        description: str,
        tags: tuple[str, ...],
        is_default: bool,
        sha256: str,
        canonical_ext: str,
        mime_type: str,
        byte_size: int,
        relative_path: str,
        visual_brief_json: str,
    ) -> tuple[models.MediaLibraryAssetBundle, bool]:
        self._require_library_owner(workspace_id, scope=scope, story_id=story_id)
        _validate_library_type(media_type)
        item, asset, blob, blob_created = self._repository.create_library_asset(
            item_id=uuid.uuid4().hex,
            asset_id=uuid.uuid4().hex,
            blob_id=uuid.uuid4().hex,
            workspace_id=str(workspace_id),
            sha256=str(sha256),
            canonical_ext=str(canonical_ext),
            mime_type=str(mime_type),
            byte_size=int(byte_size),
            relative_path=str(relative_path),
            scope=str(scope),
            story_id=story_id,
            media_type=str(media_type),
            title=str(title),
            description=str(description),
            tags=tuple(str(tag) for tag in tags),
            is_default=bool(is_default),
            visual_brief_json=str(visual_brief_json),
        )
        return (
            models.MediaLibraryAssetBundle(
                item=item,
                asset=asset,
                blob=blob,
                tags=tuple(str(tag) for tag in tags),
            ),
            blob_created,
        )

    def list_library_assets(
        self,
        workspace_id: str,
        *,
        scope: str | None = None,
        story_id: int | None = None,
        media_types: tuple[str, ...] = (),
    ) -> list[models.MediaLibraryAssetBundle]:
        self._require_workspace(workspace_id)
        if scope is not None and scope not in models.MEDIA_LIBRARY_SCOPES:
            raise ValueError(f"invalid media library scope: {scope}")
        if story_id is not None:
            self._require_story(workspace_id, story_id)
        if scope == models.MEDIA_LIBRARY_SCOPE_WORKSPACE and story_id is not None:
            raise ValueError("workspace media filter must not bind a story")
        _validate_library_types(media_types)
        return self._library_bundles(
            self._repository.list_library_items(
                str(workspace_id),
                scope=scope,
                story_id=story_id,
                media_types=media_types,
            )
        )

    def list_library_assets_page(
        self,
        workspace_id: str,
        *,
        query: str = "",
        media_types: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        scope: str | None = None,
        story_id: int | None = None,
        origins: tuple[str, ...] = (),
        sort: str = "updated_desc",
        page: int = 1,
        page_size: int = 48,
    ) -> models.MediaLibraryPage:
        self._require_workspace(workspace_id)
        if scope is not None and scope not in models.MEDIA_LIBRARY_SCOPES:
            raise ValueError(f"invalid media library scope: {scope}")
        if story_id is not None:
            self._require_story(workspace_id, story_id)
        if scope == models.MEDIA_LIBRARY_SCOPE_WORKSPACE and story_id is not None:
            raise ValueError("workspace media filter must not bind a story")
        _validate_library_types(media_types)
        invalid_origins = set(origins) - set(models.MEDIA_ASSET_ORIGINS)
        if invalid_origins:
            raise ValueError(f"invalid media origins: {', '.join(sorted(invalid_origins))}")
        if sort not in {"updated_desc", "created_desc", "title_asc", "size_desc"}:
            raise ValueError(f"invalid media library sort: {sort}")
        normalized_page = int(page)
        normalized_page_size = int(page_size)
        if normalized_page < 1:
            raise ValueError("media library page must be positive")
        if not 1 <= normalized_page_size <= 100:
            raise ValueError("media library pageSize must be between 1 and 100")
        items, total = self._repository.list_library_items_page(
            str(workspace_id),
            query_text=str(query),
            media_types=media_types,
            tags=tags,
            scope=scope,
            story_id=story_id,
            origins=origins,
            sort=sort,
            page=normalized_page,
            page_size=normalized_page_size,
        )
        return models.MediaLibraryPage(
            items=tuple(self._library_bundles(items)),
            page=normalized_page,
            page_size=normalized_page_size,
            total=total,
        )

    def get_library_facets(self, workspace_id: str) -> models.MediaLibraryFacets:
        self._require_workspace(workspace_id)
        return self._repository.get_library_facets(str(workspace_id))

    def get_library_asset(
        self,
        workspace_id: str,
        item_id: str,
    ) -> models.MediaLibraryAssetBundle | None:
        self._require_workspace(workspace_id)
        item = self._repository.get_library_item(str(item_id))
        if item is None or item.workspace_id != str(workspace_id):
            return None
        return self._library_bundle(item)

    def get_library_asset_by_asset_id(
        self,
        asset_id: str,
    ) -> models.MediaLibraryAssetBundle | None:
        item = self._repository.get_library_item_by_asset(str(asset_id))
        return self._library_bundle(item) if item is not None else None

    def get_story_default_asset(
        self,
        story_id: int,
    ) -> models.MediaLibraryAssetBundle | None:
        item = self._repository.get_story_default_library_item(int(story_id))
        return self._library_bundle(item) if item is not None else None

    def update_library_asset(
        self,
        workspace_id: str,
        item_id: str,
        *,
        scope: str,
        story_id: int | None,
        media_type: str,
        title: str,
        description: str,
        tags: tuple[str, ...],
        is_default: bool,
    ) -> models.MediaLibraryAssetBundle | None:
        existing = self.get_library_asset(workspace_id, item_id)
        if existing is None:
            return None
        self._require_library_owner(workspace_id, scope=scope, story_id=story_id)
        _validate_library_type(media_type)
        item = self._repository.update_library_item(
            str(item_id),
            scope=scope,
            story_id=story_id,
            media_type=media_type,
            title=str(title),
            description=str(description),
            tags=tuple(str(tag) for tag in tags),
            is_default=bool(is_default),
        )
        return self._library_bundle(item) if item is not None else None

    def delete_library_asset(
        self,
        workspace_id: str,
        item_id: str,
    ) -> models.MediaAssetDeleteResult | None:
        existing = self.get_library_asset(workspace_id, item_id)
        if existing is None:
            return None
        with self._database.atomic():
            asset_id = self._repository.delete_library_item(str(item_id))
            return self._repository.delete_asset(asset_id) if asset_id is not None else None

    def count_background_references(self, asset_id: str) -> int:
        return self._repository.count_background_references(str(asset_id))

    def search_library_assets(
        self,
        *,
        workspace_id: str,
        scope: str,
        story_id: int | None,
        query: str,
        weights: models.MediaLibrarySearchWeights,
        tags: tuple[str, ...] = (),
        limit: int = 20,
    ) -> list[models.MediaLibraryAssetBundle]:
        candidates = self.list_library_assets(
            workspace_id,
            scope=scope,
            story_id=story_id,
            media_types=(models.MEDIA_LIBRARY_TYPE_BACKGROUND,),
        )
        terms = _search_terms(query, tags)
        if not terms:
            return candidates[: max(1, min(20, int(limit)))]

        def score(bundle: models.MediaLibraryAssetBundle) -> tuple[int, str, str]:
            normalized_tags = {tag.casefold() for tag in bundle.tags}
            title = bundle.item.title.casefold()
            description = bundle.item.description.casefold()
            value = 0
            for term in terms:
                if term in normalized_tags:
                    value += weights.exact_tag
                if term in title:
                    value += weights.title_contains
                if term in description:
                    value += weights.description_contains
            return value, bundle.item.updated_at, bundle.item.id

        ranked = [bundle for bundle in candidates if score(bundle)[0] > 0]
        ranked.sort(key=score, reverse=True)
        return ranked[: max(1, min(20, int(limit)))]

    def get_background(self, session_id: str) -> models.SessionMediaBackground | None:
        self._require_session(session_id)
        return self._repository.get_background(str(session_id))

    def get_background_state(
        self,
        session_id: str,
    ) -> models.SessionMediaBackgroundState:
        self._require_session(session_id)
        return self._repository.ensure_background_state(str(session_id))

    def set_background(
        self,
        session_id: str,
        asset_id: str,
        *,
        source_mode: str,
    ) -> models.SessionMediaBackground:
        self._require_session(session_id)
        self._repository.ensure_background_state(str(session_id))
        return self._repository.set_background(
            str(session_id),
            str(asset_id),
            source_mode=str(source_mode),
        )

    def clear_background(self, session_id: str) -> int:
        self._require_session(session_id)
        return self._repository.clear_background(str(session_id))

    def update_background_state(
        self,
        session_id: str,
        **values: int | str | bool,
    ) -> models.SessionMediaBackgroundState:
        self._require_session(session_id)
        return self._repository.update_background_state(str(session_id), **values)

    def get_display_asset_for_session(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.MediaDisplayAssetBundle | None:
        session = self._require_session(session_id)
        gallery_item = self._repository.get_gallery_asset(str(session_id), str(asset_id))
        library_item = self._repository.get_library_item_by_asset(str(asset_id))
        background = self._repository.get_background(str(session_id))
        library_allowed = library_item is not None and (
            (
                library_item.scope == models.MEDIA_LIBRARY_SCOPE_STORY
                and library_item.story_id == session.story_id
            )
            or (
                background is not None
                and background.asset_id == str(asset_id)
            )
        )
        if gallery_item is None and not library_allowed:
            return None
        asset = self._repository.get_asset(str(asset_id))
        if asset is None:
            return None
        blob = self._repository.get_blob(asset.blob_id)
        if blob is None:
            return None
        return models.MediaDisplayAssetBundle(
            asset=asset,
            blob=blob,
            library_item=library_item,
            tags=(
                self._repository.list_library_item_tags(library_item.id)
                if library_item is not None
                else ()
            ),
            gallery_item=gallery_item,
        )

    def get_background_evaluation(
        self,
        session_id: str,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        self._require_session(session_id)
        return self._repository.get_session_background_evaluation(
            str(session_id),
            str(evaluation_id),
        )

    def get_background_evaluation_for_worker(
        self,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.get_background_evaluation(str(evaluation_id))

    def get_latest_background_evaluation(
        self,
        session_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        self._require_session(session_id)
        return self._repository.get_latest_background_evaluation(str(session_id))

    def get_successful_background_evaluation(
        self,
        session_id: str,
        source_fingerprint: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.get_successful_background_evaluation(
            str(session_id),
            str(source_fingerprint),
        )

    def get_active_background_evaluation(
        self,
        session_id: str,
        source_fingerprint: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.get_active_background_evaluation(
            str(session_id),
            str(source_fingerprint),
        )

    def get_queued_background_evaluation(
        self,
        session_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.get_queued_background_evaluation(str(session_id))

    def create_background_evaluation(
        self,
        *,
        session_id: str,
        status: str,
        target_turn_id: int,
        source_fingerprint: str,
        source_snapshot_json: str,
        decision: str = "",
        selected_asset_id: str | None = None,
        reason: str = "",
    ) -> models.MediaBackgroundEvaluation:
        self._require_session(session_id)
        return self._repository.create_background_evaluation(
            evaluation_id=uuid.uuid4().hex,
            session_id=str(session_id),
            status=str(status),
            target_turn_id=int(target_turn_id),
            source_fingerprint=str(source_fingerprint),
            source_snapshot_json=str(source_snapshot_json),
            decision=str(decision),
            selected_asset_id=selected_asset_id,
            reason=str(reason),
        )

    def update_queued_background_evaluation(
        self,
        evaluation_id: str,
        *,
        target_turn_id: int,
        source_fingerprint: str,
        source_snapshot_json: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.update_queued_background_evaluation(
            str(evaluation_id),
            target_turn_id=int(target_turn_id),
            source_fingerprint=str(source_fingerprint),
            source_snapshot_json=str(source_snapshot_json),
        )

    def claim_next_background_evaluation(
        self,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.claim_next_background_evaluation()

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
        return self._repository.finish_background_evaluation(
            str(evaluation_id),
            status=str(status),
            decision=str(decision),
            selected_asset_id=selected_asset_id,
            reason=str(reason),
            error_code=str(error_code),
            error_message=str(error_message),
        )

    def transition_background_evaluations(
        self,
        *,
        from_status: str,
        to_status: str,
        error_code: str = "",
        error_message: str = "",
    ) -> list[models.MediaBackgroundEvaluation]:
        return self._repository.transition_background_evaluations(
            from_status=str(from_status),
            to_status=str(to_status),
            error_code=str(error_code),
            error_message=str(error_message),
        )

    def delete_session_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.MediaAssetDeleteResult | None:
        self._require_session(session_id)
        if self._repository.get_gallery_asset(str(session_id), str(asset_id)) is None:
            return None
        return self._repository.delete_asset(str(asset_id))

    def clear_session_runtime(self, session_id: str) -> models.SessionMediaResetResult:
        self._require_session(session_id)
        return self._repository.clear_session_runtime(str(session_id))

    def _require_session(self, session_id: str) -> models.Session:
        session = self._sessions.get(str(session_id))
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return session

    def _require_workspace(self, workspace_id: str) -> models.Workspace:
        workspace = self._workspaces.get(str(workspace_id))
        if workspace is None:
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        return workspace

    def _require_story(self, workspace_id: str, story_id: int) -> models.Story:
        story = self._stories.get(int(story_id))
        if story is None or story.workspace_id != str(workspace_id):
            raise FileNotFoundError(f"Story not found in workspace: {workspace_id}/{story_id}")
        return story

    def _require_library_owner(
        self,
        workspace_id: str,
        *,
        scope: str,
        story_id: int | None,
    ) -> None:
        self._require_workspace(workspace_id)
        if scope not in models.MEDIA_LIBRARY_SCOPES:
            raise ValueError(f"invalid media library scope: {scope}")
        if scope == models.MEDIA_LIBRARY_SCOPE_STORY:
            if story_id is None:
                raise ValueError("story media requires story_id")
            self._require_story(workspace_id, story_id)
        elif story_id is not None:
            raise ValueError("workspace media must not bind a story")

    def _library_bundle(
        self,
        item: models.MediaLibraryItem,
    ) -> models.MediaLibraryAssetBundle | None:
        asset = self._repository.get_asset(item.asset_id)
        if asset is None:
            return None
        blob = self._repository.get_blob(asset.blob_id)
        if blob is None:
            return None
        return models.MediaLibraryAssetBundle(
            item=item,
            asset=asset,
            blob=blob,
            tags=self._repository.list_library_item_tags(item.id),
            usage=self._repository.get_library_usage((asset.id,)).get(
                asset.id,
                models.MediaLibraryUsage(),
            ),
        )

    def _library_bundles(
        self,
        items: Iterable[models.MediaLibraryItem],
    ) -> list[models.MediaLibraryAssetBundle]:
        resolved: list[tuple[models.MediaLibraryItem, models.MediaAsset, models.MediaBlob]] = []
        for item in items:
            asset = self._repository.get_asset(item.asset_id)
            if asset is None:
                continue
            blob = self._repository.get_blob(asset.blob_id)
            if blob is None:
                continue
            resolved.append((item, asset, blob))
        usage = self._repository.get_library_usage(asset.id for _, asset, _ in resolved)
        return [
            models.MediaLibraryAssetBundle(
                item=item,
                asset=asset,
                blob=blob,
                tags=self._repository.list_library_item_tags(item.id),
                usage=usage.get(asset.id, models.MediaLibraryUsage()),
            )
            for item, asset, blob in resolved
        ]


def _validate_library_type(media_type: str) -> None:
    if media_type not in models.MEDIA_LIBRARY_TYPES:
        raise ValueError(f"invalid media library type: {media_type}")


def _validate_library_types(media_types: Iterable[str]) -> None:
    invalid = set(media_types) - set(models.MEDIA_LIBRARY_TYPES)
    if invalid:
        raise ValueError(f"invalid media library types: {', '.join(sorted(invalid))}")


def _search_terms(query: str, tags: tuple[str, ...]) -> tuple[str, ...]:
    raw = str(query).replace(",", " ").replace("，", " ")
    values = [*raw.split(), *(str(tag) for tag in tags)]
    return tuple(dict.fromkeys(value.strip().casefold() for value in values if value.strip()))
