"""Explicit process runtime for the TTS service."""

from __future__ import annotations

from llm_client.manager import LLMClientManager

from commons.runtime_lifecycle import LLMClientLifecycle, cleanup_runtime_resources
from rpg_data.services import get_data_service_gateway
from rpg_data.services.gateway import DataServiceGateway
from rpg_tts.service import TTSApplicationService
from tts_service.settings import TTSServiceSettings
from tts_service.worker import TTSJobWorker


class TTSRuntime:
    """Own the TTS application service, worker, and process resources."""

    def __init__(
        self,
        *,
        gateway: DataServiceGateway,
        service: TTSApplicationService,
        worker: TTSJobWorker,
    ) -> None:
        self.service = service
        self.worker = worker
        self._gateway = gateway
        self._llm_manager: LLMClientLifecycle = LLMClientManager
        self._llm_configured = False
        self._started = False
        self._closed = False

    @classmethod
    async def create(
        cls,
        *,
        settings: TTSServiceSettings,
        llm_manager: LLMClientLifecycle = LLMClientManager,
    ) -> "TTSRuntime":
        gateway = get_data_service_gateway()
        llm_configured = False
        try:
            gateway.initialize()
            llm = settings.llm_client
            # TTSApplicationService captures the current manager at
            # construction time, so configure the loop-owned client first.
            llm_configured = True
            await llm_manager.aconfigure(
                base_url=llm.base_url,
                token=llm.token,
                request_timeout_ms=llm.request_timeout_ms,
                stream_timeout_ms=llm.stream_timeout_ms,
            )
            service = TTSApplicationService(data=gateway.tts)
            runtime = cls(
                gateway=gateway,
                service=service,
                worker=TTSJobWorker(
                    service=service,
                    concurrency=settings.worker.concurrency,
                ),
            )
            runtime._llm_manager = llm_manager
            runtime._llm_configured = True
            return runtime
        except BaseException as startup_error:
            steps = []
            if llm_configured:
                steps.append(("llm_client", llm_manager.areset))
            steps.append(("data_gateway", gateway.close))
            try:
                await cleanup_runtime_resources(
                    "TTSRuntime",
                    steps,
                )
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "TTSRuntime startup and cleanup failed",
                    [startup_error, cleanup_error],
                ) from startup_error
            raise

    async def start(
        self,
        *,
        settings: TTSServiceSettings,
        llm_manager: LLMClientLifecycle = LLMClientManager,
    ) -> None:
        if self._closed:
            raise RuntimeError("TTSRuntime is already closed")
        if self._started:
            return
        try:
            if not self._llm_configured:
                self._llm_manager = llm_manager
                llm = settings.llm_client
                self._llm_configured = True
                await self._llm_manager.aconfigure(
                    base_url=llm.base_url,
                    token=llm.token,
                    request_timeout_ms=llm.request_timeout_ms,
                    stream_timeout_ms=llm.stream_timeout_ms,
                )
            await self.worker.start()
            self._started = True
        except BaseException as startup_error:
            try:
                await self.close()
            except BaseException as cleanup_error:
                raise BaseExceptionGroup(
                    "TTSRuntime startup and cleanup failed",
                    [startup_error, cleanup_error],
                ) from startup_error
            raise

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await cleanup_runtime_resources(
                "TTSRuntime",
                (
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


__all__ = ["TTSRuntime"]
