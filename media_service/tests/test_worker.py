from __future__ import annotations

import asyncio

import pytest

from media_service.worker import MediaJobWorker
from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.brief import DemoVisualBriefPlanner
from rpg_media.facade import MediaFacade
from rpg_media.providers.catalog import MediaProviderCatalog
from rpg_media.providers.local_file import LocalFileProvider
from rpg_media.source import build_source_snapshot
from rpg_media.types import VisualBrief


@pytest.mark.asyncio
async def test_worker_interrupts_stale_active_jobs_and_resumes_queued(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "worker.sqlite3")
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(tmp_path / "workspace"),),
    )
    session = gateway.catalog.create_session("demo_workspace", 1, title="worker")
    assert session is not None
    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "scene",
        turn_id=1,
        seq_in_turn=1,
    )
    provider_dir = tmp_path / "provider"
    provider_dir.mkdir()
    (provider_dir / "sample.png").write_bytes(b"\x89PNG\r\n\x1a\nworker")
    facade = MediaFacade(
        data=gateway.media,
        catalog=gateway.catalog,
        planner=DemoVisualBriefPlanner(),
        providers=MediaProviderCatalog(
            (LocalFileProvider(provider_dir),),
            default_key="local_file",
        ),
    )
    source = build_source_snapshot(
        gateway.media,
        session.id,
        start_turn_id=1,
        end_turn_id=1,
    )
    stale = gateway.media.create_job(
        session_id=session.id,
        provider_key="local_file",
        source_start_turn_id=1,
        source_end_turn_id=1,
        source_fingerprint=source.fingerprint,
        source_snapshot_json=source.snapshot_json,
        visual_brief_json=VisualBrief(scene_description="stale").to_json(),
    )
    assert gateway.media.claim_next_job().id == stale.id  # type: ignore[union-attr]
    queued = gateway.media.create_job(
        session_id=session.id,
        provider_key="local_file",
        source_start_turn_id=1,
        source_end_turn_id=1,
        source_fingerprint=source.fingerprint,
        source_snapshot_json=source.snapshot_json,
        visual_brief_json=VisualBrief(scene_description="queued").to_json(),
    )
    worker = MediaJobWorker(
        data=gateway.media,
        facade=facade,
        concurrency=1,
        poll_interval_ms=25,
    )

    await worker.start()
    for _ in range(100):
        current = gateway.media.get_job(session.id, queued.id)
        if current is not None and current.status == models.MEDIA_JOB_STATUS_SUCCEEDED:
            break
        await asyncio.sleep(0.01)
    await worker.stop()

    interrupted = gateway.media.get_job(session.id, stale.id)
    resumed = gateway.media.get_job(session.id, queued.id)
    assert interrupted is not None
    assert interrupted.status == models.MEDIA_JOB_STATUS_INTERRUPTED
    assert resumed is not None
    assert resumed.status == models.MEDIA_JOB_STATUS_SUCCEEDED
