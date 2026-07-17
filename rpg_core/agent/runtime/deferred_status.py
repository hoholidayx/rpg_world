"""Session-local deferred status reconciliation collaborator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle

_TAG = "[DeferredStatusCoordinator]"


class DeferredStatusCoordinator:
    """Run deferred reconciliation after a committed reply is delivered."""

    def __init__(self, lifecycle: "AgentRuntimeLifecycle") -> None:
        self._lifecycle = lifecycle

    async def run(self) -> None:
        sub_agent = self._lifecycle.status_sub_agent
        status_manager = self._lifecycle.resources.status_manager
        if sub_agent is None or status_manager is None:
            return
        result = await sub_agent.reconcile_deferred(
            session_manager=self._lifecycle.session_manager,
            status_manager=status_manager,
        )
        if result.batches:
            logger.info(
                _TAG + " completed: session_id={}, batches={}, fields={}, changed={}",
                self._lifecycle.session_id,
                result.batches,
                result.fields,
                result.changed,
            )
