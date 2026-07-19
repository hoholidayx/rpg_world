"""Context construction, inspection, and the pre-transaction window gate."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from loguru import logger

from commons.errors import MainContextWindowThresholdExceededError
from rpg_core.agent.runtime.resources import AgentContextResources
from rpg_core.agent.turn import TurnExecutionSnapshot, TurnMode, TurnRequest
from rpg_core.agent.turn.resolver import TurnSnapshotResolver
from rpg_core.context.fixed_layer import FixedLayerAssembler
from rpg_core.context.fixed_layer.contributors import (
    CharacterFixedLayerContributor,
    CoreRPContractContributor,
    LorebookFixedLayerContributor,
    PlayerCharacterFixedLayerContributor,
    StaticFixedLayerContributor,
    StoryPromptFixedLayerContributor,
    TextOutputFormatFixedLayerContributor,
    TurnExecutionFixedLayerContributor,
)
from rpg_core.context.inspector import ContextInspector
from rpg_core.context.models import FixedLayerData, LayerType, Message, Role, RPGContext
from rpg_core.context.renderer import ContextRenderer
from rpg_core.status.context import render_status_tables_context
from rpg_core.context.usage import estimate_rendered_context_usage
from rpg_core.settings import settings

if TYPE_CHECKING:
    from rpg_core.context.inspector import LayerInfo
    from rpg_core.context.models import PersistentMemoryFact, RPGContext
    from rpg_core.agent.runtime.main_llm import MainLLMSelection
    from rpg_core.rp_modules.models import RPModuleSelectionSnapshot
    from rpg_core.rp_modules.registry import RPModuleRegistry
    from rpg_core.rp_modules.runtime import RPModuleTurnRuntime
    from rpg_core.rp_modules.plot_scheduler import PlotScheduleSnapshot
    from rpg_core.scene import SceneTracker
    from rpg_core.session import SessionManager
    from rpg_core.status.manager import StatusManager
    from rpg_core.utils.tokenizer import TokenCounter

_TAG = "[AgentContextService]"


class AgentContextService:
    """Build the one canonical main-Agent context for preview and turns."""

    def __init__(
        self,
        *,
        world_name: str,
        session_id: Callable[[], str],
        session_manager: "SessionManager",
        resources: Callable[[], AgentContextResources],
        rp_module_registry: Callable[[], "RPModuleRegistry | None"],
        main_llm_selection: Callable[[str], Awaitable["MainLLMSelection"]],
        token_counter: "TokenCounter",
    ) -> None:
        self._world_name = world_name
        self._session_id = session_id
        self._session_manager = session_manager
        self._resources = resources
        self._rp_module_registry = rp_module_registry
        self._main_llm_selection = main_llm_selection
        self._token_counter = token_counter

    def resolve_turn_execution(
        self,
        request: TurnRequest,
        *,
        require_player_character: bool = False,
    ) -> TurnExecutionSnapshot:
        return TurnSnapshotResolver(self._session_id()).resolve(
            request,
            require_player_character=require_player_character,
        )

    def resolve_rp_module_snapshot(self) -> "RPModuleSelectionSnapshot":
        registry = self._rp_module_registry()
        if registry is not None:
            return registry.resolve_snapshot(self._session_id())

        from rpg_core.rp_modules.models import RPModuleSelectionSnapshot

        return RPModuleSelectionSnapshot(
            session_id=self._session_id(),
            story_id=0,
            global_enabled=False,
            modules=(),
        )

    def build_transformed_context(
        self,
        *,
        current_user_message: Message | None = None,
        status_manager: "StatusManager | None" = None,
        scene_tracker: "SceneTracker | None" = None,
        user_input: str = "",
        rp_module_runtime: "RPModuleTurnRuntime | None" = None,
        turn_execution: TurnExecutionSnapshot | None = None,
        persistent_memory_snapshot: tuple["PersistentMemoryFact", ...] = (),
    ) -> list[Message]:
        context = self.build_main_context(
            current_user_message=current_user_message,
            status_manager=status_manager,
            scene_tracker=scene_tracker,
            user_input=user_input,
            include_staged_turn_runtime=True,
            rp_module_runtime=rp_module_runtime,
            turn_execution=turn_execution,
            persistent_memory_snapshot=persistent_memory_snapshot,
        )
        messages = context.to_message_objects()
        self._log_verbose_context(context)
        return messages

    def build_plot_judge_messages(
        self,
        *,
        judge_prompt: str,
        current_user_input: str,
        history_turns: int,
        status_manager: "StatusManager | None",
        scene_tracker: "SceneTracker | None",
        rp_module_runtime: "RPModuleTurnRuntime | None",
        turn_execution: TurnExecutionSnapshot,
    ) -> list[Message]:
        """Build the scheduler's bounded raw context without memory projections."""
        fixed_layer = self._assemble_fixed_layer(
            rp_module_runtime.get_fixed_sections()
            if rp_module_runtime is not None
            else None,
            turn_execution=turn_execution,
        )
        fixed_text = ContextRenderer(
            RPGContext(fixed_layer=fixed_layer)
        ).render_layer(LayerType.FIXED)
        messages: list[Message] = []
        if fixed_text:
            messages.append(Message(Role.SYSTEM, fixed_text))
        messages.append(Message(Role.SYSTEM, judge_prompt))

        state_sections: list[str] = []
        if scene_tracker is not None:
            state_sections.append(scene_tracker.get_context())
        if status_manager is not None:
            status_text = render_status_tables_context(
                status_manager.list_context_tables()
            )
            if status_text:
                state_sections.append(status_text)
        if state_sections:
            messages.append(
                Message(
                    Role.SYSTEM,
                    "当前 Scene 与状态表：\n" + "\n\n".join(state_sections),
                )
            )

        messages.extend(self._recent_raw_ic_gm_messages(history_turns))
        messages.append(Message(Role.USER, str(current_user_input or "")))
        return messages

    def _recent_raw_ic_gm_messages(self, turn_count: int) -> list[Message]:
        from rpg_core.agent.turn.models import TurnMode

        groups: list[list[Message]] = []
        for group in self._session_manager.iter_turn_groups(
            self._session_manager.history
        ):
            conversation = [
                item
                for item in group
                if not item.is_system() and not item.is_tool()
            ]
            modes = {
                str(item.mode or TurnMode.IC.value).lower()
                for item in conversation
            }
            if modes and modes.issubset({TurnMode.IC.value, TurnMode.GM.value}):
                # Keep the entire persisted turn, including any tool messages.
                groups.append(list(group))
        selected = groups[-max(1, int(turn_count)):]
        return [message for group in selected for message in group]

    def build_main_context(
        self,
        *,
        current_user_message: Message | None = None,
        status_manager: "StatusManager | None" = None,
        scene_tracker: "SceneTracker | None" = None,
        user_input: str = "",
        include_staged_turn_runtime: bool = False,
        rp_module_runtime: "RPModuleTurnRuntime | None" = None,
        turn_execution: TurnExecutionSnapshot | None = None,
        persistent_memory_snapshot: tuple["PersistentMemoryFact", ...] = (),
    ) -> "RPGContext":
        resources = self._resources()
        fixed_layer = self._assemble_fixed_layer(
            rp_module_runtime.get_fixed_sections()
            if rp_module_runtime is not None
            else None,
            turn_execution=turn_execution,
        )
        history = self._session_manager.context_history()
        context = resources.builder.build(
            fixed_layer=fixed_layer,
            history_messages=list(history.messages),
            current_user_message=current_user_message,
            summarized_message_count=history.filtered_message_count,
            status_mgr=(
                resources.status_manager
                if status_manager is None
                else status_manager
            ),
            scene_tracker=(
                resources.scene_tracker
                if scene_tracker is None
                else scene_tracker
            ),
            rp_module_sections=self._runtime_sections(
                user_input=user_input,
                include_staged_turn=include_staged_turn_runtime,
                rp_module_runtime=rp_module_runtime,
                turn_execution=turn_execution,
            ),
            persistent_memory_snapshot=persistent_memory_snapshot,
        )
        return context

    def build_for_inspection(
        self,
        user_input: str = "",
        *,
        rp_module_snapshot: "RPModuleSelectionSnapshot | None" = None,
        turn_execution: TurnExecutionSnapshot | None = None,
        persistent_memory_snapshot: tuple["PersistentMemoryFact", ...] = (),
    ) -> "RPGContext":
        resources = self._resources()
        scene_ctx = (
            resources.scene_tracker.get_context()
            if resources.scene_tracker is not None
            else None
        )
        current_user_message: Message | None = None
        if user_input or scene_ctx:
            current_user_message = Message(
                role=Role.USER,
                content=self.compose_scene_user_input(scene_ctx, user_input),
                mode=(
                    turn_execution.request.mode.value
                    if turn_execution is not None
                    else TurnMode.IC.value
                ),
            )

        registry = self._rp_module_registry()
        if registry is None:
            return self.build_main_context(
                current_user_message=current_user_message,
                status_manager=resources.status_manager,
                scene_tracker=resources.scene_tracker,
                user_input=user_input,
                turn_execution=turn_execution,
                persistent_memory_snapshot=persistent_memory_snapshot,
            )

        runtime = registry.create_runtime(
            rp_module_snapshot or self.resolve_rp_module_snapshot()
        )
        try:
            return self.build_main_context(
                current_user_message=current_user_message,
                status_manager=resources.status_manager,
                scene_tracker=resources.scene_tracker,
                user_input=user_input,
                rp_module_runtime=runtime,
                turn_execution=turn_execution,
                persistent_memory_snapshot=persistent_memory_snapshot,
            )
        finally:
            runtime.close()

    def enforce_window_threshold(
        self,
        selection: "MainLLMSelection",
        *,
        rp_module_snapshot: "RPModuleSelectionSnapshot",
        turn_execution: TurnExecutionSnapshot,
        persistent_memory_snapshot: tuple["PersistentMemoryFact", ...] = (),
        plot_schedule_snapshot: "PlotScheduleSnapshot | None" = None,
    ) -> None:
        context_limit = selection.effective.context_window
        if context_limit is None or context_limit <= 0:
            logger.warning(
                _TAG + " context threshold skipped because window is unknown: session_id={}, provider={}",
                self._session_id(),
                selection.effective_provider_key,
            )
            return

        threshold_ratio = float(
            getattr(settings, "context_window_reject_threshold_ratio", 0.9)
        )
        current_context = self.build_for_inspection(
            "",
            rp_module_snapshot=rp_module_snapshot,
            turn_execution=turn_execution,
            persistent_memory_snapshot=persistent_memory_snapshot,
        )
        usage = estimate_rendered_context_usage(
            current_context.to_message_objects(),
            self._token_counter,
            context_limit=context_limit,
        )
        if usage.used_tokens is None:
            logger.warning(
                _TAG + " context threshold skipped because usage is unknown: session_id={}, provider={}",
                self._session_id(),
                selection.effective_provider_key,
            )
            return

        reserved_tokens = (
            self._token_counter.count(plot_schedule_snapshot.context_gate_reserve_text)
            if (
                plot_schedule_snapshot is not None
                and plot_schedule_snapshot.enabled
                and turn_execution.policy.expose_rp_modules
                and turn_execution.request.mode is not TurnMode.OOC
            )
            else 0
        )
        effective_used_tokens = usage.used_tokens + reserved_tokens
        usage_ratio = effective_used_tokens / context_limit
        logger.debug(
            _TAG + " context threshold evaluated: session_id={}, provider={}, used={}, limit={}, ratio={:.4f}, threshold={:.4f}, source={}",
            self._session_id(),
            selection.effective_provider_key,
            effective_used_tokens,
            context_limit,
            usage_ratio,
            threshold_ratio,
            usage.source,
        )
        if usage_ratio < threshold_ratio:
            return
        logger.warning(
            _TAG + " normal input rejected by context threshold: session_id={}, provider={}, used={}, limit={}, ratio={:.4f}, threshold={:.4f}",
            self._session_id(),
            selection.effective_provider_key,
            effective_used_tokens,
            context_limit,
            usage_ratio,
            threshold_ratio,
        )
        raise MainContextWindowThresholdExceededError(
            used_tokens=effective_used_tokens,
            context_limit=context_limit,
            threshold_ratio=threshold_ratio,
        )

    async def load_persistent_memory_snapshot(
        self,
    ) -> tuple["PersistentMemoryFact", ...]:
        """Load an immutable SQL projection without blocking the Agent loop."""

        try:
            return await self._resources().builder.load_persistent_memory_snapshot()
        except Exception as exc:
            logger.warning(
                _TAG + " persistent memory load skipped: session_id={}, error={}",
                self._session_id(),
                exc,
            )
            return ()

    async def inspect_info(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> list["LayerInfo"]:
        return (await self._inspector(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )).layer_summary()

    async def inspect_markdown(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> str:
        return (await self._inspector(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )).to_markdown()

    async def inspect_payload(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> dict[str, object]:
        return (await self._inspector(
            user_input,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )).to_payload(session_id=self._session_id())

    async def inspect_json(
        self,
        user_input: str = "",
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
    ) -> str:
        return json.dumps(
            await self.inspect_payload(
                user_input,
                mode=mode,
                narrative_style_id=narrative_style_id,
            ),
            ensure_ascii=False,
            indent=2,
        )

    async def _inspector(
        self,
        user_input: str,
        *,
        mode: TurnMode | str | None,
        narrative_style_id: int | None,
    ) -> ContextInspector:
        persistent_memory_snapshot = await self.load_persistent_memory_snapshot()
        execution = self.resolve_turn_execution(
            TurnRequest.create(
                user_input,
                mode=mode,
                narrative_style_id=narrative_style_id,
            )
        )
        context = self.build_for_inspection(
            user_input,
            turn_execution=execution,
            persistent_memory_snapshot=persistent_memory_snapshot,
        )
        selection = await self._main_llm_selection(self._session_id())
        return ContextInspector(
            context,
            self._token_counter,
            hot_history_rounds=self._resources().builder.config.hot_history_rounds,
            context_limit=selection.effective.context_window,
        )

    def _assemble_fixed_layer(
        self,
        rp_fixed_sections: list | None = None,
        *,
        turn_execution: TurnExecutionSnapshot | None = None,
    ) -> FixedLayerData:
        resources = self._resources()
        config = resources.builder.config
        contributors = [
            CoreRPContractContributor(self._world_name),
            StoryPromptFixedLayerContributor(
                self._session_id(),
                content=(
                    turn_execution.rendered_story_prompt
                    if turn_execution is not None
                    else None
                ),
            ),
            LorebookFixedLayerContributor(
                resources.lorebook_manager,
                enabled=getattr(config, "enable_lorebook", True),
            ),
            PlayerCharacterFixedLayerContributor(
                turn_execution.player_character
                if turn_execution is not None
                else None
            ),
            CharacterFixedLayerContributor(
                resources.character_manager,
                enabled=getattr(config, "enable_character", True),
                player_character=(
                    turn_execution.player_character
                    if turn_execution is not None
                    else None
                ),
            ),
        ]
        if turn_execution is not None:
            contributors.append(TurnExecutionFixedLayerContributor(turn_execution))
        if turn_execution is None or turn_execution.request.mode is not TurnMode.OOC:
            contributors.append(TextOutputFormatFixedLayerContributor())
        assembler = FixedLayerAssembler(
            world_name=self._world_name,
            contributors=contributors,
        )
        if rp_fixed_sections and (
            turn_execution is None or turn_execution.policy.expose_rp_modules
        ):
            assembler = assembler.with_contributor(
                StaticFixedLayerContributor(rp_fixed_sections)
            )
        return assembler.assemble()

    def _runtime_sections(
        self,
        *,
        user_input: str,
        include_staged_turn: bool,
        rp_module_runtime: "RPModuleTurnRuntime | None",
        turn_execution: TurnExecutionSnapshot | None,
    ) -> list:
        sections = []
        if rp_module_runtime is not None and (
            turn_execution is None or turn_execution.policy.expose_rp_modules
        ):
            from rpg_core.rp_modules.models import ModuleContextRequest

            sections = rp_module_runtime.get_runtime_sections(
                ModuleContextRequest(
                    session_id=self._session_id(),
                    user_input=user_input,
                    include_staged_turn=include_staged_turn,
                )
            )
        if settings.verbose_logging:
            logger.debug(
                _TAG + " RP runtime sections prepared: session_id={} include_staged_turn={} count={}",
                self._session_id(),
                include_staged_turn,
                len(sections),
            )
        return sections

    def _log_verbose_context(self, context: "RPGContext") -> None:
        """Log the rendered context by layer without duplicating history text."""
        if not settings.verbose_logging:
            return
        try:
            content = ContextInspector(context, self._token_counter).to_verbose_log()
        except Exception as exc:
            logger.warning(
                _TAG + " verbose context logging skipped: session_id={}, error={}",
                self._session_id(),
                exc,
            )
            return
        logger.debug(
            _TAG + " current context prepared: session_id={} content=\n{}",
            self._session_id(),
            content,
        )

    @staticmethod
    def compose_scene_user_input(scene_context: str | None, user_input: str) -> str:
        if scene_context and user_input:
            return f"{scene_context}\n{user_input}"
        return scene_context or user_input
