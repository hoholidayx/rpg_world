"""Explicit process runtime for the Media service."""

from __future__ import annotations

from typing import Protocol

from llm_client.manager import LLMClientManager

from commons.runtime_lifecycle import LLMClientLifecycle, cleanup_runtime_resources
from media_service.settings import MediaServiceSettings
from media_service.worker import MediaBackgroundWorker, MediaJobWorker
from rpg_core.scene.status import SceneStatusService
from rpg_data import models
from rpg_data.services import get_data_service_gateway
from rpg_data.services.gateway import DataServiceGateway
from rpg_media.brief import LLMVisualBriefPlanner
from rpg_media.providers.catalog import build_provider_catalog
from rpg_media.service import MediaApplicationService
from rpg_media.settings import settings as media_settings


class MediaCatalogPort(Protocol):
    """Only the Session lookup needed by the Media HTTP adapter."""

    def get_session(self, session_id: str) -> models.Session | None: ...


class MediaRuntime:
    """Own Media workers, LLM client lifecycle, and the private data Gateway."""

    def __init__(
        self,
        *,
        gateway: DataServiceGateway,
        service: MediaApplicationService,
        worker: MediaJobWorker,
        background_worker: MediaBackgroundWorker | None = None,
    ) -> None:
        self.service = service
        self.catalog: MediaCatalogPort = gateway.catalog
        self.worker = worker
        self.background_worker = background_worker or MediaBackgroundWorker(
            service=service,
            concurrency=1,
        )
        self._gateway = gateway
        self._llm_manager: LLMClientLifecycle = LLMClientManager
        self._llm_configured = False
        self._started = False
        self._closed = False

    @classmethod
    async def create(
        cls,
        *,
        settings: MediaServiceSettings,
    ) -> "MediaRuntime":
        gateway = get_data_service_gateway()
        try:
            gateway.initialize()
            service = MediaApplicationService(
                data=gateway.media,
                catalog=gateway.catalog,
                planner=LLMVisualBriefPlanner(),
                providers=build_provider_catalog(media_settings.providers),
                status=SceneStatusService(gateway.status),
            )
            return cls(
                gateway=gateway,
                service=service,
                worker=MediaJobWorker(
                    service=service,
                    concurrency=settings.worker.concurrency,
                ),
                background_worker=MediaBackgroundWorker(
                    service=service,
                    concurrency=settings.background_worker.concurrency,
                ),
            )
        except BaseException as startup_error:
            try:
                await cleanup_runtime_resources(
                    "MediaRuntime",
                    (("data_gateway", gateway.close),),
                )
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "MediaRuntime startup and cleanup failed",
                    [startup_error, cleanup_error],
                ) from startup_error
            raise

    async def start(
        self,
        *,
        settings: MediaServiceSettings,
        llm_manager: LLMClientLifecycle = LLMClientManager,
    ) -> None:
        if self._closed:
            raise RuntimeError("MediaRuntime is already closed")
        if self._started:
            return
        self._llm_manager = llm_manager
        llm = settings.llm_client
        self._llm_configured = True
        try:
            await self._llm_manager.aconfigure(
                base_url=llm.base_url,
                token=llm.token,
                request_timeout_ms=llm.request_timeout_ms,
                stream_timeout_ms=llm.stream_timeout_ms,
            )
            await self.worker.start()
            await self.background_worker.start()
            self._started = True
        except BaseException as startup_error:
            try:
                await self.close()
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "MediaRuntime startup and cleanup failed",
                    [startup_error, cleanup_error],
                ) from startup_error
            raise

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await cleanup_runtime_resources(
                "MediaRuntime",
                (
                    ("background_worker", self.background_worker.stop),
                    ("job_worker", self.worker.stop),
                    *(
                        (("llm_client", self._llm_manager.areset),)
                        if self._llm_configured
                        else ()
                    ),
                    ("data_gateway", self._gateway.close),
                ),
            )
        finally:
            self._started = False


__all__ = ["MediaCatalogPort", "MediaRuntime"]
