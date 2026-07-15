from __future__ import annotations

import pytest

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

    result = gateway.session_reset.reset(session.id)

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
