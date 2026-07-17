"""Public composition facade for the RPG Agent runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from rpg_core.agent.protocol import AgentStreamEvent, TurnCancelResult
from rpg_core.agent.command.dispatcher import CommandDispatcher
from rpg_core.agent.command.models import CommandResult
from rpg_core.agent.runtime.context import AgentContextService
from rpg_core.agent.runtime.deferred_status import DeferredStatusCoordinator
from rpg_core.agent.runtime.derivation import (
    AgentDerivationService,
    SessionDerivationPreparationResult,
)
from rpg_core.agent.runtime.lifecycle import AgentRuntimeLifecycle
from rpg_core.agent.mailbox.service import AgentMailbox
from rpg_core.agent.runtime.model import MainModelRuntime
from rpg_core.agent.runtime.session import AgentSessionService
from rpg_core.agent.runtime.tools import AgentToolService
from rpg_core.tooling.base import BaseTool
from rpg_core.agent.turn import TurnMode, TurnRequest
from rpg_core.agent.turn.factory import TurnRuntimeFactory
from rpg_core.agent.turn.hooks.fixed import (
    MemoryRecallHook,
    PostCommitHooks,
    StatusPreflightHook,
    TurnDiagnostics,
)
from rpg_core.agent.turn.orchestrator import TurnOrchestrator
from rpg_core.agent.turn.planning import TurnPlanResolver
from rpg_core.agent.turn.preparation import TurnPreparation
from rpg_core.agent.turn.runner import AgentReply, run_chat_loop, run_chat_loop_stream
from rpg_core.agent.turn.service import AgentTurnService
from rpg_core.agent.runtime.main_llm import MainLLMSelectionService
from rpg_core.utils.tokenizer import TiktokenTokenCounter, TokenCounter

if TYPE_CHECKING:
    from rpg_data.models import SessionResetResult
    from rpg_core.agent.command.models import CommandDef
    from rpg_core.agent.turn.runner import ToolCallRecord
    from rpg_core.context.inspector import LayerInfo
    from rpg_core.context.rpg_context import Message
    from rpg_core.session import SessionManager


class RPGGameAgent:
    """Composition root and stable public API for one cached Agent session."""

    def __init__(
        self,
        session_id: str = "default",
        world_name: str = "Nanobot Realm",
        history_enabled: bool = True,
        tools: list[BaseTool] | None = None,
        token_counter: TokenCounter | None = None,
        main_llm_selection_service: MainLLMSelectionService | None = None,
    ) -> None:
        token_counter = token_counter or TiktokenTokenCounter()
        self._command_dispatcher = CommandDispatcher(agent=self)
        self._model_runtime = MainModelRuntime(
            selection_service=(
                main_llm_selection_service or MainLLMSelectionService()
            ),
            initial_model=None,
        )
        self._lifecycle = AgentRuntimeLifecycle(
            session_id=session_id,
            world_name=world_name,
            history_enabled=history_enabled,
            command_dispatcher=self._command_dispatcher,
        )
        self._context_service = AgentContextService(
            world_name=world_name,
            session_id=lambda: self._lifecycle.session_id,
            session_manager=self._lifecycle.session_manager,
            resources=lambda: self._lifecycle.resources,
            rp_module_registry=lambda: self._lifecycle.rp_module_registry,
            main_llm_selection=self._model_runtime.resolve,
            token_counter=token_counter,
        )
        self._tool_service = AgentToolService(
            session_id=lambda: self._lifecycle.session_id,
            resources=lambda: self._lifecycle.resources,
            extra_tools=tools,
        )
        self._session_service = AgentSessionService(
            lifecycle=self._lifecycle,
            tool_service=self._tool_service,
        )
        status_preflight = StatusPreflightHook(
            status_sub_agent=lambda: self._lifecycle.status_sub_agent,
            tool_service=self._tool_service,
        )
        preparation = TurnPreparation(
            context_service=self._context_service,
            tool_service=self._tool_service,
            memory_recall=MemoryRecallHook(
                lambda: self._lifecycle.resources,
                self._lifecycle.session_manager,
            ),
        )
        orchestrator = TurnOrchestrator(
            session_id=lambda: self._lifecycle.session_id,
            plan_resolver=TurnPlanResolver(
                lifecycle=self._lifecycle,
                context_service=self._context_service,
                model_runtime=self._model_runtime,
            ),
            runtime_factory=TurnRuntimeFactory(
                lifecycle=self._lifecycle,
                context_service=self._context_service,
                model_runtime=self._model_runtime,
                status_preflight=status_preflight,
            ),
            preparation=preparation,
            post_commit_hooks=PostCommitHooks(
                lifecycle=self._lifecycle,
                session_manager=self._lifecycle.session_manager,
            ),
            diagnostics=TurnDiagnostics(),
            sync_runner=run_chat_loop,
            stream_runner=run_chat_loop_stream,
        )
        self._turn_service = AgentTurnService(
            session_id=lambda: self._lifecycle.session_id,
            model=lambda: self._model_runtime.model,
            command_dispatcher=self._command_dispatcher,
            player_character_guard=self._session_service.player_character_guard_reply,
            orchestrator=orchestrator,
            stream_error_event=AgentMailbox.stream_error_event,
        )
        deferred_status = DeferredStatusCoordinator(self._lifecycle)
        self._derivation_service = AgentDerivationService(
            lifecycle=self._lifecycle,
            context_service=self._context_service,
        )
        self._mailbox = AgentMailbox(
            session_id=lambda: self._lifecycle.session_id,
            model=lambda: self._model_runtime.model,
            turn_service=self._turn_service,
            command_dispatcher=self._command_dispatcher,
            truncate_history=self._session_service.truncate_history_from_turn_now,
            materialize_derivation=self._derivation_service.materialize,
            deferred_status=deferred_status.run,
        )
        self._session_service.bind_mailbox(self._mailbox)

    @property
    def session_id(self) -> str:
        """Current globally unique session ID."""
        return self._lifecycle.session_id

    @property
    def session_manager(self) -> "SessionManager":
        """Read-only access for trusted internal command collaborators."""
        return self._lifecycle.session_manager

    async def initialize(self) -> None:
        """Idempotently initialize the session runtime and mailbox."""
        await self._lifecycle.initialize(
            tool_service=self._tool_service,
            mailbox=self._mailbox,
        )

    async def close(self) -> None:
        """Permanently stop this cached runtime and release session resources."""

        try:
            await self._mailbox.close()
        finally:
            await self._lifecycle.release_resources()

    async def send(
        self,
        user_input: str,
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> AgentReply:
        await self.initialize()
        return await self._mailbox.send(
            TurnRequest.create(
                user_input,
                mode=mode,
                narrative_style_id=narrative_style_id,
            )
        )

    async def send_stream(
        self,
        user_input: str,
        *,
        request_id: str | None = None,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        await self.initialize()
        request = TurnRequest.create(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
            request_id=request_id,
        )
        async for event in self._mailbox.send_stream(request):
            yield event

    async def cancel_current_turn(
        self,
        request_id: str | None = None,
    ) -> TurnCancelResult:
        return await self._mailbox.cancel_current_turn(request_id=request_id)

    async def execute_command(self, command: str) -> CommandResult:
        await self.initialize()
        return await self._mailbox.execute_command(command)

    async def materialize_derivation(self, job_id: str) -> object:
        """Create a derivation target at this source mailbox boundary."""

        await self.initialize()
        return await self._mailbox.materialize_derivation(job_id)

    async def prepare_derivation_target(
        self,
        job_id: str,
    ) -> SessionDerivationPreparationResult:
        """Prepare this provisioning target without entering the turn pipeline."""

        await self.initialize()
        return await self._derivation_service.prepare_target(job_id)

    def list_commands(self) -> list["CommandDef"]:
        return self._command_dispatcher.list_commands()

    def render_role_bind_prompt(self, *, error: str = "") -> str:
        return self._session_service.render_role_bind_prompt(error=error)

    def bind_player_character_by_index(self, index: int):
        return self._session_service.bind_player_character_by_index(index)

    @property
    def history(self) -> list["Message"]:
        return self._session_service.history

    async def reload_history(self) -> None:
        await self.initialize()
        await self._session_service.reload_history()

    async def truncate_history_from_turn(self, turn_id: int) -> dict[str, object]:
        await self.initialize()
        return await self._session_service.truncate_history_from_turn(turn_id)

    async def delete_message(self, message_id: int) -> "Message":
        await self.initialize()
        return await self._session_service.delete_message(message_id)

    @property
    def last_tool_records(self) -> list["ToolCallRecord"] | None:
        return self._turn_service.last_tool_records

    async def reset_session(self) -> "SessionResetResult":
        return await self._session_service.reset_session()

    async def reload_rpg_context(self) -> None:
        await self._session_service.reload_rpg_context()

    async def switch_session(self, session_id: str) -> None:
        await self._session_service.switch_session(session_id)

    async def reindex_memory(self) -> bool:
        return await self._session_service.reindex_memory()

    async def get_context_info(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> list["LayerInfo"]:
        await self.initialize()
        return await self._context_service.inspect_info(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )

    async def get_context_markdown(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> str:
        await self.initialize()
        return await self._context_service.inspect_markdown(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )

    async def get_context_payload(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> dict[str, object]:
        await self.initialize()
        return await self._context_service.inspect_payload(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )

    async def get_context_json(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> str:
        await self.initialize()
        return await self._context_service.inspect_json(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )
