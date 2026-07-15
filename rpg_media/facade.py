"""Application-neutral media use cases shared by HTTP and worker adapters."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Mapping

from rpg_data import models
from rpg_data.services.catalog import CatalogService
from rpg_data.services.gateway import DataServiceGateway
from rpg_data.services.media import MediaAssetInUseError, MediaDataService, MediaSourceRangeError
from rpg_media.brief import DemoVisualBriefPlanner, VisualBriefPlanner
from rpg_media.errors import (
    MediaAssetInUseDomainError,
    MediaError,
    MediaGenerationCancelled,
    MediaProviderUnavailableError,
    MediaSourceChangedError,
)
from rpg_media.image_store import WorkspaceImageStore
from rpg_media.providers.catalog import MediaProviderCatalog, build_provider_catalog
from rpg_media.settings import RPGMediaSettings, settings
from rpg_media.source import build_source_snapshot, source_turn_views
from rpg_media.types import (
    MediaBackgroundView,
    MediaGenerationRequest,
    MediaProviderDescriptor,
    MediaSourceTurnView,
    SessionGalleryAsset,
    VisualBrief,
    VisualBriefResult,
    mapping_json,
)


class MediaFacade:
    def __init__(
        self,
        *,
        data: MediaDataService,
        catalog: CatalogService,
        planner: VisualBriefPlanner,
        providers: MediaProviderCatalog,
        image_store: WorkspaceImageStore | None = None,
    ) -> None:
        self._data = data
        self._catalog = catalog
        self._planner = planner
        self._providers = providers
        self._image_store = image_store or WorkspaceImageStore(catalog)

    @classmethod
    def from_gateway(
        cls,
        gateway: DataServiceGateway,
        *,
        media_settings: RPGMediaSettings | None = None,
        providers: MediaProviderCatalog | None = None,
        planner: VisualBriefPlanner | None = None,
    ) -> "MediaFacade":
        configured = media_settings or settings
        return cls(
            data=gateway.media,
            catalog=gateway.catalog,
            planner=planner or DemoVisualBriefPlanner(configured.demo_brief),
            providers=providers or build_provider_catalog(configured.providers),
        )

    @property
    def default_provider_key(self) -> str:
        return self._providers.default_key

    def list_providers(self) -> list[MediaProviderDescriptor]:
        return self._providers.list()

    def list_source_turns(self, session_id: str) -> list[MediaSourceTurnView]:
        return source_turn_views(self._data.list_source_turns(session_id))

    def create_visual_brief(
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
        return VisualBriefResult(source=source, brief=self._planner.plan(source))

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

    def list_gallery(self, session_id: str) -> list[SessionGalleryAsset]:
        return [
            SessionGalleryAsset(
                bundle=bundle,
                source_stale=self._is_gallery_source_stale(bundle),
            )
            for bundle in self._data.list_gallery(session_id)
        ]

    def get_session_asset(
        self,
        session_id: str,
        asset_id: str,
    ) -> SessionGalleryAsset | None:
        bundle = self._data.get_session_asset(session_id, asset_id)
        if bundle is None:
            return None
        return SessionGalleryAsset(
            bundle=bundle,
            source_stale=self._is_gallery_source_stale(bundle),
        )

    def get_background(self, session_id: str) -> MediaBackgroundView | None:
        background = self._data.get_background(session_id)
        if background is None:
            return None
        asset = self.get_session_asset(session_id, background.asset_id)
        if asset is None:
            return None
        return MediaBackgroundView(background=background, asset=asset)

    def set_background(self, session_id: str, asset_id: str) -> MediaBackgroundView:
        background = self._data.set_background(session_id, asset_id)
        asset = self.get_session_asset(session_id, asset_id)
        if asset is None:
            raise RuntimeError(f"session background asset disappeared: {asset_id}")
        return MediaBackgroundView(background=background, asset=asset)

    def clear_background(self, session_id: str) -> bool:
        return bool(self._data.clear_background(session_id))

    def delete_asset(self, session_id: str, asset_id: str) -> bool:
        try:
            deleted = self._data.delete_session_asset(session_id, asset_id)
        except MediaAssetInUseError as exc:
            raise MediaAssetInUseDomainError(asset_id) from exc
        if deleted is None:
            return False
        if deleted.blob_deleted:
            self._image_store.delete_blob_file(deleted.blob)
        return True

    def resolve_asset_content(self, session_id: str, asset_id: str) -> tuple[Path, str]:
        bundle = self._data.get_session_asset(session_id, asset_id)
        if bundle is None:
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
            completion = self._data.complete_job(
                job_id=job.id,
                sha256=stored.image.sha256,
                canonical_ext=stored.image.canonical_ext,
                mime_type=stored.image.mime_type,
                byte_size=stored.image.byte_size,
                relative_path=stored.relative_path,
                provider_asset_id=generated.provider_asset_id,
                metadata_json=mapping_json(generated.metadata),
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
