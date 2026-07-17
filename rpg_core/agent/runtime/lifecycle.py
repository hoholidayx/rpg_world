"""Session-scoped runtime lifecycle for the Agent composition."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from llm_client.keys import (
    AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
)
from rpg_core.agent.runtime.resources import (
    AgentContextResources,
    build_agent_context_resources,
)
from rpg_core.agent.sub_agents.context import SubAgentContext
from rpg_core.agent.sub_agents.memory.agent import MemorySubAgent
from rpg_core.agent.sub_agents.status.agent import StatusSubAgent
from rpg_core.session import SessionManager
from rpg_core.settings import settings
from rpg_core.summary.compressor import SummaryCompressor
from rpg_core.utils.watcher import get_watcher

if TYPE_CHECKING:
    from rpg_core.agent.command.dispatcher import CommandDispatcher
    from rpg_core.agent.mailbox import AgentMailbox
    from rpg_core.agent.runtime.tools import AgentToolService
    from rpg_core.rp_modules import RPModuleRegistry

ContextResourceFactory = Callable[..., AgentContextResources]

_TAG = "[AgentRuntimeLifecycle]"


class AgentRuntimeLifecycle:
    """Own initialization and rebinding of all session-scoped resources."""

    def __init__(
        self,
        *,
        session_id: str,
        world_name: str,
        history_enabled: bool,
        command_dispatcher: "CommandDispatcher",
        resource_factory: ContextResourceFactory = build_agent_context_resources,
    ) -> None:
        self._session_id = session_id
        self._world_name = world_name
        self._command_dispatcher = command_dispatcher
        self._resource_factory = resource_factory
        self._session_manager = SessionManager(
            session_id=session_id,
            history_enabled=history_enabled,
        )
        self._resources = self._build_resources(session_id)
        self._rp_module_registry: RPModuleRegistry | None = None
        self._status_sub_agent: StatusSubAgent | None = None
        self._memory_sub_agent: MemorySubAgent | None = None
        self._compressor: SummaryCompressor | None = None
        self._initialized = False
        self._init_lock: asyncio.Lock | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    @property
    def resources(self) -> AgentContextResources:
        return self._resources

    @property
    def rp_module_registry(self) -> "RPModuleRegistry | None":
        return self._rp_module_registry

    @property
    def status_sub_agent(self) -> StatusSubAgent | None:
        return self._status_sub_agent

    @property
    def memory_sub_agent(self) -> MemorySubAgent | None:
        return self._memory_sub_agent

    @property
    def compressor(self) -> SummaryCompressor | None:
        return self._compressor

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def initialize(
        self,
        *,
        tool_service: "AgentToolService",
        mailbox: "AgentMailbox",
    ) -> None:
        """Initialize exactly once and start the serialized mailbox."""
        if self._initialized:
            return
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()

        async with self._init_lock:
            if self._initialized:
                return

            self._setup_rp_module_registry()
            self._session_manager.load()
            if self._resources.memory_manager is not None:
                await self._resources.memory_manager.initialize()
            self._create_sub_agents()
            self._configure_commands()
            tool_service.refresh_base_registry()
            get_watcher().start()
            mailbox.start()
            self._initialized = True

    async def reload_resources(self, tool_service: "AgentToolService") -> None:
        """Rebuild managers/stores and rebind all dependent collaborators."""
        if not self._initialized:
            return
        await self._replace_resources(self._session_id)
        if self._resources.memory_manager is not None:
            await self._resources.memory_manager.initialize()
        tool_service.refresh_base_registry()

    async def release_resources(self) -> None:
        """Close the active resource set before destructive session file work."""

        await self._resources.close()

    def refresh_sub_agent_bindings(self) -> None:
        """Refresh cached SubAgent context after session-local role changes."""

        self._refresh_sub_agent_bindings()

    async def switch_session(
        self,
        session_id: str,
        *,
        tool_service: "AgentToolService",
    ) -> None:
        """Switch the complete runtime while preserving provider reuse semantics."""
        if self._session_id == session_id:
            return
        self._session_id = session_id
        await self._replace_resources(session_id)
        if self._resources.memory_manager is not None:
            await self._resources.memory_manager.initialize()
        get_watcher().start()
        self._session_manager.switch_to(session_id)
        tool_service.refresh_base_registry()
        logger.info(_TAG + " switched to session: {}", session_id)

    async def reindex_memory(self) -> bool:
        manager = self._resources.memory_manager
        if manager is None:
            return False
        await manager.reindex()
        return True

    def _build_resources(self, session_id: str) -> AgentContextResources:
        return self._resource_factory(
            world_name=self._world_name,
            session_id=session_id,
        )

    async def _replace_resources(self, session_id: str) -> None:
        replacement = self._build_resources(session_id)
        await self._resources.close()
        self._resources = replacement
        builder = self._resources.builder
        if self._memory_sub_agent is not None:
            self._memory_sub_agent.replace_session_stores(
                summary_store=builder.summary_store,
                story_store=builder.story_memory_store,
                batch_store=builder.batch_summary_store,
            )
        if self._compressor is not None:
            self._compressor.replace_session_resources(
                batch_store=builder.batch_summary_store,
                memory_sub_agent=self._memory_sub_agent,
            )
        self._refresh_sub_agent_bindings()
        if self._rp_module_registry is not None:
            self._setup_rp_module_registry()

    def _setup_rp_module_registry(self) -> None:
        from rpg_core.rp_modules import RPModuleRegistry

        self._rp_module_registry = RPModuleRegistry(
            settings=getattr(settings, "rp_module_settings", None),
        )

    def _create_sub_agents(self) -> None:
        status_cfg = settings.status_sub_agent_config
        self._status_sub_agent = StatusSubAgent(
            provider_biz_key=AGENT_STATUS_SUB_AGENT_BIZ_KEY,
            enabled=status_cfg.get("enabled", True),
        )
        memory_cfg = settings.memory_sub_agent_config
        builder = self._resources.builder
        self._memory_sub_agent = MemorySubAgent(
            provider_biz_key=AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
            enabled=memory_cfg.get("enabled", True),
            summary_store=builder.summary_store,
            story_store=builder.story_memory_store,
            batch_store=builder.batch_summary_store,
            max_story_items=settings.memory_story_max_items,
            max_window_rounds=settings.memory_keep_rounds,
        )
        self._compressor = SummaryCompressor(
            batch_store=builder.batch_summary_store,
            memory_sub_agent=self._memory_sub_agent,
            enabled=settings.memory_compression_enabled,
            keep_recent_rounds=settings.memory_keep_rounds,
            compression_threshold=settings.memory_keep_rounds,
            compress_batch_size=settings.memory_compress_batch_size,
            max_batch_chars=settings.memory_summary_max_batch_chars,
        )
        self._refresh_sub_agent_bindings()

    def _refresh_sub_agent_bindings(self) -> None:
        context = _build_sub_agent_context(
            self._resources,
            session_id=self._session_id,
        )
        if self._status_sub_agent is not None:
            providers = (
                [self._resources.scene_tracker]
                if self._resources.scene_tracker is not None
                else []
            )
            self._status_sub_agent.replace_tool_providers(providers)
            self._status_sub_agent.bind_context(context)
        if self._memory_sub_agent is not None:
            self._memory_sub_agent.bind_context(
                _build_sub_agent_context(
                    self._resources,
                    session_id=self._session_id,
                )
            )

    def _configure_commands(self) -> None:
        self._command_dispatcher.register_default_builtins()
        self._command_dispatcher.replace_command_providers([
            lambda: self._rp_module_registry.get_commands(self._session_id)
            if self._rp_module_registry is not None
            else []
        ])
        sub_agents = []
        if self._status_sub_agent is not None and self._status_sub_agent.enabled:
            sub_agents.append(self._status_sub_agent)
        if self._memory_sub_agent is not None and self._memory_sub_agent.enabled:
            sub_agents.append(self._memory_sub_agent)
        self._command_dispatcher.replace_sub_agents(sub_agents)


def _build_sub_agent_context(
    resources: AgentContextResources,
    *,
    session_id: str,
) -> SubAgentContext:
    lorebook_entries: list[dict[str, object]] = []
    if resources.lorebook_manager is not None:
        try:
            lorebook_entries = resources.lorebook_manager.list_enabled_entries()
        except Exception:
            pass

    characters: list[dict[str, object]] = []
    if resources.character_manager is not None:
        try:
            characters = resources.character_manager.list_enabled_characters()
        except Exception:
            pass

    player_character = None
    try:
        from rpg_data import models
        from rpg_data.services import get_data_service_gateway

        state = get_data_service_gateway().session_roles.get_state(session_id)
        if state.status == models.PLAYER_CHARACTER_STATUS_BOUND:
            player_character = state.player
    except FileNotFoundError:
        logger.debug(
            _TAG + " SubAgent player context skipped missing session: session_id={}",
            session_id,
        )

    return SubAgentContext(
        lorebook_entries=lorebook_entries,
        characters=characters,
        player_character=player_character,
    )
