from __future__ import annotations

import pytest

from rpg_core.session.reset import SessionResetService
from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_data.services.media import MediaAssetInUseError, MediaSourceRangeError


def _session_with_turns(tmp_path):  # noqa: ANN202
    gateway = get_data_service_gateway(tmp_path / "media.sqlite3")
    session = gateway.catalog.create_session(
        "demo_workspace",
        1,
        title="Media session",
    )
    assert session is not None
    for turn_id, content in ((1, "走入森林"), (2, "看见月光"), (3, "抵达石门")):
        gateway.messages.append(
            session.id,
            models.MESSAGE_ROLE_USER,
            content,
            turn_id=turn_id,
            seq_in_turn=1,
        )
    return gateway, session


def _create_and_claim_job(gateway, session_id: str, *, retry_of: str | None = None):  # noqa: ANN202
    job = gateway.media.create_job(
        session_id=session_id,
        provider_key="local_file",
        source_start_turn_id=1,
        source_end_turn_id=2,
        source_fingerprint="a" * 64,
        source_snapshot_json='{"messages":[]}',
        visual_brief_json='{"sceneDescription":"forest"}',
        retry_of_job_id=retry_of,
    )
    claimed = gateway.media.claim_next_job()
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == models.MEDIA_JOB_STATUS_RUNNING
    return claimed


def test_source_range_requires_contiguous_committed_turns(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)

    turns = gateway.media.get_source_turns(
        session.id,
        start_turn_id=1,
        end_turn_id=3,
    )

    assert [turn.turn_id for turn in turns] == [1, 2, 3]
    assert turns[0].messages[0].content == "走入森林"
    gateway.messages.clear(session.id)
    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "only first",
        turn_id=1,
        seq_in_turn=1,
    )
    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "third",
        turn_id=3,
        seq_in_turn=1,
    )
    with pytest.raises(MediaSourceRangeError, match="contiguous"):
        gateway.media.get_source_turns(
            session.id,
            start_turn_id=1,
            end_turn_id=3,
        )


def test_blob_deduplicates_but_every_job_creates_an_independent_asset(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)
    first_job = _create_and_claim_job(gateway, session.id)
    first = gateway.media.complete_job(
        job_id=first_job.id,
        sha256="b" * 64,
        canonical_ext="png",
        mime_type="image/png",
        byte_size=100,
        relative_path=f"assets/images/{'b' * 64}.png",
    )
    assert first is not None

    second_job = _create_and_claim_job(gateway, session.id, retry_of=first_job.id)
    second = gateway.media.complete_job(
        job_id=second_job.id,
        sha256="b" * 64,
        canonical_ext="png",
        mime_type="image/png",
        byte_size=100,
        relative_path=f"assets/images/{'b' * 64}.png",
    )
    assert second is not None

    assert first.asset.id != second.asset.id
    assert first.blob.id == second.blob.id
    assert first.blob_created is True
    assert second.blob_created is False
    assert len(gateway.media.list_gallery(session.id)) == 2
    library = gateway.media.list_library_assets(
        "demo_workspace",
        scope=models.MEDIA_LIBRARY_SCOPE_STORY,
        story_id=1,
    )
    assert {bundle.asset.id for bundle in library} == {
        first.asset.id,
        second.asset.id,
    }
    assert all(
        bundle.asset.origin_kind == models.MEDIA_ASSET_ORIGIN_GENERATED
        and bundle.tags == ("generated",)
        for bundle in library
    )


def test_background_blocks_asset_deletion_and_last_asset_collects_blob(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)
    job = _create_and_claim_job(gateway, session.id)
    completed = gateway.media.complete_job(
        job_id=job.id,
        sha256="c" * 64,
        canonical_ext="webp",
        mime_type="image/webp",
        byte_size=120,
        relative_path=f"assets/images/{'c' * 64}.webp",
    )
    assert completed is not None
    gateway.media.set_background(session.id, completed.asset.id)

    with pytest.raises(MediaAssetInUseError):
        gateway.media.delete_session_asset(session.id, completed.asset.id)

    gateway.media.clear_background(session.id)
    deleted = gateway.media.delete_session_asset(session.id, completed.asset.id)
    assert deleted is not None
    assert deleted.blob_deleted is True
    assert gateway.media.get_session_asset(session.id, completed.asset.id) is None


