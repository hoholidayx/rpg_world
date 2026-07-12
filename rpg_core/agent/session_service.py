"""Session, role, and history operations for ``RPGGameAgent``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.context.rpg_context import Message

if TYPE_CHECKING:
    from rpg_core.agent.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.mailbox import AgentMailbox
    from rpg_core.agent.tool_service import AgentToolService

_TAG = "[AgentSessionService]"


class AgentSessionService:
    """Own role guards and every mutable session-history operation."""

    def __init__(
        self,
        *,
        lifecycle: "AgentRuntimeLifecycle",
        tool_service: "AgentToolService",
    ) -> None:
        self._lifecycle = lifecycle
        self._tool_service = tool_service
        self._mailbox: AgentMailbox | None = None

    def bind_mailbox(self, mailbox: "AgentMailbox") -> None:
        self._mailbox = mailbox

    @property
    def history(self) -> list[Message]:
        return self._lifecycle.session_manager.history

    def render_role_bind_prompt(self, *, error: str = "") -> str:
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().session_roles.render_role_bind_prompt(
            self._lifecycle.session_id,
            error=error,
        )

    def bind_player_character_by_index(self, index: int):
        from rpg_data.services import get_data_service_gateway

        session_id = self._lifecycle.session_id
        logger.info(
            _TAG + " binding player character by index: session_id={}, index={}",
            session_id,
            index,
        )
        result = get_data_service_gateway().session_roles.bind_by_index(
            session_id,
            int(index),
        )
        self._lifecycle.session_manager.load()
        self._lifecycle.refresh_sub_agent_bindings()
        logger.info(
            _TAG + " player character binding loaded history: session_id={}, index={}, first_message_appended={}, history_len={}",
            session_id,
            index,
            bool(result.first_message),
            len(self._lifecycle.session_manager.history),
        )
        return result

    def player_character_guard_reply(self) -> str:
        from rpg_data import models
        from rpg_data.services import get_data_service_gateway

        session_id = self._lifecycle.session_id
        if not session_id:
            return ""
        service = get_data_service_gateway().session_roles
        try:
            state = service.get_state(session_id)
        except FileNotFoundError:
            logger.warning(
                _TAG + " player character guard skipped missing session: session_id={}",
                session_id,
            )
            return ""
        if state.status == models.PLAYER_CHARACTER_STATUS_BOUND:
            return ""
        logger.info(
            _TAG + " player character guard requires binding: session_id={}, status={}",
            session_id,
            state.status,
        )
        return service.render_role_bind_prompt(session_id)

    async def reload_history(self) -> None:
        await self._wait_idle()
        self._lifecycle.session_manager.load()

    async def truncate_history_from_turn(self, turn_id: int) -> dict[str, object]:
        if self._mailbox is None:
            raise RuntimeError("AgentSessionService mailbox is not bound")
        return await self._mailbox.truncate_history_from_turn(int(turn_id))

    def truncate_history_from_turn_now(self, turn_id: int) -> dict[str, object]:
        boundary_turn = int(turn_id)
        if boundary_turn <= 0:
            raise ValueError("turn_id must be positive")
        session = self._lifecycle.session_manager
        session_id = self._lifecycle.session_id
        if session.first_user_message_for_turn(boundary_turn) is None:
            logger.warning(
                _TAG + " truncate rejected: user message not found, session_id={}, turn_id={}",
                session_id,
                boundary_turn,
            )
            raise ValueError(f"user message not found for turn: {boundary_turn}")

        before_count = len(session.history)
        logger.info(
            _TAG + " truncate starting: session_id={}, turn_id={}, history_count={}",
            session_id,
            boundary_turn,
            before_count,
        )
        try:
            removed = session.truncate_from_turn(boundary_turn)
        except Exception as exc:
            remaining_rows = self._history_rows()
            if any(int(row.turn_id) == boundary_turn for row in remaining_rows):
                raise
            logger.warning(
                _TAG + " truncate persisted but agent reload failed: session_id={}, turn_id={}, error={}",
                session_id,
                boundary_turn,
                exc,
            )
            return {
                "status": "truncated",
                "session_id": session_id,
                "turn_id": boundary_turn,
                "removed": max(0, before_count - len(remaining_rows)),
                "agent_sync_status": "failed",
                "agent_sync_error": str(exc),
            }

        logger.info(
            _TAG + " truncate completed: session_id={}, turn_id={}, removed={}, remaining_count={}",
            session_id,
            boundary_turn,
            removed,
            len(session.history),
        )
        return {
            "status": "truncated",
            "session_id": session_id,
            "turn_id": boundary_turn,
            "removed": removed,
            "agent_sync_status": "synced",
        }

    async def delete_message(self, message_id: int) -> Message:
        await self._wait_idle()
        return self._lifecycle.session_manager.delete_message(message_id)

    def clear_history(self) -> None:
        if self._lifecycle.initialized:
            self._lifecycle.session_manager.clear()

    async def reload_rpg_context(self) -> None:
        await self._lifecycle.reload_resources(self._tool_service)

    async def switch_session(self, session_id: str) -> None:
        await self._lifecycle.switch_session(
            session_id,
            tool_service=self._tool_service,
        )

    def reindex_memory(self) -> bool:
        return self._lifecycle.reindex_memory()

    def _history_rows(self):
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().messages.list(self._lifecycle.session_id)

    async def _wait_idle(self) -> None:
        if self._mailbox is not None:
            await self._mailbox.wait_idle()
