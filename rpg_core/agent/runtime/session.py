"""Session, role, and history operations for ``RPGGameAgent``."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from rpg_core.agent.command.role import render_role_bind_prompt, resolve_role_index
from rpg_core.context.models import Message
from rpg_core.session.role import SessionRoleService
from rpg_core.session.reset import SessionResetService
from rpg_data.model.session import SESSION_LIFECYCLE_READY, Session

if TYPE_CHECKING:
    from rpg_data.model.session import SessionMessage
    from rpg_core.session.reset import SessionResetResult
    from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle
    from rpg_core.agent.mailbox import AgentMailbox
    from rpg_core.agent.runtime.tools import AgentToolService

_TAG = "[AgentSessionService]"


class AgentSessionDataPort(Protocol):
    def resolve_session_runtime_dir(self, session_id: str) -> Path: ...

    def list_messages(self, session_id: str) -> list["SessionMessage"]: ...

    def get_session(self, session_id: str) -> Session | None: ...

    def list_sessions(
        self,
        workspace_id: str,
        story_id: int,
    ) -> list[Session] | None: ...


class SessionCatalogCreator(Protocol):
    def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str,
    ) -> Session | None: ...


class AgentSessionService:
    """Own role guards and every mutable session-history operation."""

    def __init__(
        self,
        *,
        lifecycle: "AgentRuntimeLifecycle",
        tool_service: "AgentToolService",
        data: AgentSessionDataPort,
        catalog_creator: SessionCatalogCreator,
        role_service: SessionRoleService,
        reset_service: SessionResetService,
    ) -> None:
        self._lifecycle = lifecycle
        self._tool_service = tool_service
        self._data = data
        self._catalog_creator = catalog_creator
        self._role_service = role_service
        self._reset_service = reset_service
        self._mailbox: AgentMailbox | None = None

    def bind_mailbox(self, mailbox: "AgentMailbox") -> None:
        self._mailbox = mailbox

    @property
    def history(self) -> list[Message]:
        return self._lifecycle.session_manager.history

    def list_story_sessions(self) -> list[Session]:
        current = self._require_catalog_session()
        return self._data.list_sessions(
            str(current.workspace_id),
            int(current.story_id),
        ) or []

    def create_story_session(self, title: str) -> Session | None:
        current = self._require_catalog_session()
        return self._catalog_creator.create_session(
            str(current.workspace_id),
            int(current.story_id),
            title=str(title),
        )

    def can_switch_session(self, session_id: str) -> bool:
        current = self._require_catalog_session()
        target = self._data.get_session(str(session_id))
        return bool(
            target is not None
            and target.lifecycle == SESSION_LIFECYCLE_READY
            and str(target.workspace_id) == str(current.workspace_id)
            and int(target.story_id) == int(current.story_id)
        )

    def render_role_bind_prompt(self, *, error: str = "") -> str:
        return render_role_bind_prompt(
            self._role_service.list_options(self._lifecycle.session_id),
            self._role_service.get_state(self._lifecycle.session_id),
            error=error,
        )

    def bind_player_character_by_index(
        self,
        index: int,
        opening_index: int | None = None,
        *,
        story_opening_id: int | None = None,
    ):
        session_id = self._lifecycle.session_id
        logger.info(
            _TAG + " binding player character by index: session_id={}, index={}",
            session_id,
            index,
        )
        option = resolve_role_index(
            self._role_service.list_options(session_id),
            int(index),
        )
        selected_opening_id = (
            int(story_opening_id) if story_opening_id is not None else None
        )
        if opening_index is not None and selected_opening_id is not None:
            raise ValueError(
                "opening index and story opening id cannot both be provided"
            )
        if opening_index is not None:
            openings = self._role_service.list_opening_options(
                session_id,
                option.snapshot.character_id,
            )
            opening_position = int(opening_index)
            if opening_position < 1 or opening_position > len(openings):
                raise ValueError(f"无效开局序号: {opening_position}")
            selected_opening_id = openings[opening_position - 1].opening.id
        result = self._role_service.bind_player_character(
            session_id,
            option.snapshot.character_id,
            story_opening_id=selected_opening_id,
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
        from rpg_core.session.role import PlayerCharacterBindingStatus

        session_id = self._lifecycle.session_id
        if not session_id:
            return ""
        try:
            state = self._role_service.get_state(session_id)
        except FileNotFoundError:
            logger.warning(
                _TAG + " player character guard skipped missing session: session_id={}",
                session_id,
            )
            return ""
        if state.status is PlayerCharacterBindingStatus.BOUND:
            return ""
        logger.info(
            _TAG + " player character guard requires binding: session_id={}, status={}",
            session_id,
            state.status,
        )
        return render_role_bind_prompt(
            self._role_service.list_options(session_id),
            state,
        )

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

        if not self._lifecycle.initialized:
            raise RuntimeError("Agent runtime is not initialized")

        session_id = self._lifecycle.session_id
        runtime_dir = self._data.resolve_session_runtime_dir(session_id)
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

            result = self._reset_service.reset(session_id)
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
            + " session reset completed: session_id={}, messages={}, outcomes={}, plot_decisions={}, story_memories={}, template_status_tables_cleared={}, template_status_tables_initialized={}, native_status_tables_reset={}, first_message_appended={}",
            session_id,
            result.messages_cleared,
            result.narrative_outcomes_cleared,
            result.plot_schedule_decisions_cleared,
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

    def _history_rows(self) -> list["SessionMessage"]:
        return self._data.list_messages(self._lifecycle.session_id)

    def _require_catalog_session(self) -> Session:
        session_id = self._lifecycle.session_id
        session = self._data.get_session(session_id)
        if session is None:
            raise FileNotFoundError(
                f"Session not found in rpg_data: {session_id}"
            )
        return session

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