def test_session_reset_clears_jobs_gallery_and_background_but_preserves_asset(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)
    job = _create_and_claim_job(gateway, session.id)
    completed = gateway.media.complete_job(
        job_id=job.id,
        sha256="d" * 64,
        canonical_ext="jpg",
        mime_type="image/jpeg",
        byte_size=140,
        relative_path=f"assets/images/{'d' * 64}.jpg",
    )
    assert completed is not None
    gateway.media.set_background(session.id, completed.asset.id)

    result = SessionResetService(gateway.sessions).reset(session.id)

    assert result.media_jobs_cleared == 1
    assert result.media_gallery_items_cleared == 1
    assert result.media_backgrounds_cleared == 1
    assert gateway.media.list_gallery(session.id) == []
    assert gateway.media.get_background(session.id) is None
    asset_count = gateway.database.execute_sql(
        "SELECT COUNT(*) FROM rpg_media_assets WHERE id = ?",
        (completed.asset.id,),
    ).fetchone()[0]
    assert asset_count == 1


def test_restart_interrupts_running_and_cancelling_but_leaves_queued(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)
    running = _create_and_claim_job(gateway, session.id)
    cancelling = gateway.media.request_cancel(session.id, running.id)
    assert cancelling is not None
    assert cancelling.status == models.MEDIA_JOB_STATUS_CANCELLING
    queued = gateway.media.create_job(
        session_id=session.id,
        provider_key="local_file",
        source_start_turn_id=2,
        source_end_turn_id=3,
        source_fingerprint="e" * 64,
        source_snapshot_json='{"messages":[]}',
        visual_brief_json='{"sceneDescription":"gate"}',
    )

    assert gateway.media.interrupt_active_jobs() == 1
    interrupted = gateway.media.get_job(session.id, running.id)
    still_queued = gateway.media.get_job(session.id, queued.id)
    assert interrupted is not None
    assert interrupted.status == models.MEDIA_JOB_STATUS_INTERRUPTED
    assert still_queued is not None
    assert still_queued.status == models.MEDIA_JOB_STATUS_QUEUED


def test_library_uploads_share_blob_index_but_keep_independent_assets(tmp_path) -> None:
    gateway, _session = _session_with_turns(tmp_path)
    common = {
        "workspace_id": "demo_workspace",
        "scope": models.MEDIA_LIBRARY_SCOPE_STORY,
        "story_id": 1,
        "description": "A moonlit forest background",
        "tags": ("forest", "night"),
        "is_default": False,
        "sha256": "f" * 64,
        "canonical_ext": "png",
        "mime_type": "image/png",
        "byte_size": 128,
        "relative_path": f"assets/images/{'f' * 64}.png",
        "visual_brief_json": '{"sceneDescription":"forest"}',
    }

    first, first_blob_created = gateway.media.create_library_asset(
        title="First forest",
        **common,
    )
    second, second_blob_created = gateway.media.create_library_asset(
        title="Second forest",
        **common,
    )

    assert first.asset.id != second.asset.id
    assert first.blob.id == second.blob.id
    assert first_blob_created is True
    assert second_blob_created is False
    blob_columns = {
        str(row[1])
        for row in gateway.database.execute_sql("PRAGMA table_info(rpg_media_blobs)")
    }
    assert "data" not in blob_columns
    assert "content" not in blob_columns
    assert first.blob.relative_path == f"assets/images/{'f' * 64}.png"


