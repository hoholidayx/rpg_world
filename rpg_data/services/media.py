"""Media persistence facade shared by the media process and Agent reset flow."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from peewee import Database

from rpg_data import models
from rpg_data.repositories.media_repo import MediaRepository
from rpg_data.repositories.session_repo import SessionRepository
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository

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
        self._stories = StoryRepository(database)
        self._workspaces = WorkspaceRepository(database)

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

    def get_latest_source_turns(
        self,
        session_id: str,
        *,
        through_turn_id: int,
        limit: int = 3,
    ) -> list[models.MediaSourceTurn]:
        self._require_session(session_id)
        if int(through_turn_id) <= 0:
            raise MediaSourceRangeError("media source turn id must be positive")
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
        library_title: str = "Generated image",
        library_description: str | None = None,
        library_tags: tuple[str, ...] = ("generated",),
    ) -> models.MediaJobCompletion | None:
        job = self._repository.get_job(str(job_id))
        if job is None:
            return None
        session = self._sessions.get(job.session_id)
        if session is None:
            return None
        normalized_title, normalized_description, normalized_tags = _validate_library_metadata(
            library_title,
            library_description or job.visual_brief_json,
            library_tags,
        )
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
            library_item_id=uuid.uuid4().hex,
            story_id=session.story_id,
            library_title=normalized_title,
            library_description=normalized_description,
            library_tags=normalized_tags,
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
        if scope != models.MEDIA_LIBRARY_SCOPE_STORY and is_default:
            raise ValueError("workspace fallback media cannot be a story default")
        normalized_title, normalized_description, normalized_tags = _validate_library_metadata(
            title,
            description,
            tags,
        )
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
            title=normalized_title,
            description=normalized_description,
            tags=normalized_tags,
            is_default=bool(is_default),
            visual_brief_json=str(visual_brief_json),
        )
        return (
            models.MediaLibraryAssetBundle(
                item=item,
                asset=asset,
                blob=blob,
                tags=normalized_tags,
            ),
            blob_created,
        )

    def list_library_assets(
        self,
        workspace_id: str,
        *,
        scope: str | None = None,
        story_id: int | None = None,
    ) -> list[models.MediaLibraryAssetBundle]:
        self._require_workspace(workspace_id)
        if scope is not None and scope not in models.MEDIA_LIBRARY_SCOPES:
            raise ValueError(f"invalid media library scope: {scope}")
        if story_id is not None:
            self._require_story(workspace_id, story_id)
        return [
            bundle
            for item in self._repository.list_library_items(
                str(workspace_id),
                scope=scope,
                story_id=story_id,
            )
            if (bundle := self._library_bundle(item)) is not None
        ]

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
        title: str,
        description: str,
        tags: tuple[str, ...],
        is_default: bool,
    ) -> models.MediaLibraryAssetBundle | None:
        existing = self.get_library_asset(workspace_id, item_id)
        if existing is None:
            return None
        normalized_title, normalized_description, normalized_tags = _validate_library_metadata(
            title,
            description,
            tags,
        )
        if existing.item.scope != models.MEDIA_LIBRARY_SCOPE_STORY and is_default:
            raise ValueError("workspace fallback media cannot be a story default")
        item = self._repository.update_library_item(
            str(item_id),
            title=normalized_title,
            description=normalized_description,
            tags=normalized_tags,
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
        if self._repository.count_background_references(existing.asset.id):
            raise MediaAssetInUseError(
                f"media asset is referenced by a session background: {existing.asset.id}"
            )
        with self._database.atomic():
            asset_id = self._repository.delete_library_item(str(item_id))
            return self._repository.delete_asset(asset_id) if asset_id is not None else None

    def search_library_assets(
        self,
        *,
        workspace_id: str,
        scope: str,
        story_id: int | None,
        query: str,
        tags: tuple[str, ...] = (),
        limit: int = 20,
    ) -> list[models.MediaLibraryAssetBundle]:
        candidates = self.list_library_assets(
            workspace_id,
            scope=scope,
            story_id=story_id,
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
                    value += 100
                if term in title:
                    value += 20
                if term in description:
                    value += 5
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
    ) -> models.SessionMediaBackground:
        self._require_session(session_id)
        session = self._require_session(session_id)
        gallery_item = self._repository.get_gallery_asset(str(session_id), str(asset_id))
        library_item = self._repository.get_library_item_by_asset(str(asset_id))
        library_allowed = (
            library_item is not None
            and library_item.scope == models.MEDIA_LIBRARY_SCOPE_STORY
            and library_item.story_id == session.story_id
        )
        if gallery_item is None and not library_allowed:
            raise FileNotFoundError(f"Media asset is not manually selectable: {asset_id}")
        self._repository.ensure_background_state(str(session_id))
        return self._repository.set_background(
            str(session_id),
            str(asset_id),
            source_mode=models.MEDIA_BACKGROUND_SOURCE_MANUAL,
        )

    def clear_background(self, session_id: str) -> int:
        self._require_session(session_id)
        latest_turn_id = self._repository.get_latest_source_turns(
            str(session_id),
            through_turn_id=2**63 - 1,
            limit=1,
        )
        suppressed_through = latest_turn_id[-1].turn_id if latest_turn_id else 0
        self._repository.update_background_state(
            str(session_id),
            auto_suppressed=True,
            suppressed_through_turn_id=suppressed_through,
            desired_turn_id=0,
            desired_source_fingerprint="",
            latest_observed_turn_id=max(
                suppressed_through,
                self._repository.ensure_background_state(str(session_id)).latest_observed_turn_id,
            ),
        )
        return self._repository.clear_background(str(session_id))

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

    def queue_background_evaluation(
        self,
        *,
        session_id: str,
        observed_turn_id: int,
        target_turn_id: int,
        source_fingerprint: str,
        source_snapshot_json: str,
    ) -> models.MediaBackgroundEvaluation:
        self._require_session(session_id)
        if int(observed_turn_id) <= 0 or int(target_turn_id) <= 0:
            raise MediaSourceRangeError("background evaluation turn id must be positive")
        if int(observed_turn_id) > int(target_turn_id):
            raise MediaSourceRangeError("observed turn has not been committed")
        if len(str(source_fingerprint)) != 64:
            raise ValueError("background source fingerprint must be a SHA-256 digest")
        with self._database.atomic():
            state = self._repository.ensure_background_state(str(session_id))
            background = self._repository.get_background(str(session_id))
            self._repository.update_background_state(
                str(session_id),
                latest_observed_turn_id=max(state.latest_observed_turn_id, int(target_turn_id)),
                latest_source_fingerprint=str(source_fingerprint),
            )
            if (
                background is not None
                and background.source_mode == models.MEDIA_BACKGROUND_SOURCE_MANUAL
            ):
                return self._repository.create_background_evaluation(
                    evaluation_id=uuid.uuid4().hex,
                    session_id=str(session_id),
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL,
                    target_turn_id=int(target_turn_id),
                    source_fingerprint=str(source_fingerprint),
                    source_snapshot_json=str(source_snapshot_json),
                    decision="keep",
                    reason="manual background is locked",
                )
            if (
                state.auto_suppressed
                and int(target_turn_id) <= state.suppressed_through_turn_id
            ):
                return self._repository.create_background_evaluation(
                    evaluation_id=uuid.uuid4().hex,
                    session_id=str(session_id),
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED,
                    target_turn_id=int(target_turn_id),
                    source_fingerprint=str(source_fingerprint),
                    source_snapshot_json=str(source_snapshot_json),
                    decision="keep",
                    reason="automatic background is suppressed until a newer turn",
                )
            successful = self._repository.get_successful_background_evaluation(
                str(session_id),
                str(source_fingerprint),
            )
            if successful is not None:
                return successful
            active = self._repository.get_active_background_evaluation(
                str(session_id),
                str(source_fingerprint),
            )
            if active is not None:
                self._repository.update_background_state(
                    str(session_id),
                    desired_turn_id=int(target_turn_id),
                    desired_source_fingerprint=str(source_fingerprint),
                )
                return active
            queued = self._repository.get_queued_background_evaluation(str(session_id))
            if queued is not None:
                updated = self._repository.update_queued_background_evaluation(
                    queued.id,
                    target_turn_id=int(target_turn_id),
                    source_fingerprint=str(source_fingerprint),
                    source_snapshot_json=str(source_snapshot_json),
                )
                if updated is not None:
                    self._repository.update_background_state(
                        str(session_id),
                        desired_turn_id=int(target_turn_id),
                        desired_source_fingerprint=str(source_fingerprint),
                    )
                    return updated
            evaluation = self._repository.create_background_evaluation(
                evaluation_id=uuid.uuid4().hex,
                session_id=str(session_id),
                status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
                target_turn_id=int(target_turn_id),
                source_fingerprint=str(source_fingerprint),
                source_snapshot_json=str(source_snapshot_json),
            )
            self._repository.update_background_state(
                str(session_id),
                desired_turn_id=int(target_turn_id),
                desired_source_fingerprint=str(source_fingerprint),
            )
            return evaluation

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

    def claim_next_background_evaluation(
        self,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.claim_next_background_evaluation()

    def fail_background_evaluation(
        self,
        evaluation_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> models.MediaBackgroundEvaluation | None:
        return self._repository.finish_background_evaluation(
            str(evaluation_id),
            status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_FAILED,
            error_code=str(error_code),
            error_message=str(error_message),
        )

    def apply_background_decision(
        self,
        evaluation_id: str,
        *,
        decision: str,
        selected_asset_id: str | None,
        reason: str,
    ) -> models.MediaBackgroundEvaluation | None:
        if decision not in {"keep", "switch"}:
            raise ValueError(f"invalid media background decision: {decision}")
        with self._database.atomic():
            evaluation = self._repository.get_background_evaluation(str(evaluation_id))
            if evaluation is None:
                return None
            if evaluation.status != models.MEDIA_BACKGROUND_EVALUATION_STATUS_RUNNING:
                return evaluation
            state = self._repository.ensure_background_state(evaluation.session_id)
            if (
                state.desired_turn_id != evaluation.target_turn_id
                or state.desired_source_fingerprint != evaluation.source_fingerprint
            ):
                return self._repository.finish_background_evaluation(
                    evaluation.id,
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED,
                    decision=decision,
                    selected_asset_id=selected_asset_id,
                    reason="a newer background evaluation superseded this result",
                )
            background = self._repository.get_background(evaluation.session_id)
            if (
                background is not None
                and background.source_mode == models.MEDIA_BACKGROUND_SOURCE_MANUAL
            ):
                return self._repository.finish_background_evaluation(
                    evaluation.id,
                    status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SKIPPED_MANUAL,
                    decision="keep",
                    reason="manual background was selected during evaluation",
                )
            if decision == "switch":
                if not selected_asset_id:
                    raise ValueError("switch background decision requires asset_id")
                session = self._require_session(evaluation.session_id)
                library_item = self._repository.get_library_item_by_asset(selected_asset_id)
                allowed = library_item is not None and (
                    (
                        library_item.scope == models.MEDIA_LIBRARY_SCOPE_STORY
                        and library_item.story_id == session.story_id
                    )
                    or library_item.scope == models.MEDIA_LIBRARY_SCOPE_WORKSPACE_FALLBACK
                )
                if not allowed:
                    raise PermissionError(
                        f"background asset is outside the session media pools: {selected_asset_id}"
                    )
                self._repository.set_background(
                    evaluation.session_id,
                    selected_asset_id,
                    source_mode=models.MEDIA_BACKGROUND_SOURCE_AUTO,
                )
            self._repository.update_background_state(
                evaluation.session_id,
                last_applied_turn_id=evaluation.target_turn_id,
                last_applied_fingerprint=evaluation.source_fingerprint,
                last_decision=decision,
                last_reason=str(reason),
                auto_suppressed=False,
                suppressed_through_turn_id=0,
            )
            return self._repository.finish_background_evaluation(
                evaluation.id,
                status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED,
                decision=decision,
                selected_asset_id=selected_asset_id,
                reason=str(reason),
            )

    def interrupt_background_evaluations(
        self,
    ) -> list[models.MediaBackgroundEvaluation]:
        interrupted = self._repository.interrupt_running_background_evaluations()
        for evaluation in interrupted:
            queued = self._repository.get_queued_background_evaluation(evaluation.session_id)
            if queued is not None:
                continue
            self._repository.create_background_evaluation(
                evaluation_id=uuid.uuid4().hex,
                session_id=evaluation.session_id,
                status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_QUEUED,
                target_turn_id=evaluation.target_turn_id,
                source_fingerprint=evaluation.source_fingerprint,
                source_snapshot_json=evaluation.source_snapshot_json,
            )
        return interrupted

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
            raise ValueError("workspace fallback media must not bind a story")

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
        )


def _validate_library_metadata(
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


def _search_terms(query: str, tags: tuple[str, ...]) -> tuple[str, ...]:
    raw = str(query).replace(",", " ").replace("，", " ")
    values = [*raw.split(), *(str(tag) for tag in tags)]
    return tuple(dict.fromkeys(value.strip().casefold() for value in values if value.strip()))
