from __future__ import annotations

import asyncio
import logging

from rpg_tts.errors import TTS_ERROR_CODE_WORKER_ERROR
from rpg_tts.service import TTSApplicationService

logger = logging.getLogger("tts_service.worker")


class TTSJobWorker:
    def __init__(
        self,
        *,
        service: TTSApplicationService,
        concurrency: int = 1,
    ) -> None:
        self._service = service
        self._concurrency = max(1, int(concurrency))
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._tasks:
            return
        self._service.interrupt_active_jobs()
        self._stop_event.clear()
        self._wake_event.set()
        self._tasks = [
            asyncio.create_task(self._run(index), name=f"tts-worker-{index}")
            for index in range(self._concurrency)
        ]

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._service.interrupt_active_jobs()

    def wake(self) -> None:
        self._wake_event.set()

    async def _run(self, worker_index: int) -> None:
        while not self._stop_event.is_set():
            await self._wake_event.wait()
            self._wake_event.clear()
            while not self._stop_event.is_set():
                job = self._service.claim_next_job()
                if job is None:
                    break
                try:
                    await self._service.execute_job(job.id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception(
                        "unhandled TTS worker error worker=%s job_id=%s",
                        worker_index,
                        job.id,
                    )
                    try:
                        self._service.fail_job(
                            job.id,
                            error_code=TTS_ERROR_CODE_WORKER_ERROR,
                            error_message=str(exc),
                        )
                    except Exception:
                        logger.exception(
                            "failed to persist TTS worker error worker=%s job_id=%s",
                            worker_index,
                            job.id,
                        )
