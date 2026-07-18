"""Mutable, transaction-bound resources for one Agent turn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import TurnExecutionPlan

if TYPE_CHECKING:
    from llm_client.types import LLMProvider
    from rpg_core.agent.telemetry import TurnStats
    from rpg_core.agent.sub_agents.status.models import (
        StatusSubAgentPreflightOutcome,
        StatusSubAgentResult,
    )
    from rpg_core.agent.turn.transaction import AgentTurnTransaction, TurnScratch
    from rpg_core.rp_modules.runtime import RPModuleTurnRuntime


@dataclass
class TurnRuntime:
    """Own the mutable resources whose lifetime is exactly one turn."""

    plan: TurnExecutionPlan
    transaction: "AgentTurnTransaction"
    scratch: "TurnScratch"
    stats: "TurnStats"
    provider: "LLMProvider"
    rp_module_runtime: "RPModuleTurnRuntime | None" = None
    preflight_result: "StatusSubAgentResult | None" = None
    preflight_outcome: "StatusSubAgentPreflightOutcome | None" = None
    committed: bool = False
    _closed: bool = False

    def commit(self, assistant_text: str) -> int:
        self.transaction.stage_assistant_message(assistant_text)
        self.transaction.commit()
        self.committed = True
        return self.scratch.turn_id

    def discard(self) -> None:
        if not self.committed:
            self.transaction.discard()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.rp_module_runtime is not None:
                self.rp_module_runtime.close()
        finally:
            self.transaction.close()