def test_reconcile_missing_blobs_cascades_shared_assets_and_is_idempotent(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)
    first_job = _create_and_claim_job(gateway, session.id)
    first = gateway.media.complete_job(
        job_id=first_job.id,
        sha256="6" * 64,
        canonical_ext="png",
        mime_type="image/png",
        byte_size=100,
        relative_path=f"assets/images/{'6' * 64}.png",
    )
    assert first is not None
    second_job = _create_and_claim_job(gateway, session.id, retry_of=first_job.id)
    second = gateway.media.complete_job(
        job_id=second_job.id,
        sha256="6" * 64,
        canonical_ext="png",
        mime_type="image/png",
        byte_size=100,
        relative_path=f"assets/images/{'6' * 64}.png",
    )
    assert second is not None
    survivor, _ = gateway.media.create_library_asset(
        workspace_id="demo_workspace",
        scope=models.MEDIA_LIBRARY_SCOPE_STORY,
        story_id=1,
        title="Existing file",
        description="This blob must remain indexed.",
        tags=("existing",),
        is_default=False,
        sha256="7" * 64,
        canonical_ext="webp",
        mime_type="image/webp",
        byte_size=90,
        relative_path=f"assets/images/{'7' * 64}.webp",
        visual_brief_json='{"sceneDescription":"existing"}',
    )
    gateway.media.set_background(session.id, first.asset.id)

    result = gateway.media.reconcile_missing_blobs(
        "demo_workspace",
        blob_ids=(first.blob.id,),
        scanned_blobs=2,
    )

    assert result == models.MediaLibraryReconcileResult(
        workspace_id="demo_workspace",
        scanned_blobs=2,
        removed_blobs=1,
        removed_assets=2,
        removed_library_items=2,
        removed_gallery_items=2,
        cleared_backgrounds=1,
    )
    assert gateway.media.get_background(session.id) is None
    assert gateway.media.list_gallery(session.id) == []
    assert gateway.media.get_library_asset_by_asset_id(survivor.asset.id) is not None
    assert gateway.media.get_job(session.id, first_job.id).output_asset_id is None
    assert gateway.media.get_job(session.id, second_job.id).output_asset_id is None

    repeated = gateway.media.reconcile_missing_blobs(
        "demo_workspace",
        blob_ids=(first.blob.id,),
        scanned_blobs=1,
    )
    assert repeated == models.MediaLibraryReconcileResult(
        workspace_id="demo_workspace",
        scanned_blobs=1,
    )


def test_reconcile_missing_blobs_rolls_back_all_changes_on_delete_failure(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)
    job = _create_and_claim_job(gateway, session.id)
    completed = gateway.media.complete_job(
        job_id=job.id,
        sha256="5" * 64,
        canonical_ext="jpg",
        mime_type="image/jpeg",
        byte_size=110,
        relative_path=f"assets/images/{'5' * 64}.jpg",
    )
    assert completed is not None
    gateway.media.set_background(session.id, completed.asset.id)
    gateway.database.execute_sql(
        """
        CREATE TRIGGER reject_media_blob_delete
        BEFORE DELETE ON rpg_media_blobs
        BEGIN
            SELECT RAISE(ABORT, 'blocked media blob delete');
        END
        """
    )

    with pytest.raises(Exception, match="blocked media blob delete"):
        gateway.media.reconcile_missing_blobs(
            "demo_workspace",
            blob_ids=(completed.blob.id,),
            scanned_blobs=1,
        )

    background = gateway.media.get_background(session.id)
    assert background is not None
    assert background.asset_id == completed.asset.id
    assert gateway.media.get_session_asset(session.id, completed.asset.id) is not None
    assert gateway.media.get_library_asset_by_asset_id(completed.asset.id) is not None
    assert gateway.media.get_job(session.id, job.id).output_asset_id == completed.asset.id
    assert gateway.media.get_workspace_blob_by_hash("demo_workspace", "5" * 64) is not None


