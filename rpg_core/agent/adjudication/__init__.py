"""Shared context and tool-loop primitives for non-narrative adjudication."""

from rpg_core.agent.adjudication.models import (
    AdjudicationContextMessage,
    AdjudicationContextSnapshot,
)
from rpg_core.agent.adjudication.loop import (
    AdjudicationLoopResult,
    run_adjudication_tool_loop,
)

__all__ = [
    "AdjudicationContextMessage",
    "AdjudicationContextSnapshot",
    "AdjudicationLoopResult",
    "run_adjudication_tool_loop",
]
