from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from media_service.worker import MediaBackgroundWorker, MediaJobWorker
from rpg_data import models
from rpg_data.services.gateway import get_data_service_gateway
from rpg_media.brief import DemoVisualBriefPlanner
from rpg_media.facade import MediaFacade
from rpg_media.providers.catalog import MediaProviderCatalog
from rpg_media.providers.local_file import LocalFileProvider
from rpg_media.source import build_source_snapshot
from rpg_media.types import VisualBrief


@pytest.mark.asyncio
async def test_worker_sleeps_until_woken_and_returns_to_sleep_after_job() -> None:
    data = Mock()
    data.interrupt_active_jobs.return_value = 0
    data.claim_next_job.return_value = None
    facade = Mock()
    facade.execute_job = AsyncMock(
        return_value=SimpleNamespace(status=models.MEDIA_JOB_STATUS_SUCCEEDED)
    )
    worker = MediaJobWorker(data=data, facade=facade, concurrency=1)

    await worker.start()
    try:
        for _ in range(100):
            if data.claim_next_job.call_count:
                break
            await asyncio.sleep(0.001)
        assert data.claim_next_job.call_count == 1

        await asyncio.sleep(0.3)
        assert data.claim_next_job.call_count == 1

        job = SimpleNamespace(
            id="job1",
            session_id="session1",
            provider_key="local_file",
        )
        data.claim_next_job.side_effect = [job, None]
        worker.wake()
        for _ in range(100):
            if facade.execute_job.await_count == 1 and data.claim_next_job.call_count == 3:
                break
            await asyncio.sleep(0.001)
        facade.execute_job.assert_awaited_once_with("job1")
        assert data.claim_next_job.call_count == 3

        await asyncio.sleep(0.3)
        assert data.claim_next_job.call_count == 3
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_generation_worker_does_not_lose_wake_during_empty_claim() -> None:
    data = Mock()
    data.interrupt_active_jobs.return_value = 0
    facade = Mock()
    facade.execute_job = AsyncMock(
        return_value=SimpleNamespace(status=models.MEDIA_JOB_STATUS_SUCCEEDED)
    )
    worker = MediaJobWorker(data=data, facade=facade, concurrency=1)
    job = SimpleNamespace(id="job-race", session_id="session1", provider_key="local")
    claims = 0

    def claim():  # noqa: ANN202
        nonlocal claims
        claims += 1
        if claims == 1:
            worker.wake()
            return None
        if claims == 2:
            return job
        return None

    data.claim_next_job.side_effect = claim
    await worker.start()
    try:
        for _ in range(100):
            if facade.execute_job.await_count:
                break
            await asyncio.sleep(0.001)
        facade.execute_job.assert_awaited_once_with("job-race")
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_background_worker_does_not_lose_wake_during_empty_claim() -> None:
    data = Mock()
    data.interrupt_background_evaluations.return_value = []
    facade = Mock()
    facade.execute_background_evaluation = AsyncMock(
        return_value=SimpleNamespace(status=models.MEDIA_BACKGROUND_EVALUATION_STATUS_SUCCEEDED)
    )
    worker = MediaBackgroundWorker(data=data, facade=facade, concurrency=1)
    evaluation = SimpleNamespace(
        id="evaluation-race",
        session_id="session1",
        target_turn_id=2,
    )
    claims = 0

    def claim():  # noqa: ANN202
        nonlocal claims
        claims += 1
        if claims == 1:
            worker.wake()
            return None
        if claims == 2:
            return evaluation
        return None

    data.claim_next_background_evaluation.side_effect = claim
    await worker.start()
    try:
        for _ in range(100):
            if facade.execute_background_evaluation.await_count:
                break
            await asyncio.sleep(0.001)
        facade.execute_background_evaluation.assert_awaited_once_with("evaluation-race")
    finally:
        await worker.stop()


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