def test_manual_clear_supersedes_running_background_evaluation(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)
    library, _ = gateway.media.create_library_asset(
        workspace_id="demo_workspace",
        scope=models.MEDIA_LIBRARY_SCOPE_STORY,
        story_id=1,
        title="Forest",
        description="A moonlit forest background",
        tags=("forest",),
        is_default=True,
        sha256="9" * 64,
        canonical_ext="png",
        mime_type="image/png",
        byte_size=128,
        relative_path=f"assets/images/{'9' * 64}.png",
        visual_brief_json='{"sceneDescription":"forest"}',
    )
    queued = gateway.media.queue_background_evaluation(
        session_id=session.id,
        observed_turn_id=3,
        target_turn_id=3,
        source_fingerprint="8" * 64,
        source_snapshot_json="{}",
    )
    claimed = gateway.media.claim_next_background_evaluation()
    assert claimed is not None and claimed.id == queued.id

    gateway.media.clear_background(session.id)
    result = gateway.media.apply_background_decision(
        queued.id,
        decision="switch",
        selected_asset_id=library.asset.id,
        reason="late result",
    )

    assert result is not None
    assert result.status == models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUPERSEDED
    assert gateway.media.get_background(session.id) is None
    assert gateway.media.get_background_state(session.id).auto_suppressed is True


def test_media_library_taxonomy_pagination_facets_and_background_guard(tmp_path) -> None:
    gateway, session = _session_with_turns(tmp_path)

    def create_asset(*, suffix: str, title: str, media_type: str, tags: tuple[str, ...]):
        return gateway.media.create_library_asset(
            workspace_id="demo_workspace",
            scope=models.MEDIA_LIBRARY_SCOPE_STORY,
            story_id=1,
            media_type=media_type,
            title=title,
            description=f"{title} description",
            tags=tags,
            is_default=False,
            sha256=suffix * 64,
            canonical_ext="png",
            mime_type="image/png",
            byte_size=128,
            relative_path=f"assets/images/{suffix * 64}.png",
            visual_brief_json=f'{{"sceneDescription":"{title}"}}',
        )[0]

    background = create_asset(
        suffix="1",
        title="Moonlit forest",
        media_type=models.MEDIA_LIBRARY_TYPE_BACKGROUND,
        tags=("Forest", "Night"),
    )
    avatar = create_asset(
        suffix="2",
        title="Forest guardian",
        media_type=models.MEDIA_LIBRARY_TYPE_AVATAR,
        tags=("forest", "Portrait"),
    )
    create_asset(
        suffix="3",
        title="Ancient map",
        media_type=models.MEDIA_LIBRARY_TYPE_MAP,
        tags=("forest", "map"),
    )

    page = gateway.media.list_library_assets_page(
        "demo_workspace",
        query="guardian",
        media_types=(models.MEDIA_LIBRARY_TYPE_AVATAR,),
        tags=("portrait",),
        page=1,
        page_size=1,
    )

    assert page.total == 1
    assert [bundle.item.id for bundle in page.items] == [avatar.item.id]
    assert page.items[0].item.media_type == models.MEDIA_LIBRARY_TYPE_AVATAR
    facets = gateway.media.get_library_facets("demo_workspace")
    assert {facet.value: facet.count for facet in facets.media_types} == {
        "avatar": 1,
        "background": 1,
        "map": 1,
    }
    assert {facet.value.casefold(): facet.count for facet in facets.tags}["forest"] == 3

    gateway.media.set_background(session.id, background.asset.id)
    background_page = gateway.media.list_library_assets_page(
        "demo_workspace",
        media_types=(models.MEDIA_LIBRARY_TYPE_BACKGROUND,),
    )
    assert background_page.items[0].usage.background_references == 1
    with pytest.raises(MediaAssetInUseError):
        gateway.media.update_library_asset(
            "demo_workspace",
            background.item.id,
            scope=background.item.scope,
            story_id=background.item.story_id,
            media_type=models.MEDIA_LIBRARY_TYPE_AVATAR,
            title=background.item.title,
            description=background.item.description,
            tags=background.tags,
            is_default=False,
        )
    with pytest.raises(FileNotFoundError, match="not manually selectable"):
        gateway.media.set_background(session.id, avatar.asset.id)
