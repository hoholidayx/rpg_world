"""Session, role, and history operations for ``RPGGameAgent``."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from rpg_core.context.models import Message

if TYPE_CHECKING:
    from rpg_data.models import SessionResetResult
    from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.mailbox import AgentMailbox
    from rpg_core.agent.runtime.tools import AgentToolService

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
            self._clamp_deferred_progress(
                max((int(row.turn_id) for row in remaining_rows), default=0)
            )
            return {
                "status": "truncated",
                "session_id": session_id,
                "turn_id": boundary_turn,
                "removed": max(0, before_count - len(remaining_rows)),
                "agent_sync_status": "failed",
                "agent_sync_error": str(exc),
            }

        self._clamp_deferred_progress()
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
        deleted = self._lifecycle.session_manager.delete_message(message_id)
        self._clamp_deferred_progress()
        return deleted

    async def reset_session(self) -> "SessionResetResult":
        """Reset gameplay data, runtime files, and session-scoped resources."""

        from rpg_data.services import get_data_service_gateway

        if not self._lifecycle.initialized:
            raise RuntimeError("Agent runtime is not initialized")

        session_id = self._lifecycle.session_id
        gateway = get_data_service_gateway()
        runtime_dir = gateway.catalog.resolve_session_runtime_dir(session_id)
        quarantine_dir = runtime_dir.with_name(
            f".{runtime_dir.name}.clear-{uuid.uuid4().hex}"
        )
        runtime_moved = False
        database_reset = False
        logger.info(
            _TAG + " session reset starting: session_id={}, runtime_dir={}",
            session_id,
            runtime_dir,
        )

        try:
            await self._lifecycle.release_resources()
            if runtime_dir.exists():
                runtime_dir.rename(quarantine_dir)
                runtime_moved = True

            result = gateway.session_reset.reset(session_id)
            database_reset = True

            if runtime_moved:
                shutil.rmtree(quarantine_dir)

            await self._lifecycle.reload_resources(self._tool_service)
            self._lifecycle.session_manager.load()
        except Exception:
            logger.exception(
                _TAG + " session reset failed: session_id={}, database_reset={}",
                session_id,
                database_reset,
            )
            self._recover_reset_runtime(
                runtime_dir=runtime_dir,
                quarantine_dir=quarantine_dir,
                runtime_moved=runtime_moved,
                restore_old_runtime=not database_reset,
            )
            try:
                await self._lifecycle.reload_resources(self._tool_service)
                self._lifecycle.session_manager.load()
            except Exception:
                logger.exception(
                    _TAG + " session reset recovery reload failed: session_id={}",
                    session_id,
                )
            raise

        logger.info(
            _TAG
            + " session reset completed: session_id={}, messages={}, outcomes={}, story_memories={}, template_status_tables_cleared={}, template_status_tables_initialized={}, native_status_tables_reset={}, first_message_appended={}",
            session_id,
            result.messages_cleared,
            result.narrative_outcomes_cleared,
            result.story_memories_cleared,
            result.template_status_tables_cleared,
            result.template_status_tables_initialized,
            result.session_native_status_tables_reset,
            bool(result.first_message),
        )
        return result

    @staticmethod
    def _recover_reset_runtime(
        *,
        runtime_dir: Path,
        quarantine_dir: Path,
        runtime_moved: bool,
        restore_old_runtime: bool,
    ) -> None:
        if not runtime_moved or not quarantine_dir.exists():
            return
        if restore_old_runtime:
            if runtime_dir.exists():
                shutil.rmtree(runtime_dir)
            quarantine_dir.rename(runtime_dir)
            return
        try:
            shutil.rmtree(quarantine_dir)
        except Exception:
            logger.exception(
                _TAG + " failed to remove quarantined reset runtime: path={}",
                quarantine_dir,
            )

    async def reload_rpg_context(self) -> None:
        await self._lifecycle.reload_resources(self._tool_service)

    async def reindex_memory(self) -> bool:
        return await self._lifecycle.reindex_memory()

    def _history_rows(self):
        from rpg_data.services import get_data_service_gateway

        return get_data_service_gateway().messages.list(self._lifecycle.session_id)

    def _clamp_deferred_progress(self, max_turn_id: int | None = None) -> None:
        if not self._lifecycle.initialized:
            return
        status_manager = self._lifecycle.resources.status_manager
        if status_manager is None:
            return
        boundary = (
            self._lifecycle.session_manager.latest_turn_id(
                self._lifecycle.session_manager.history
            )
            if max_turn_id is None
            else max(0, int(max_turn_id))
        )
        try:
            status_manager.clamp_deferred_progress(boundary)
        except Exception as exc:
            logger.opt(exception=exc).warning(
                _TAG + " failed to clamp deferred status progress: session_id={}, max_turn_id={}",
                self._lifecycle.session_id,
                boundary,
            )

    async def _wait_idle(self) -> None:
        if self._mailbox is not None:
            await self._mailbox.wait_idle()
