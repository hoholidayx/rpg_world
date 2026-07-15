"""Persistent database-backed media job worker."""

from __future__ import annotations

import asyncio
import logging

from rpg_data.services.media import MediaDataService
from rpg_media.facade import MediaFacade

logger = logging.getLogger("media_service.worker")


class MediaJobWorker:
    def __init__(
        self,
        *,
        data: MediaDataService,
        facade: MediaFacade,
        concurrency: int = 1,
    ) -> None:
        self._data = data
        self._facade = facade
        self._concurrency = max(1, int(concurrency))
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def running(self) -> bool:
        return bool(self._tasks) and any(not task.done() for task in self._tasks)

    async def start(self) -> None:
        if self.running:
            return
        interrupted = self._data.interrupt_active_jobs()
        if interrupted:
            logger.warning("interrupted stale media jobs count=%s", interrupted)
        self._stop_event.clear()
        self._wake_event.set()
        self._tasks = [
            asyncio.create_task(self._run(index), name=f"media-worker-{index}")
            for index in range(self._concurrency)
        ]

    async def stop(self) -> None:
        if not self._tasks:
            return
        self._stop_event.set()
        self._wake_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        interrupted = self._data.interrupt_active_jobs()
        if interrupted:
            logger.warning("interrupted media jobs during shutdown count=%s", interrupted)

    def wake(self) -> None:
        self._wake_event.set()

    async def _run(self, worker_index: int) -> None:
        while not self._stop_event.is_set():
            job = self._data.claim_next_job()
            if job is not None:
                logger.info(
                    "media job claimed worker=%s job_id=%s session_id=%s provider=%s",
                    worker_index,
                    job.id,
                    job.session_id,
                    job.provider_key,
                )
                try:
                    result = await self._facade.execute_job(job.id)
                    logger.info(
                        "media job finished worker=%s job_id=%s status=%s",
                        worker_index,
                        job.id,
                        result.status if result is not None else "deleted",
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "unhandled media worker error worker=%s job_id=%s",
                        worker_index,
                        job.id,
                    )
                continue
            self._wake_event.clear()
            await self._wake_event.wait()
