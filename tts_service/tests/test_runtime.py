from __future__ import annotations

from types import SimpleNamespace

import pytest

from commons.runtime_lifecycle import RuntimeCleanupError
from tts_service import main as service_main
from tts_service.runtime import TTSRuntime


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
        self._events = events

    def close(self) -> None:
        self._events.append("gateway.close")


@pytest.mark.asyncio
async def test_tts_runtime_close_continues_and_is_idempotent() -> None:
    events: list[str] = []

    class Worker:
        async def stop(self) -> None:
            events.append("worker.stop")
            raise RuntimeError("worker failed")

    class LLM:
        @classmethod
        async def areset(cls) -> None:
            events.append("llm.reset")

    runtime = TTSRuntime(
        gateway=_Gateway(events),  # type: ignore[arg-type]
        service=object(),  # type: ignore[arg-type]
        worker=Worker(),  # type: ignore[arg-type]
    )
    runtime._llm_manager = LLM
    runtime._llm_configured = True

    with pytest.raises(RuntimeCleanupError) as exc_info:
        await runtime.close()

    assert [failure.resource for failure in exc_info.value.failures] == [
        "job_worker"
    ]
    assert events == ["worker.stop", "llm.reset", "gateway.close"]
    await runtime.close()
    assert len(events) == 3


@pytest.mark.asyncio
async def test_tts_runtime_start_failure_closes_database() -> None:
    events: list[str] = []

    class Worker:
        async def start(self) -> None:
            events.append("worker.start")
            raise ValueError("start failed")

        async def stop(self) -> None:
            events.append("worker.stop")

    class LLM:
        @classmethod
        async def aconfigure(cls, **_kwargs: object) -> None:
            events.append("llm.configure")

        @classmethod
        async def areset(cls) -> None:
            events.append("llm.reset")

    runtime = TTSRuntime(
        gateway=_Gateway(events),  # type: ignore[arg-type]
        service=object(),  # type: ignore[arg-type]
        worker=Worker(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="start failed"):
        await runtime.start(settings=_settings(), llm_manager=LLM)  # type: ignore[arg-type]

    assert events == [
        "llm.configure",
        "worker.start",
        "worker.stop",
        "llm.reset",
        "gateway.close",
    ]


@pytest.mark.asyncio
async def test_tts_lifespan_reentry_uses_fresh_runtime(monkeypatch) -> None:
    created: list[object] = []

    class Runtime:
        async def start(self, **_kwargs: object) -> None:
            return None

        async def close(self) -> None:
            return None

    async def create(**_kwargs: object):  # noqa: ANN202
        runtime = Runtime()
        created.append(runtime)
        return runtime

    service_main.set_runtime_for_tests(None)
    monkeypatch.setattr(service_main.TTSRuntime, "create", staticmethod(create))

    for _ in range(2):
        async with service_main.lifespan(service_main.app):
            assert service_main.get_runtime() is created[-1]
            assert service_main.app.state.tts_runtime is created[-1]
        with pytest.raises(RuntimeError, match="outside app lifespan"):
            service_main.get_runtime()

    assert created[0] is not created[1]
