"""Process-local asynchronous Dream generation lifecycle."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from dream_service.contracts import DreamProposalView, DreamRepository
from rp_memory.dream.engine import DreamEngine
from rp_memory.dream.errors import DreamAlreadyRunningError, DreamError
from rp_memory.dream.types import DreamDepth, DreamScope

logger = logging.getLogger("dream_service.runtime")


@dataclass(frozen=True)
class _ActiveGeneration:
    proposal_id: str
    task: asyncio.Task[None]


class DreamTaskManager:
    def __init__(
        self,
        *,
        repository: DreamRepository,
        engine: DreamEngine,
        orphan_check_interval_seconds: float = 0.5,
    ) -> None:
        self.repository = repository
        self.engine = engine
        self._orphan_check_interval_seconds = max(
            0.01,
            float(orphan_check_interval_seconds),
        )
        self._tasks_by_session: dict[str, _ActiveGeneration] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        interrupted = self.repository.interrupt_generating()
        if interrupted:
            logger.warning("interrupted stale Dream proposals count=%s", interrupted)

    async def stop(self) -> None:
        tasks = tuple(active.task for active in self._tasks_by_session.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks_by_session.clear()
        interrupted = self.repository.interrupt_generating()
        if interrupted:
            logger.warning(
                "interrupted Dream proposals during shutdown count=%s",
                interrupted,
            )

    async def create_proposal(
        self,
        session_id: str,
        *,
        depth: DreamDepth,
        scope: DreamScope,
    ) -> DreamProposalView:
        async with self._lock:
            existing = self._tasks_by_session.get(session_id)
            if existing is not None and not existing.task.done():
                stored = self.repository.get_proposal(
                    session_id,
                    existing.proposal_id,
                )
                if stored is not None and stored.status == "generating":
                    raise DreamAlreadyRunningError(
                        f"Session already has a generating Dream proposal: {session_id}"
                    )
                # `/clear`, Session deletion, or an external state transition
                # may remove/finish SQL state before this process-local LLM
                # task observes it.  Drain that orphan before accepting work.
                existing.task.cancel()
                await asyncio.gather(existing.task, return_exceptions=True)
                if self._tasks_by_session.get(session_id) is existing:
                    self._tasks_by_session.pop(session_id, None)
            elif existing is not None:
                self._tasks_by_session.pop(session_id, None)
            snapshot = self.repository.build_source_snapshot(session_id)
            selection = self.engine.prepare(snapshot, depth=depth, scope=scope)
            proposal = self.repository.create_proposal(selection)
            task = asyncio.create_task(
                self._generate(proposal, selection),
                name=f"dream-{session_id}-{proposal.proposal_id}",
            )
            active = _ActiveGeneration(proposal.proposal_id, task)
            self._tasks_by_session[session_id] = active
            task.add_done_callback(
                lambda completed, sid=session_id, pid=proposal.proposal_id: self._forget(
                    sid,
                    pid,
                    completed,
                )
            )
            return proposal

    async def _generate(self, proposal, selection) -> None:  # noqa: ANN001
        generation = asyncio.create_task(
            self.engine.generate(selection),
            name=f"dream-engine-{proposal.session_id}-{proposal.proposal_id}",
        )
        orphan_guard = asyncio.create_task(
            self._wait_until_proposal_inactive(
                proposal.session_id,
                proposal.proposal_id,
            ),
            name=f"dream-guard-{proposal.session_id}-{proposal.proposal_id}",
        )
        try:
            completed, _pending = await asyncio.wait(
                {generation, orphan_guard},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if orphan_guard in completed:
                generation.cancel()
                await asyncio.gather(generation, return_exceptions=True)
                logger.info(
                    "cancelled orphaned Dream generation proposal_id=%s session_id=%s",
                    proposal.proposal_id,
                    proposal.session_id,
                )
                return
            orphan_guard.cancel()
            await asyncio.gather(orphan_guard, return_exceptions=True)
            result = generation.result()
            self.repository.set_proposal_ready(proposal.proposal_id, result.items)
        except asyncio.CancelledError:
            generation.cancel()
            orphan_guard.cancel()
            await asyncio.gather(
                generation,
                orphan_guard,
                return_exceptions=True,
            )
            raise
        except Exception as exc:
            logger.exception(
                "Dream generation failed proposal_id=%s session_id=%s",
                proposal.proposal_id,
                proposal.session_id,
            )
            try:
                self.repository.set_proposal_failed(
                    proposal.proposal_id,
                    error_code=(
                        "DREAM_MODEL_CONTRACT_ERROR"
                        if isinstance(exc, DreamError)
                        else "DREAM_GENERATION_FAILED"
                    ),
                    error_message=str(exc),
                )
            except Exception:
                logger.exception(
                    "failed to persist Dream generation error proposal_id=%s",
                    proposal.proposal_id,
                )
        finally:
            generation.cancel()
            orphan_guard.cancel()
            await asyncio.gather(
                generation,
                orphan_guard,
                return_exceptions=True,
            )

    async def _wait_until_proposal_inactive(
        self,
        session_id: str,
        proposal_id: str,
    ) -> None:
        while True:
            await asyncio.sleep(self._orphan_check_interval_seconds)
            try:
                stored = self.repository.get_proposal(session_id, proposal_id)
            except Exception:
                logger.warning(
                    "failed to inspect Dream proposal while guarding generation "
                    "proposal_id=%s session_id=%s",
                    proposal_id,
                    session_id,
                    exc_info=True,
                )
                continue
            if stored is None or stored.status != "generating":
                return

    def _forget(
        self,
        session_id: str,
        proposal_id: str,
        completed: asyncio.Task[None],
    ) -> None:
        active = self._tasks_by_session.get(session_id)
        if (
            active is not None
            and active.proposal_id == proposal_id
            and active.task is completed
        ):
            self._tasks_by_session.pop(session_id, None)
