from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from rpg_tts.errors import TTS_ERROR_CODE_WORKER_ERROR
from tts_service.worker import TTSJobWorker


@pytest.mark.asyncio
async def test_worker_uses_application_service_for_recovery_claim_and_failure() -> None:
    service = Mock()
    service.interrupt_active_jobs.return_value = 1
    service.execute_job = AsyncMock(side_effect=RuntimeError("worker failure"))
    job = SimpleNamespace(id="tts-job")
    service.claim_next_job.side_effect = [job, None]
    worker = TTSJobWorker(service=service, concurrency=1)

    await worker.start()
    try:
        for _ in range(100):
            if service.fail_job.call_count:
                break
            await asyncio.sleep(0.001)
        service.execute_job.assert_awaited_once_with("tts-job")
        service.fail_job.assert_called_once_with(
            "tts-job",
            error_code=TTS_ERROR_CODE_WORKER_ERROR,
            error_message="worker failure",
        )
    finally:
        await worker.stop()

    assert service.interrupt_active_jobs.call_count == 2
