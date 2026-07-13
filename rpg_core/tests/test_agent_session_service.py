from __future__ import annotations

from types import SimpleNamespace

from rpg_core.agent.session_service import AgentSessionService
from rpg_core.context.rpg_context import Message, Role
from rpg_core.session import SessionManager


class _StatusManager:
    def __init__(self) -> None:
        self.boundaries: list[int] = []

    def clamp_deferred_progress(self, max_turn_id: int) -> int:
        self.boundaries.append(max_turn_id)
        return 0


def test_history_truncate_and_clear_clamp_deferred_progress() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "第一轮", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "第一轮回复", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "第二轮", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "第二轮回复", turn_id=2, seq_in_turn=2),
    ], persist=False)
    status = _StatusManager()
    lifecycle = SimpleNamespace(
        initialized=True,
        session_id="s_status_progress",
        session_manager=session,
        resources=SimpleNamespace(status_manager=status),
    )
    service = AgentSessionService(lifecycle=lifecycle, tool_service=object())

    result = service.truncate_history_from_turn_now(2)
    service.clear_history()

    assert result["removed"] == 2
    assert status.boundaries == [1, 0]
