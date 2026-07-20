"""Application-neutral media use cases shared by HTTP and worker adapters."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import ContextManager, Mapping, Protocol, TypeVar

from rpg_data import models
from rpg_media.background_agent import BackgroundMatcher, LLMMediaBackgroundAgent
from rpg_media.brief import VisualBriefPlanner
from rpg_media.errors import (
    MediaAssetInUseDomainError,
    MediaError,
    MediaGenerationCancelled,
    MediaSourceChangedError,
    MediaSourceRangeError,
)
from rpg_media.image_store import WorkspaceImageStore, inspect_image_bytes
from rpg_media.metadata import ImageMetadataAnalyzer, LLMImageMetadataAnalyzer
from rpg_media.providers.catalog import MediaProviderCatalog
from rpg_media.source import (
    build_background_source_snapshot,
    build_source_snapshot,
    parse_background_source_snapshot,
    source_turn_views,
    visible_excerpt,
)
from rpg_media.types import (
    MEDIA_BACKGROUND_DECISION_KEEP,
    MEDIA_BACKGROUND_DECISION_SWITCH,
    MediaBackgroundDecisionKind,
    MediaBackgroundView,
    MediaGenerationRequest,
    MediaImageMetadata,
    MediaProviderDescriptor,
    MediaSourceTurnView,
    SessionGalleryAsset,
    VisualBrief,
    VisualBriefResult,
    mapping_json,
)

logger = logging.getLogger(__name__)

class MediaCatalogPort(Protocol):
    def get_session(self, session_id: str) -> models.Session | None: ...

    def get_workspace_runtime_dir(self, workspace_id: str) -> Path: ...


class MediaDataPort(Protocol):
    """Typed persistence capabilities required by Media use cases."""

    def transaction(self) -> ContextManager[None]: ...

    def list_source_turns(self, session_id: str) -> list[models.MediaSourceTurn]: ...

    def get_source_turns(
        self,
        session_id: str,
        *,
        start_turn_id: int,
        end_turn_id: int,
    ) -> list[models.MediaSourceTurn]: ...

    def get_latest_source_turns(
        self,
        session_id: str,
        *,
        through_turn_id: int,
        limit: int = 3,
    ) -> list[models.MediaSourceTurn]: ...

    def create_job(self, **values: str | int | None) -> models.MediaJob: ...

    def get_job(self, session_id: str, job_id: str) -> models.MediaJob | None: ...

    def get_job_for_worker(self, job_id: str) -> models.MediaJob | None: ...

    def list_jobs(
        self,
        session_id: str,
        *,
        statuses: Iterable[str] | None = None,
    ) -> list[models.MediaJob]: ...

    def claim_next_job(self) -> models.MediaJob | None: ...

    def request_cancel(self, session_id: str, job_id: str) -> models.MediaJob | None: ...

    def mark_cancelled(self, job_id: str) -> models.MediaJob | None: ...

    def mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.MediaJob | None: ...

    def transition_jobs(
        self,
        *,
        from_statuses: Iterable[str],
        to_status: str,
        error_code: str = "",
        error_message: str = "",
    ) -> int: ...

    def complete_job(
        self,
        *,
        job_id: str,
        write: models.MediaJobCompletionWrite,
    ) -> models.MediaJobCompletion | None: ...

    def list_gallery(self, session_id: str) -> list[models.SessionMediaAssetBundle]: ...

    def get_session_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.SessionMediaAssetBundle | None: ...

    def get_workspace_blob_by_hash(
        self,
        workspace_id: str,
        sha256: str,
    ) -> models.MediaBlob | None: ...

    def purge_missing_blob(self, blob_id: str) -> bool: ...

    def list_workspace_blobs(self, workspace_id: str) -> list[models.MediaBlob]: ...

    def reconcile_missing_blobs(
        self,
        workspace_id: str,
        *,
        blob_ids: tuple[str, ...],
        scanned_blobs: int,
    ) -> models.MediaLibraryReconcileResult: ...

    def create_library_asset(
        self,
        **values: str | int | bool | tuple[str, ...] | None,
    ) -> tuple[models.MediaLibraryAssetBundle, bool]: ...

    def list_library_assets(
        self,
        workspace_id: str,
        *,
        scope: str | None = None,
        story_id: int | None = None,
        media_types: tuple[str, ...] = (),
    ) -> list[models.MediaLibraryAssetBundle]: ...

    def list_library_assets_page(
        self,
        workspace_id: str,
        **filters: str | int | tuple[str, ...] | None,
    ) -> models.MediaLibraryPage: ...

    def get_library_facets(self, workspace_id: str) -> models.MediaLibraryFacets: ...

    def get_library_asset(
        self,
        workspace_id: str,
        item_id: str,
    ) -> models.MediaLibraryAssetBundle | None: ...

    def get_library_asset_by_asset_id(
        self,
        asset_id: str,
    ) -> models.MediaLibraryAssetBundle | None: ...

    def get_story_default_asset(
        self,
        story_id: int,
    ) -> models.MediaLibraryAssetBundle | None: ...

    def update_library_asset(
        self,
        workspace_id: str,
        item_id: str,
        **values: str | int | bool | tuple[str, ...] | None,
    ) -> models.MediaLibraryAssetBundle | None: ...

    def delete_library_asset(
        self,
        workspace_id: str,
        item_id: str,
    ) -> models.MediaAssetDeleteResult | None: ...

    def count_background_references(self, asset_id: str) -> int: ...

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
    ) -> list[models.MediaLibraryAssetBundle]: ...

    def get_background(self, session_id: str) -> models.SessionMediaBackground | None: ...

    def get_background_state(self, session_id: str) -> models.SessionMediaBackgroundState: ...

    def set_background(
        self,
        session_id: str,
        asset_id: str,
        *,
        source_mode: str,
    ) -> models.SessionMediaBackground: ...

    def clear_background(self, session_id: str) -> int: ...

    def update_background_state(
        self,
        session_id: str,
        **values: int | str | bool,
    ) -> models.SessionMediaBackgroundState: ...

    def get_display_asset_for_session(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.MediaDisplayAssetBundle | None: ...

    def get_background_evaluation(
        self,
        session_id: str,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def get_background_evaluation_for_worker(
        self,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def get_latest_background_evaluation(
        self,
        session_id: str,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def get_successful_background_evaluation(
        self,
        session_id: str,
        source_fingerprint: str,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def get_active_background_evaluation(
        self,
        session_id: str,
        source_fingerprint: str,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def get_queued_background_evaluation(
        self,
        session_id: str,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def create_background_evaluation(
        self,
        **values: str | int | None,
    ) -> models.MediaBackgroundEvaluation: ...

    def update_queued_background_evaluation(
        self,
        evaluation_id: str,
        *,
        target_turn_id: int,
        source_fingerprint: str,
        source_snapshot_json: str,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def claim_next_background_evaluation(self) -> models.MediaBackgroundEvaluation | None: ...

    def finish_background_evaluation(
        self,
        evaluation_id: str,
        **values: str | None,
    ) -> models.MediaBackgroundEvaluation | None: ...

    def transition_background_evaluations(
        self,
        *,
        from_status: str,
        to_status: str,
        error_code: str = "",
        error_message: str = "",
    ) -> list[models.MediaBackgroundEvaluation]: ...

    def delete_session_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> models.MediaAssetDeleteResult | None: ...


class _BlobBundle(Protocol):
    blob: models.MediaBlob


class SceneAttrsReader(Protocol):
    """Narrow Scene projection required by media background evaluation."""

    def get_attrs(self, session_id: str) -> dict[str, str] | None: ...


_BlobBundleT = TypeVar("_BlobBundleT", bound=_BlobBundle)


class MediaApplicationService:
    def __init__(
        self,
        *,
        data: MediaDataPort,
        catalog: MediaCatalogPort,
        planner: VisualBriefPlanner,
        providers: MediaProviderCatalog,
        image_store: WorkspaceImageStore | None = None,
        status: SceneAttrsReader | None = None,
        background_matcher: BackgroundMatcher | None = None,
        image_analyzer: ImageMetadataAnalyzer | None = None,
    ) -> None:
        self._data = data
        self._catalog = catalog
        self._planner = planner
        self._providers = providers
        self._image_store = image_store or WorkspaceImageStore(catalog)
        self._status = status
        self._background_matcher = background_matcher or LLMMediaBackgroundAgent(
            data,
            asset_exists=self._blob_file_exists,
        )
        self._image_analyzer = image_analyzer or LLMImageMetadataAnalyzer()

    @property
    def default_provider_key(self) -> str:
        return self._providers.default_key

    def list_providers(self) -> list[MediaProviderDescriptor]:
        return self._providers.list()

    def list_source_turns(self, session_id: str) -> list[MediaSourceTurnView]:
        return source_turn_views(self._data.list_source_turns(session_id))

    async def create_visual_brief(
        self,
        session_id: str,
        *,
        start_turn_id: int,
        end_turn_id: int,
    ) -> VisualBriefResult:
        source = build_source_snapshot(
            self._data,
            session_id,
            start_turn_id=start_turn_id,
            end_turn_id=end_turn_id,
        )
        return VisualBriefResult(source=source, brief=await self._planner.plan(source))

    async def analyze_library_image(
        self,
        workspace_id: str,
        *,
        data: bytes,
    ) -> MediaImageMetadata:
        self._catalog.get_workspace_runtime_dir(str(workspace_id))
        inspected = await asyncio.to_thread(inspect_image_bytes, data)
        return await self._image_analyzer.analyze(inspected)

    def create_job(
        self,
        session_id: str,
        *,
        provider_key: str | None,
        start_turn_id: int,
        end_turn_id: int,
        source_fingerprint: str,
        visual_brief: VisualBrief,
        generation_params: Mapping[str, object] | None = None,
    ) -> models.MediaJob:
        selected_provider = provider_key or self.default_provider_key
        self._providers.require_available(selected_provider)
        source = build_source_snapshot(
            self._data,
            session_id,
            start_turn_id=start_turn_id,
            end_turn_id=end_turn_id,
        )
        if source.fingerprint != str(source_fingerprint):
            raise MediaSourceChangedError()
        return self._data.create_job(
            session_id=session_id,
            provider_key=selected_provider,
            source_start_turn_id=source.start_turn_id,
            source_end_turn_id=source.end_turn_id,
            source_fingerprint=source.fingerprint,
            source_snapshot_json=source.snapshot_json,
            visual_brief_json=visual_brief.to_json(),
            generation_params_json=mapping_json(generation_params or {}),
        )

    def retry_job(self, session_id: str, job_id: str) -> models.MediaJob:
        original = self._data.get_job(session_id, job_id)
        if original is None:
            raise FileNotFoundError(f"Media job not found: {job_id}")
        if original.status in models.MEDIA_JOB_ACTIVE_STATUSES:
            raise MediaError(
                "MEDIA_JOB_NOT_RETRYABLE",
                f"Active media job cannot be retried: {job_id}",
            )
        self._providers.require_available(original.provider_key)
        source = build_source_snapshot(
            self._data,
            session_id,
            start_turn_id=original.source_start_turn_id,
            end_turn_id=original.source_end_turn_id,
        )
        if source.fingerprint != original.source_fingerprint:
            raise MediaSourceChangedError()
        return self._data.create_job(
            session_id=session_id,
            provider_key=original.provider_key,
            source_start_turn_id=source.start_turn_id,
            source_end_turn_id=source.end_turn_id,
            source_fingerprint=source.fingerprint,
            source_snapshot_json=source.snapshot_json,
            visual_brief_json=original.visual_brief_json,
            generation_params_json=original.generation_params_json,
            retry_of_job_id=original.id,
        )

    def get_job(self, session_id: str, job_id: str) -> models.MediaJob | None:
        return self._data.get_job(session_id, job_id)

    def list_active_jobs(self, session_id: str) -> list[models.MediaJob]:
        return self._data.list_jobs(
            session_id,
            statuses=models.MEDIA_JOB_ACTIVE_STATUSES,
        )

    def list_jobs(self, session_id: str) -> list[models.MediaJob]:
        return self._data.list_jobs(session_id)

    def cancel_job(self, session_id: str, job_id: str) -> models.MediaJob | None:
        return self._data.request_cancel(session_id, job_id)

    def claim_next_job(self) -> models.MediaJob | None:
        return self._data.claim_next_job()

    def interrupt_active_jobs(self) -> int:
        return self._data.transition_jobs(
            from_statuses=(
                models.MEDIA_JOB_STATUS_RUNNING,
                models.MEDIA_JOB_STATUS_CANCELLING,
            ),
            to_status=models.MEDIA_JOB_STATUS_INTERRUPTED,
            error_code="MEDIA_JOB_INTERRUPTED",
            error_message="Media service restarted before the job finished.",
        )

    def claim_next_background_evaluation(
        self,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._data.claim_next_background_evaluation()

    def interrupt_background_evaluations(
        self,
    ) -> list[models.MediaBackgroundEvaluation]:
        interrupted = self._data.transition_background_evaluations(
            from_status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING,
            to_status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_INTERRUPTED,
            error_code="MEDIA_BACKGROUND_EVALUATION_INTERRUPTED",
            error_message="Media service restarted during background evaluation.",
        )
        for evaluation in interrupted:
            if self._data.get_queued_background_evaluation(evaluation.session_id) is not None:
                continue
            self._data.create_background_evaluation(
                session_id=evaluation.session_id,
                status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
                target_turn_id=evaluation.target_turn_id,
                source_fingerprint=evaluation.source_fingerprint,
                source_snapshot_json=evaluation.source_snapshot_json,
            )
        return interrupted

    def list_gallery(self, session_id: str) -> list[SessionGalleryAsset]:
        return [
            SessionGalleryAsset(
                bundle=bundle,
                source_stale=self._is_gallery_source_stale(bundle),
                media_type=self._gallery_media_type(bundle.asset.id),
            )
            for bundle in self._existing_file_bundles(
                self._data.list_gallery(session_id)
            )
        ]

    def get_session_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> SessionGalleryAsset | None:
        bundle = self._data.get_session_asset(session_id, asset_id)
        if bundle is None or not self._blob_file_available(bundle.blob):
            return None
        return SessionGalleryAsset(
            bundle=bundle,
            source_stale=self._is_gallery_source_stale(bundle),
            media_type=self._gallery_media_type(bundle.asset.id),
        )

    def _gallery_media_type(self, asset_id: str) -> str:
        library = self._data.get_library_asset_by_asset_id(asset_id)
        return (
            library.item.media_type
            if library is not None
            else models.MEDIA_LIBRARY_TYPE_BACKGROUND
        )

    def get_background(self, session_id: str) -> MediaBackgroundView | None:
        session = self._catalog.get_session(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        state = self._data.get_background_state(session_id)
        background = self._data.get_background(session_id)
        if background is not None:
            asset = self._data.get_display_asset_for_session(session_id, background.asset_id)
            if asset is not None and not self._blob_file_available(asset.blob):
                asset = None
                background = None
        if background is not None:
            if asset is None:
                return MediaBackgroundView(
                    background=None,
                    asset=None,
                    source_mode="none",
                    manual_locked=False,
                    revision_token=f"none:{state.version}",
                    state=state,
                )
            return MediaBackgroundView(
                background=background,
                asset=asset,
                source_mode=background.source_mode,
                manual_locked=(
                    background.source_mode == models.MEDIA_BACKGROUND_SOURCE_MANUAL
                ),
                revision_token=f"{background.source_mode}:{background.version}:{asset.asset.id}",
                state=state,
            )
        latest_turns = self._data.get_latest_source_turns(
            session_id,
            through_turn_id=2**63 - 1,
            limit=1,
        )
        latest_turn_id = latest_turns[-1].turn_id if latest_turns else 0
        if state.auto_suppressed and latest_turn_id <= state.suppressed_through_turn_id:
            return MediaBackgroundView(
                background=None,
                asset=None,
                source_mode="none",
                manual_locked=False,
                revision_token=f"none:{state.version}",
                state=state,
            )
        default = self._data.get_story_default_asset(session.story_id)
        if default is not None and not self._blob_file_available(default.blob):
            default = None
        if default is None:
            return MediaBackgroundView(
                background=None,
                asset=None,
                source_mode="none",
                manual_locked=False,
                revision_token=f"none:{state.version}",
                state=state,
            )
        return MediaBackgroundView(
            background=None,
            asset=models.MediaDisplayAssetBundle(
                asset=default.asset,
                blob=default.blob,
                library_item=default.item,
                tags=default.tags,
            ),
            source_mode="story_default",
            manual_locked=False,
            revision_token=f"story_default:{default.item.id}:{default.item.version}",
            state=state,
        )

    def set_background(self, session_id: str, asset_id: str) -> MediaBackgroundView:
        session = self._catalog.get_session(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        gallery = self._data.get_session_asset(session_id, asset_id)
        library = self._data.get_library_asset_by_asset_id(asset_id)
        library_allowed = (
            library is not None
            and library.item.scope == models.MEDIA_LIBRARY_SCOPE_STORY
            and library.item.story_id == session.story_id
            and library.item.media_type == models.MEDIA_LIBRARY_TYPE_BACKGROUND
        )
        gallery_allowed = (
            gallery is not None
            and (
                library is None
                or library.item.media_type == models.MEDIA_LIBRARY_TYPE_BACKGROUND
            )
        )
        candidate_blob = (
            gallery.blob
            if gallery is not None
            else library.blob if library is not None else None
        )
        if (
            not gallery_allowed
            and not library_allowed
        ) or candidate_blob is None or not self._blob_file_available(candidate_blob):
            raise FileNotFoundError(f"Media asset content not found: {asset_id}")
        self._data.set_background(
            session_id,
            asset_id,
            source_mode=models.MEDIA_BACKGROUND_SOURCE_MANUAL,
        )
        background = self.get_background(session_id)
        if background is None or background.asset is None:
            raise RuntimeError(f"session background asset disappeared: {asset_id}")
        return background

    def clear_background(self, session_id: str) -> bool:
        latest = self._data.get_latest_source_turns(
            session_id,
            through_turn_id=2**63 - 1,
            limit=1,
        )
        suppressed_through = latest[-1].turn_id if latest else 0
        with self._data.transaction():
            state = self._data.get_background_state(session_id)
            self._data.update_background_state(
                session_id,
                auto_suppressed=True,
                suppressed_through_turn_id=suppressed_through,
                desired_turn_id=0,
                desired_source_fingerprint="",
                latest_observed_turn_id=max(
                    suppressed_through,
                    state.latest_observed_turn_id,
                ),
            )
            return bool(self._data.clear_background(session_id))

    async def upload_library_asset(
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
        data: bytes,
    ) -> models.MediaLibraryAssetBundle:
        normalized_title, normalized_description, normalized_tags = (
            _prepare_library_metadata(title, description, tags)
        )
        _validate_library_policy(
            scope=scope,
            media_type=media_type,
            is_default=is_default,
        )
        stored = await asyncio.to_thread(self._image_store.put, workspace_id, data)
        try:
            bundle, _ = self._data.create_library_asset(
                workspace_id=workspace_id,
                scope=scope,
                story_id=story_id,
                media_type=media_type,
                title=normalized_title,
                description=normalized_description,
                tags=normalized_tags,
                is_default=is_default,
                sha256=stored.image.sha256,
                canonical_ext=stored.image.canonical_ext,
                mime_type=stored.image.mime_type,
                byte_size=stored.image.byte_size,
                relative_path=stored.relative_path,
                visual_brief_json=VisualBrief(
                    scene_description=normalized_description
                ).to_json(),
            )
            return bundle
        except Exception:
            await self._discard_unreferenced_file(workspace_id, stored)
            raise

    def list_library_assets(
        self,
        workspace_id: str,
        *,
        scope: str | None = None,
        story_id: int | None = None,
        media_types: tuple[str, ...] = (),
    ) -> list[models.MediaLibraryAssetBundle]:
        return self._existing_file_bundles(
            self._data.list_library_assets(
                workspace_id,
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
        result = self._data.list_library_assets_page(
            workspace_id,
            query=query,
            media_types=media_types,
            tags=tags,
            scope=scope,
            story_id=story_id,
            origins=origins,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        visible = tuple(self._existing_file_bundles(result.items))
        return models.MediaLibraryPage(
            items=visible,
            page=result.page,
            page_size=result.page_size,
            total=result.total,
        )

    def get_library_facets(self, workspace_id: str) -> models.MediaLibraryFacets:
        return self._data.get_library_facets(workspace_id)

    async def reconcile_library_assets(
        self,
        workspace_id: str,
    ) -> models.MediaLibraryReconcileResult:
        blobs = self._data.list_workspace_blobs(workspace_id)
        missing_blob_ids = await asyncio.to_thread(
            lambda: tuple(
                blob.id
                for blob in blobs
                if not self._blob_file_exists(blob)
            )
        )
        return self._data.reconcile_missing_blobs(
            workspace_id,
            blob_ids=missing_blob_ids,
            scanned_blobs=len(blobs),
        )

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
        normalized_title, normalized_description, normalized_tags = (
            _prepare_library_metadata(title, description, tags)
        )
        _validate_library_policy(
            scope=scope,
            media_type=media_type,
            is_default=is_default,
        )
        with self._data.transaction():
            existing = self._data.get_library_asset(workspace_id, item_id)
            if existing is None:
                return None
            changes_binding = (
                media_type != models.MEDIA_LIBRARY_TYPE_BACKGROUND
                or scope != existing.item.scope
                or story_id != existing.item.story_id
            )
            if changes_binding and self._data.count_background_references(
                existing.asset.id
            ):
                raise MediaAssetInUseDomainError(item_id)
            return self._data.update_library_asset(
                workspace_id,
                item_id,
                scope=scope,
                story_id=story_id,
                media_type=media_type,
                title=normalized_title,
                description=normalized_description,
                tags=normalized_tags,
                is_default=is_default,
            )

    def delete_library_asset(self, workspace_id: str, item_id: str) -> bool:
        with self._data.transaction():
            existing = self._data.get_library_asset(workspace_id, item_id)
            if existing is None:
                return False
            if self._data.count_background_references(existing.asset.id):
                raise MediaAssetInUseDomainError(item_id)
            deleted = self._data.delete_library_asset(workspace_id, item_id)
        if deleted is None:
            return False
        if deleted.blob_deleted:
            self._image_store.delete_blob_file(deleted.blob)
        return True

    def batch_update_library_assets(
        self,
        workspace_id: str,
        *,
        item_ids: tuple[str, ...],
        media_type: str | None = None,
        add_tags: tuple[str, ...] = (),
        remove_tags: tuple[str, ...] = (),
    ) -> models.MediaLibraryBatchResult:
        succeeded: list[str] = []
        failed: list[models.MediaLibraryBatchFailure] = []
        remove_keys = {tag.strip().casefold() for tag in remove_tags if tag.strip()}
        for item_id in item_ids:
            try:
                existing = self._data.get_library_asset(workspace_id, item_id)
                if existing is None:
                    raise FileNotFoundError(f"Media library item not found: {item_id}")
                merged = {
                    tag.casefold(): tag
                    for tag in existing.tags
                    if tag.casefold() not in remove_keys
                }
                for tag in add_tags:
                    normalized = tag.strip()
                    if normalized:
                        merged[normalized.casefold()] = normalized
                next_type = media_type or existing.item.media_type
                updated = self.update_library_asset(
                    workspace_id,
                    item_id,
                    scope=existing.item.scope,
                    story_id=existing.item.story_id,
                    media_type=next_type,
                    title=existing.item.title,
                    description=existing.item.description,
                    tags=tuple(merged.values()),
                    is_default=(
                        existing.item.is_default
                        and next_type == models.MEDIA_LIBRARY_TYPE_BACKGROUND
                    ),
                )
                if updated is None:
                    raise FileNotFoundError(f"Media library item not found: {item_id}")
                succeeded.append(item_id)
            except FileNotFoundError as exc:
                failed.append(models.MediaLibraryBatchFailure(
                    item_id=item_id,
                    error_code="MEDIA_LIBRARY_ITEM_NOT_FOUND",
                    message=str(exc),
                ))
            except MediaAssetInUseDomainError as error:
                failed.append(models.MediaLibraryBatchFailure(
                    item_id=item_id,
                    error_code=error.code,
                    message=str(error),
                ))
            except ValueError as exc:
                failed.append(models.MediaLibraryBatchFailure(
                    item_id=item_id,
                    error_code="MEDIA_LIBRARY_UPDATE_INVALID",
                    message=str(exc),
                ))
        return models.MediaLibraryBatchResult(
            succeeded_item_ids=tuple(succeeded),
            failed=tuple(failed),
        )

    def batch_delete_library_assets(
        self,
        workspace_id: str,
        *,
        item_ids: tuple[str, ...],
    ) -> models.MediaLibraryBatchResult:
        succeeded: list[str] = []
        failed: list[models.MediaLibraryBatchFailure] = []
        for item_id in item_ids:
            try:
                if not self.delete_library_asset(workspace_id, item_id):
                    raise FileNotFoundError(f"Media library item not found: {item_id}")
                succeeded.append(item_id)
            except MediaAssetInUseDomainError as exc:
                failed.append(models.MediaLibraryBatchFailure(
                    item_id=item_id,
                    error_code=exc.code,
                    message=str(exc),
                ))
            except FileNotFoundError as exc:
                failed.append(models.MediaLibraryBatchFailure(
                    item_id=item_id,
                    error_code="MEDIA_LIBRARY_ITEM_NOT_FOUND",
                    message=str(exc),
                ))
        return models.MediaLibraryBatchResult(
            succeeded_item_ids=tuple(succeeded),
            failed=tuple(failed),
        )

    def resolve_library_asset_content(
        self,
        workspace_id: str,
        item_id: str,
    ) -> tuple[Path, str]:
        bundle = self._data.get_library_asset(workspace_id, item_id)
        if bundle is None or not self._blob_file_available(bundle.blob):
            raise FileNotFoundError(f"Media library item not found: {item_id}")
        return self._image_store.resolve_blob_path(bundle.blob), bundle.blob.mime_type

    def queue_background_evaluation(
        self,
        session_id: str,
        *,
        observed_turn_id: int,
    ) -> models.MediaBackgroundEvaluation:
        session = self._catalog.get_session(session_id)
        if session is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        latest = self._data.get_latest_source_turns(
            session_id,
            through_turn_id=2**63 - 1,
            limit=1,
        )
        if not latest:
            raise MediaSourceRangeError("session has no committed media source turn")
        target_turn_id = latest[-1].turn_id
        if int(observed_turn_id) > target_turn_id:
            raise MediaSourceRangeError("observed turn has not been committed")
        state = self._data.get_background_state(session_id)
        current_view = self.get_background(session_id)
        current_asset = current_view.asset if current_view is not None else None
        source = build_background_source_snapshot(
            self._data,
            session,
            target_turn_id=target_turn_id,
            scene_attrs=(
                self._status.get_attrs(session_id)
                if self._status is not None
                else None
            ),
            current_asset=current_asset,
            state=state,
        )
        observed = int(observed_turn_id)
        if observed <= 0:
            raise MediaSourceRangeError("background evaluation turn id must be positive")
        with self._data.transaction():
            state = self._data.get_background_state(session_id)
            background = self._data.get_background(session_id)
            self._data.update_background_state(
                session_id,
                latest_observed_turn_id=max(
                    state.latest_observed_turn_id,
                    target_turn_id,
                ),
                latest_source_fingerprint=source.fingerprint,
            )
            if (
                background is not None
                and background.source_mode == models.MEDIA_BACKGROUND_SOURCE_MANUAL
            ):
                return self._data.create_background_evaluation(
                    session_id=session_id,
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL,
                    target_turn_id=target_turn_id,
                    source_fingerprint=source.fingerprint,
                    source_snapshot_json=source.snapshot_json,
                    decision=MEDIA_BACKGROUND_DECISION_KEEP,
                    reason="manual background is locked",
                )
            if state.auto_suppressed and target_turn_id <= state.suppressed_through_turn_id:
                return self._data.create_background_evaluation(
                    session_id=session_id,
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED,
                    target_turn_id=target_turn_id,
                    source_fingerprint=source.fingerprint,
                    source_snapshot_json=source.snapshot_json,
                    decision=MEDIA_BACKGROUND_DECISION_KEEP,
                    reason="automatic background is suppressed until a newer turn",
                )
            successful = self._data.get_successful_background_evaluation(
                session_id,
                source.fingerprint,
            )
            if successful is not None:
                return successful
            active = self._data.get_active_background_evaluation(
                session_id,
                source.fingerprint,
            )
            if active is not None:
                self._data.update_background_state(
                    session_id,
                    desired_turn_id=target_turn_id,
                    desired_source_fingerprint=source.fingerprint,
                )
                return active
            queued = self._data.get_queued_background_evaluation(session_id)
            if queued is not None:
                updated = self._data.update_queued_background_evaluation(
                    queued.id,
                    target_turn_id=target_turn_id,
                    source_fingerprint=source.fingerprint,
                    source_snapshot_json=source.snapshot_json,
                )
                if updated is not None:
                    self._data.update_background_state(
                        session_id,
                        desired_turn_id=target_turn_id,
                        desired_source_fingerprint=source.fingerprint,
                    )
                    return updated
            evaluation = self._data.create_background_evaluation(
                session_id=session_id,
                status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
                target_turn_id=target_turn_id,
                source_fingerprint=source.fingerprint,
                source_snapshot_json=source.snapshot_json,
            )
            self._data.update_background_state(
                session_id,
                desired_turn_id=target_turn_id,
                desired_source_fingerprint=source.fingerprint,
            )
            return evaluation

    def get_background_evaluation(
        self,
        session_id: str,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._data.get_background_evaluation(session_id, evaluation_id)

    def get_latest_background_evaluation(
        self,
        session_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._data.get_latest_background_evaluation(session_id)

    async def execute_background_evaluation(
        self,
        evaluation_id: str,
    ) -> models.MediaBackgroundEvaluation | None:
        evaluation = self._data.get_background_evaluation_for_worker(evaluation_id)
        if evaluation is None or evaluation.status != models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING:
            return evaluation
        try:
            source = parse_background_source_snapshot(evaluation.source_snapshot_json)
            if source.fingerprint != evaluation.source_fingerprint:
                raise ValueError("media background source fingerprint changed")
            self.list_library_assets(source.workspace_id)
            decision = await self._background_matcher.decide(source)
            return self._apply_background_decision(
                evaluation,
                decision=decision.decision,
                selected_asset_id=decision.asset_id,
                reason=decision.reason,
            )
        except Exception as exc:
            return self._data.finish_background_evaluation(
                evaluation.id,
                status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_FAILED,
                error_code=(
                    exc.code if isinstance(exc, MediaError) else "MEDIA_BACKGROUND_MATCH_FAILED"
                ),
                error_message=str(exc),
            )

    def _apply_background_decision(
        self,
        evaluation: models.MediaBackgroundEvaluation,
        *,
        decision: MediaBackgroundDecisionKind,
        selected_asset_id: str | None,
        reason: str,
    ) -> models.MediaBackgroundEvaluation | None:
        if decision not in {
            MEDIA_BACKGROUND_DECISION_KEEP,
            MEDIA_BACKGROUND_DECISION_SWITCH,
        }:
            raise ValueError(f"invalid media background decision: {decision}")
        with self._data.transaction():
            current = self._data.get_background_evaluation_for_worker(evaluation.id)
            if current is None:
                return None
            if current.status != models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING:
                return current
            state = self._data.get_background_state(current.session_id)
            if (
                state.desired_turn_id != current.target_turn_id
                or state.desired_source_fingerprint != current.source_fingerprint
            ):
                return self._data.finish_background_evaluation(
                    current.id,
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED,
                    decision=decision,
                    selected_asset_id=selected_asset_id,
                    reason="a newer background evaluation superseded this result",
                )
            background = self._data.get_background(current.session_id)
            if (
                background is not None
                and background.source_mode == models.MEDIA_BACKGROUND_SOURCE_MANUAL
            ):
                return self._data.finish_background_evaluation(
                    current.id,
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL,
                    decision=MEDIA_BACKGROUND_DECISION_KEEP,
                    reason="manual background was selected during evaluation",
                )
            if decision == MEDIA_BACKGROUND_DECISION_SWITCH:
                if not selected_asset_id:
                    raise ValueError("switch background decision requires asset_id")
                session = self._catalog.get_session(current.session_id)
                if session is None:
                    raise FileNotFoundError(f"Session not found: {current.session_id}")
                library = self._data.get_library_asset_by_asset_id(selected_asset_id)
                allowed = (
                    library is not None
                    and library.item.media_type == models.MEDIA_LIBRARY_TYPE_BACKGROUND
                    and (
                        (
                            library.item.scope == models.MEDIA_LIBRARY_SCOPE_STORY
                            and library.item.story_id == session.story_id
                        )
                        or library.item.scope == models.MEDIA_LIBRARY_SCOPE_WORKSPACE
                    )
                )
                if not allowed:
                    raise PermissionError(
                        "background asset is outside the session media pools: "
                        f"{selected_asset_id}"
                    )
                self._data.set_background(
                    current.session_id,
                    selected_asset_id,
                    source_mode=models.MEDIA_BACKGROUND_SOURCE_AUTO,
                )
            self._data.update_background_state(
                current.session_id,
                last_applied_turn_id=current.target_turn_id,
                last_applied_fingerprint=current.source_fingerprint,
                last_decision=decision,
                last_reason=reason,
                auto_suppressed=False,
                suppressed_through_turn_id=0,
            )
            return self._data.finish_background_evaluation(
                current.id,
                status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED,
                decision=decision,
                selected_asset_id=selected_asset_id,
                reason=reason,
            )

    def delete_asset(self, session_id: str, asset_id: str) -> bool:
        with self._data.transaction():
            existing = self._data.get_session_asset(session_id, asset_id)
            if existing is None:
                return False
            if self._data.count_background_references(asset_id):
                raise MediaAssetInUseDomainError(asset_id)
            deleted = self._data.delete_session_asset(session_id, asset_id)
        if deleted is None:
            return False
        if deleted.blob_deleted:
            self._image_store.delete_blob_file(deleted.blob)
        return True

    def resolve_asset_content(self, session_id: str, asset_id: str) -> tuple[Path, str]:
        bundle = self._data.get_display_asset_for_session(session_id, asset_id)
        if bundle is None or not self._blob_file_available(bundle.blob):
            raise FileNotFoundError(f"Media asset not found: {asset_id}")
        return self._image_store.resolve_blob_path(bundle.blob), bundle.blob.mime_type

    async def execute_job(self, job_id: str) -> models.MediaJob | None:
        job = self._data.get_job_for_worker(job_id)
        if job is None or job.status != models.MEDIA_JOB_STATUS_RUNNING:
            return job
        session = self._catalog.get_session(job.session_id)
        if session is None:
            return None
        stored = None

        async def is_cancelled() -> bool:
            current = self._data.get_job_for_worker(job.id)
            return current is None or current.status in {
                models.MEDIA_JOB_STATUS_CANCELLING,
                models.MEDIA_JOB_STATUS_CANCELLED,
                models.MEDIA_JOB_STATUS_INTERRUPTED,
            }

        try:
            provider = self._providers.require_available(job.provider_key)
            brief = VisualBrief.from_json(job.visual_brief_json)
            raw_params: object = json.loads(job.generation_params_json or "{}")
            if not isinstance(raw_params, dict):
                raise ValueError("media generation params must be a JSON object")
            generated = await provider.generate(
                MediaGenerationRequest(
                    job_id=job.id,
                    session_id=job.session_id,
                    prompt=brief.to_prompt(),
                    visual_brief=brief,
                    generation_params=raw_params,
                ),
                is_cancelled=is_cancelled,
            )
            if await is_cancelled():
                raise MediaGenerationCancelled()
            stored = await asyncio.to_thread(
                self._image_store.put,
                session.workspace_id,
                generated.data,
            )
            if await is_cancelled():
                raise MediaGenerationCancelled()
            library_title, library_description, library_tags = (
                _prepare_library_metadata(
                    visible_excerpt(
                        brief.scene_description,
                        segment_length=96,
                    ),
                    brief.to_prompt(),
                    _generated_library_tags(brief, job.provider_key),
                )
            )
            completion = self._data.complete_job(
                job_id=job.id,
                write=models.MediaJobCompletionWrite(
                    workspace_id=session.workspace_id,
                    story_id=session.story_id,
                    sha256=stored.image.sha256,
                    canonical_ext=stored.image.canonical_ext,
                    mime_type=stored.image.mime_type,
                    byte_size=stored.image.byte_size,
                    relative_path=stored.relative_path,
                    provider_asset_id=generated.provider_asset_id,
                    metadata_json=mapping_json(generated.metadata),
                    library_title=library_title,
                    library_description=library_description,
                    library_tags=library_tags,
                ),
            )
            if completion is None:
                await self._discard_unreferenced_file(session.workspace_id, stored)
                current = self._data.get_job_for_worker(job.id)
                if current is not None and current.status == models.MEDIA_JOB_STATUS_CANCELLING:
                    return self._data.mark_cancelled(job.id)
                return current
            return completion.job
        except MediaGenerationCancelled:
            if stored is not None:
                await self._discard_unreferenced_file(session.workspace_id, stored)
            return self._data.mark_cancelled(job.id)
        except Exception as exc:
            if stored is not None:
                await self._discard_unreferenced_file(session.workspace_id, stored)
            current = self._data.get_job_for_worker(job.id)
            if current is None:
                return None
            if current.status == models.MEDIA_JOB_STATUS_CANCELLING:
                return self._data.mark_cancelled(job.id)
            code = exc.code if isinstance(exc, MediaError) else "MEDIA_GENERATION_FAILED"
            return self._data.mark_failed(
                job.id,
                error_code=code,
                error_message=str(exc),
            )

    def _existing_file_bundles(
        self,
        bundles: Iterable[_BlobBundleT],
    ) -> list[_BlobBundleT]:
        return [bundle for bundle in bundles if self._blob_file_exists(bundle.blob)]

    def _blob_file_exists(self, blob: models.MediaBlob) -> bool:
        path: Path | None = None
        try:
            path = self._image_store.resolve_blob_path(blob)
            if path.is_file():
                return True
        except (OSError, ValueError) as exc:
            logger.warning(
                "ignoring media blob with an invalid workspace path "
                "blob_id=%s workspace_id=%s relative_path=%s error=%s",
                blob.id,
                blob.workspace_id,
                blob.relative_path,
                exc,
            )
            return False
        logger.warning(
            "ignoring media blob whose workspace file is missing "
            "blob_id=%s workspace_id=%s path=%s",
            blob.id,
            blob.workspace_id,
            path,
        )
        return False

    def _blob_file_available(self, blob: models.MediaBlob) -> bool:
        if self._blob_file_exists(blob):
            return True
        logger.warning(
            "pruning unavailable media blob after a direct asset read "
            "blob_id=%s workspace_id=%s",
            blob.id,
            blob.workspace_id,
        )
        self._data.purge_missing_blob(blob.id)
        return False

    def _is_gallery_source_stale(
        self,
        bundle: models.SessionMediaAssetBundle,
    ) -> bool:
        item = bundle.gallery_item
        try:
            current = build_source_snapshot(
                self._data,
                item.session_id,
                start_turn_id=item.source_start_turn_id,
                end_turn_id=item.source_end_turn_id,
            )
        except (FileNotFoundError, MediaSourceRangeError):
            return True
        return current.fingerprint != item.source_fingerprint

    async def _discard_unreferenced_file(
        self,
        workspace_id: str,
        stored,  # noqa: ANN001
    ) -> None:
        if not stored.file_created:
            return
        if self._data.get_workspace_blob_by_hash(workspace_id, stored.image.sha256) is not None:
            return
        await asyncio.to_thread(
            self._image_store.delete_stored_file,
            workspace_id,
            stored,
        )


def _generated_library_tags(
    brief: VisualBrief,
    provider_key: str,
) -> tuple[str, ...]:
    values = (
        "generated",
        str(provider_key),
        brief.aspect_ratio,
        *brief.subjects,
        brief.environment,
        brief.style,
        brief.mood_lighting,
    )
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = visible_excerpt(str(value), segment_length=64).strip()
        normalized = tag.casefold()
        if not tag or normalized in seen:
            continue
        seen.add(normalized)
        tags.append(tag)
        if len(tags) == 20:
            break
    return tuple(tags)


def _prepare_library_metadata(
    title: str,
    description: str,
    tags: tuple[str, ...],
) -> tuple[str, str, tuple[str, ...]]:
    normalized_title = str(title).strip()
    normalized_description = str(description).strip()
    if not normalized_title or not normalized_description:
        raise ValueError("media library title and description are required")
    normalized_tags = tuple(dict.fromkeys(
        str(tag).strip().casefold()
        for tag in tags
        if str(tag).strip()
    ))
    if not 1 <= len(normalized_tags) <= 20:
        raise ValueError("media library requires between 1 and 20 tags")
    return normalized_title, normalized_description, normalized_tags


def _validate_library_policy(
    *,
    scope: str,
    media_type: str,
    is_default: bool,
) -> None:
    if scope not in models.MEDIA_LIBRARY_SCOPES:
        raise ValueError(f"invalid media library scope: {scope}")
    if media_type not in models.MEDIA_LIBRARY_TYPES:
        raise ValueError(f"invalid media library type: {media_type}")
    if is_default and (
        scope != models.MEDIA_LIBRARY_SCOPE_STORY
        or media_type != models.MEDIA_LIBRARY_TYPE_BACKGROUND
    ):
        raise ValueError("only story background media can be a default")
