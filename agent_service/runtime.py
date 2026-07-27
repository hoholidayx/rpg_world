"""Lifespan-owned Agent service composition and cleanup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from loguru import logger

from agent_service.derivation_worker import SessionDerivationWorker
from agent_service.play_event_notifications import SessionDerivationPlayEventSink
from agent_service.settings import AgentServiceSettings
from commons.runtime_lifecycle import cleanup_runtime_resources
from llm_client.manager import LLMClientManager
from play_events import PlayEventPublisher
from play_events.auth import uses_default_play_event_token
from rpg_core.agent.manager import AgentManager
from rpg_core.agent.runtime.main_llm import MainLLMSelectionService
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.derivation import SessionDerivationService
from rpg_core.session.deletion import SessionDeletionService
from rpg_core.session.role import SessionRoleService
from rpg_data.services import (
    CatalogService,
    DataServiceGateway,
    MessageDataService,
    SessionDataService,
)


DerivationWorkerFactory = Callable[..., SessionDerivationWorker]
EventPublisherFactory = Callable[..., PlayEventPublisher]


class AgentManagerRuntime(Protocol):
    def get_or_create(self, session_id: str): ...  # noqa: ANN201

    async def areset(self) -> None: ...

    async def drop_session(self, session_id: str) -> None: ...

    async def begin_session_deletion(self, session_id: str) -> None: ...

    def finish_session_deletion(self, session_id: str) -> None: ...


class LLMClientManagerRuntime(Protocol):
    async def aconfigure(
        self,
        *,
        base_url: str,
        token: str,
        request_timeout_ms: int,
        stream_timeout_ms: int,
    ) -> None: ...

    async def areset(self) -> None: ...


@dataclass(slots=True)
class AgentServiceRuntime:
    """Own process resources and expose only preassembled narrow services."""

    catalog: CatalogService
    session_data: SessionDataService
    messages: MessageDataService
    session_catalog: SessionCatalogService
    session_roles: SessionRoleService
    derivations: SessionDerivationService
    deletion: SessionDeletionService
    main_llm_selection: MainLLMSelectionService
    agent_manager: AgentManagerRuntime
    derivation_worker: SessionDerivationWorker | None
    _gateway: DataServiceGateway = field(repr=False)
    _llm_manager: LLMClientManagerRuntime = field(repr=False)
    _event_publisher: PlayEventPublisher | None = field(default=None, repr=False)
    _llm_configured: bool = field(default=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    async def create(
        cls,
        *,
        gateway: DataServiceGateway,
        settings: AgentServiceSettings,
        agent_manager: AgentManagerRuntime = AgentManager,
        llm_manager: LLMClientManagerRuntime = LLMClientManager,
        derivation_worker_factory: DerivationWorkerFactory = SessionDerivationWorker,
        event_publisher_factory: EventPublisherFactory = PlayEventPublisher,
    ) -> "AgentServiceRuntime":
        """Initialize the complete runtime or clean every partial resource."""

        runtime: AgentServiceRuntime | None = None
        try:
            gateway.initialize()
            session_data = gateway.sessions
            runtime = cls(
                catalog=gateway.catalog,
                session_data=session_data,
                messages=gateway.messages,
                session_catalog=SessionCatalogService(session_data),
                session_roles=SessionRoleService(session_data),
                derivations=SessionDerivationService(session_data),
                deletion=SessionDeletionService(session_data),
                main_llm_selection=MainLLMSelectionService(gateway.catalog),
                agent_manager=agent_manager,
                derivation_worker=None,
                _gateway=gateway,
                _llm_manager=llm_manager,
            )
            await runtime._start(
                settings=settings,
                derivation_worker_factory=derivation_worker_factory,
                event_publisher_factory=event_publisher_factory,
            )
            return runtime
        except BaseException as startup_error:
            if runtime is None:
                try:
                    await cleanup_runtime_resources(
                        "AgentServiceRuntime",
                        (("data_gateway", gateway.close),),
                    )
                except BaseException as cleanup_error:
                    raise BaseExceptionGroup(
                        "AgentServiceRuntime startup and cleanup failed",
                        [startup_error, cleanup_error],
                    ) from startup_error
            else:
                try:
                    await runtime.close()
                except BaseException as cleanup_error:
                    raise BaseExceptionGroup(
                        "AgentServiceRuntime startup and cleanup failed",
                        [startup_error, cleanup_error],
                    ) from startup_error
            raise

    async def _start(
        self,
        *,
        settings: AgentServiceSettings,
        derivation_worker_factory: DerivationWorkerFactory,
        event_publisher_factory: EventPublisherFactory,
    ) -> None:
        llm_cfg = settings.llm_client
        # Mark before awaiting so a partially configured loop-owned client is
        # still reset if configuration itself raises.
        self._llm_configured = True
        await self._llm_manager.aconfigure(
            base_url=llm_cfg.base_url,
            token=llm_cfg.token,
            request_timeout_ms=llm_cfg.request_timeout_ms,
            stream_timeout_ms=llm_cfg.stream_timeout_ms,
        )

        notification_sink = None
        event_cfg = settings.play_events
        if event_cfg.enabled:
            if uses_default_play_event_token(event_cfg.token_env):
                logger.warning(
                    "{} is not set; using the local Play event token fallback",
                    event_cfg.token_env,
                )
            self._event_publisher = event_publisher_factory(
                endpoint_url=event_cfg.endpoint_url,
                token=event_cfg.token,
                timeout_ms=event_cfg.timeout_ms,
            )
            notification_sink = SessionDerivationPlayEventSink(
                self._event_publisher
            )

        self.derivation_worker = derivation_worker_factory(
            session_data=self.session_data,
            notification_sink=notification_sink,
        )
        await self.derivation_worker.start()

    async def close(self) -> None:
        """Close every owned resource in the required order, exactly once."""

        if self._closed:
            return
        self._closed = True
        worker = self.derivation_worker
        publisher = self._event_publisher
        steps = []
        if worker is not None:
            steps.append(("derivation_worker", worker.stop))
        steps.append(("agent_manager", self.agent_manager.areset))
        if worker is not None:
            steps.append(("derivation_stale_jobs", worker.interrupt_stale_jobs))
        if publisher is not None:
            steps.append(("event_publisher", publisher.close))
        if self._llm_configured:
            steps.append(("llm_client", self._llm_manager.areset))
        steps.append(("data_gateway", self._gateway.close))

        try:
            await cleanup_runtime_resources("AgentServiceRuntime", steps)
        finally:
            self.derivation_worker = None
            self._event_publisher = None


__all__ = ["AgentServiceRuntime"]
