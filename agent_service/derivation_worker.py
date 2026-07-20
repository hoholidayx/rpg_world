"""Persistent single-consumer worker for session derivation jobs."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from agent_service.derivation_notifications import (
    NullSessionDerivationNotificationSink,
    SessionDerivationNotification,
    SessionDerivationNotificationSink,
)
from rpg_core.agent.manager import AgentManager
from rpg_core.agent.runtime.derivation import SessionDerivationPreparationError
from rpg_core.session.derivation import (
    SessionDerivationError,
    SessionDerivationErrorCode,
    SessionDerivationService,
    SessionDerivationStatus,
)
from rpg_core.session.deletion import SessionDeletionService

if TYPE_CHECKING:
    from rpg_data.models import SessionDerivationJob
    from rpg_data.services.gateway import DataServiceGateway


_TAG = "[SessionDerivationWorker]"
_DEFAULT_RETRY_DELAY_SECONDS = 0.25


class SessionDerivationWorker:
    """Consume queued jobs serially and publish only fully prepared targets."""

    def __init__(
        self,
        *,
        gateway: "DataServiceGateway",
        notification_sink: SessionDerivationNotificationSink | None = None,
        retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
        derivation_service: SessionDerivationService | None = None,
        deletion_service: SessionDeletionService | None = None,
    ) -> None:
        self._gateway = gateway
        self._derivations = derivation_service or SessionDerivationService(gateway)
        self._deletion = deletion_service or SessionDeletionService(gateway)
        self._notifications = (
            notification_sink or NullSessionDerivationNotificationSink()
        )
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._retry_delay_seconds = max(0.01, float(retry_delay_seconds))
        self._stale_recovery_pending = True

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._wake_event.set()
        self._stale_recovery_pending = not await self.interrupt_stale_jobs()
        self._task = asyncio.create_task(
            self._run(),
            name="session-derivation-worker",
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._wake_event.set()
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    def wake(self) -> None:
        self._wake_event.set()

    async def interrupt_stale_jobs(self) -> bool:
        """Clean target runtimes before the data layer marks stale jobs final."""

        service = self._derivations
        try:
            running = service.list_jobs(SessionDerivationStatus.RUNNING)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " stale job listing failed; recovery will retry",
            )
            return False
        recovered_all = True
        for job in running:
            if job.target_session_id:
                try:
                    await AgentManager.drop_session(job.target_session_id)
                except Exception as exc:
                    recovered_all = False
                    logger.opt(exception=exc).error(
                        _TAG + " stale target runtime close failed: target_session_id={}",
                        job.target_session_id,
                    )
                    continue
                try:
                    self._deletion.delete_provisioning_target(
                        job.id,
                        job.target_session_id,
                    )
                except Exception as exc:
                    recovered_all = False
                    logger.opt(exception=exc).error(
                        _TAG + " stale target deletion failed: target_session_id={}",
                        job.target_session_id,
                    )
                    continue
            try:
                interrupted = service.interrupt_job(job.id)
            except Exception as exc:
                recovered_all = False
                logger.opt(exception=exc).error(
                    _TAG + " stale job terminal update failed: job_id={}",
                    job.id,
                )
                continue
            await self._publish(interrupted)
            logger.warning(
                _TAG + " interrupted stale job: job_id={}, target_session_id={}",
                interrupted.id,
                interrupted.target_session_id,
            )
        return recovered_all

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._stale_recovery_pending:
                self._stale_recovery_pending = not await self.interrupt_stale_jobs()
                if self._stale_recovery_pending:
                    await self._wait_before_retry()
                    continue
                # Recovery may have interrupted one blocking running job while
                # older queued work is still persisted. Re-scan immediately;
                # no new API request is guaranteed to wake the worker.
                self._wake_event.set()
            await self._wake_event.wait()
            self._wake_event.clear()
            while not self._stop_event.is_set():
                try:
                    queued = self._derivations.list_jobs(
                        SessionDerivationStatus.QUEUED
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.opt(exception=exc).warning(
                        _TAG + " queued job listing failed; consumer will retry",
                    )
                    await self._wait_before_retry()
                    continue
                if not queued:
                    break
                if not await self._execute(queued[0]):
                    await self._wait_before_retry()
                    if self._stale_recovery_pending:
                        break

    async def _execute(self, queued_job: "SessionDerivationJob") -> bool:
        service = self._derivations
        try:
            job = service.start_job(queued_job.id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " job claim failed; consumer will retry: job_id={}",
                queued_job.id,
            )
            return False
        logger.info(
            _TAG + " started: job_id={}, source_session_id={}, turn_id={}",
            job.id,
            job.source_session_id,
            job.branch_turn_id,
        )
        try:
            source_agent = AgentManager.get_or_create(job.source_session_id)
            seed = await source_agent.materialize_derivation(job.id)
            target_id = seed.session.id
            target_agent = AgentManager.get_or_create(target_id)
            await target_agent.prepare_derivation_target(job.id)
            completed = service.complete_job(job.id)
            logger.info(
                _TAG + " ready: job_id={}, target_session_id={}",
                completed.id,
                completed.target_session_id,
            )
            await self._publish(completed)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " failed: job_id={}",
                job.id,
            )
            failed = await self._fail(job.id, exc)
            if failed is not None:
                await self._publish(failed)
                return True
            self._stale_recovery_pending = True
            return False

    async def _fail(
        self,
        job_id: str,
        error: Exception,
    ) -> "SessionDerivationJob | None":
        service = self._derivations
        current = service.get_job(job_id)
        if current is None:
            return None
        if current.target_session_id:
            try:
                await AgentManager.drop_session(current.target_session_id)
            except Exception as exc:
                logger.opt(exception=exc).error(
                    _TAG + " target runtime close failed: job_id={}, target_session_id={}",
                    job_id,
                    current.target_session_id,
                )
                return None
            try:
                self._deletion.delete_provisioning_target(
                    job_id,
                    current.target_session_id,
                )
            except Exception as exc:
                logger.opt(exception=exc).error(
                    _TAG + " target deletion failed: job_id={}, target_session_id={}",
                    job_id,
                    current.target_session_id,
                )
                return None
        code = (
            error.code
            if isinstance(
                error,
                (SessionDerivationPreparationError, SessionDerivationError),
            )
            else SessionDerivationErrorCode.PREPARATION_FAILED.value
        )
        message = str(error) or type(error).__name__
        try:
            return service.fail_job(
                job_id,
                error_code=code,
                error_message=message,
            )
        except Exception:
            logger.exception(_TAG + " failed to persist terminal state: job_id={}", job_id)
            return None

    async def _wait_before_retry(self) -> None:
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self._retry_delay_seconds,
            )
        except TimeoutError:
            pass

    async def _publish(self, job: "SessionDerivationJob") -> None:
        try:
            await self._notifications.publish(
                SessionDerivationNotification(
                    job_id=job.id,
                    source_session_id=job.source_session_id,
                    target_session_id=job.target_session_id,
                    branch_turn_id=job.branch_turn_id,
                    status=job.status,
                    error_code=job.error_code,
                    error_message=job.error_message,
                    context_threshold_exceeded=job.context_threshold_exceeded,
                    finished_at=job.finished_at,
                    updated_at=job.updated_at,
                )
            )
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " notification sink failed: job_id={}",
                job.id,
            )
