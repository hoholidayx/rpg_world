from __future__ import annotations

from types import SimpleNamespace

import pytest

from commons.runtime_lifecycle import RuntimeCleanupError
from media_service import main as service_main
from media_service.runtime import MediaRuntime


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm_client=SimpleNamespace(
            base_url="http://127.0.0.1:1/llm/v1",
            token="token",
            request_timeout_ms=10,
            stream_timeout_ms=20,
        )
    )


class _Gateway:
    def __init__(self, events: list[str]) -> None:
        self.catalog = SimpleNamespace(get_session=lambda _session_id: None)
        self._events = events

    def close(self) -> None:
        self._events.append("gateway.close")


@pytest.mark.asyncio
async def test_media_runtime_start_failure_cleans_all_resources() -> None:
    events: list[str] = []

    class JobWorker:
        async def start(self) -> None:
            events.append("job.start")
            raise RuntimeError("job start failed")

        async def stop(self) -> None:
            events.append("job.stop")

    class BackgroundWorker:
        async def start(self) -> None:
            events.append("background.start")

        async def stop(self) -> None:
            events.append("background.stop")

    class LLM:
        @classmethod
        async def aconfigure(cls, **_kwargs: object) -> None:
            events.append("llm.configure")

        @classmethod
        async def areset(cls) -> None:
            events.append("llm.reset")

    runtime = MediaRuntime(
        gateway=_Gateway(events),  # type: ignore[arg-type]
        service=object(),  # type: ignore[arg-type]
        worker=JobWorker(),  # type: ignore[arg-type]
        background_worker=BackgroundWorker(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="job start failed"):
        await runtime.start(settings=_settings(), llm_manager=LLM)  # type: ignore[arg-type]

    assert events == [
        "llm.configure",
        "job.start",
        "background.stop",
        "job.stop",
        "llm.reset",
        "gateway.close",
    ]


@pytest.mark.asyncio
async def test_media_runtime_close_continues_and_is_idempotent() -> None:
    events: list[str] = []

    class JobWorker:
        async def stop(self) -> None:
            events.append("job.stop")

    class BackgroundWorker:
        async def stop(self) -> None:
            events.append("background.stop")
            raise RuntimeError("background failed")

    class LLM:
        @classmethod
        async def areset(cls) -> None:
            events.append("llm.reset")
            raise RuntimeError("llm failed")

    runtime = MediaRuntime(
        gateway=_Gateway(events),  # type: ignore[arg-type]
        service=object(),  # type: ignore[arg-type]
        worker=JobWorker(),  # type: ignore[arg-type]
        background_worker=BackgroundWorker(),  # type: ignore[arg-type]
    )
    runtime._llm_manager = LLM
    runtime._llm_configured = True

    with pytest.raises(RuntimeCleanupError) as exc_info:
        await runtime.close()

    assert [failure.resource for failure in exc_info.value.failures] == [
        "background_worker",
        "llm_client",
    ]
    assert events == [
        "background.stop",
        "job.stop",
        "llm.reset",
        "gateway.close",
    ]
    await runtime.close()
    assert len(events) == 4


@pytest.mark.asyncio
async def test_media_lifespan_reentry_uses_fresh_runtime(monkeypatch) -> None:
    created: list[object] = []
    events: list[str] = []

    class Runtime:
        async def start(self, **_kwargs: object) -> None:
            events.append(f"start:{id(self)}")

        async def close(self) -> None:
            events.append(f"close:{id(self)}")

    async def create(**_kwargs: object):  # noqa: ANN202
        runtime = Runtime()
        created.append(runtime)
        return runtime

    service_main.set_runtime_for_tests(None)
    monkeypatch.setattr(service_main.MediaRuntime, "create", staticmethod(create))

    for _ in range(2):
        async with service_main.lifespan(service_main.app):
            assert service_main.get_runtime() is created[-1]
            assert service_main.app.state.media_runtime is created[-1]
        with pytest.raises(RuntimeError, match="outside app lifespan"):
            service_main.get_runtime()

    assert created[0] is not created[1]
    assert len(events) == 4
