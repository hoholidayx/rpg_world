from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_service.runtime import AgentServiceRuntime
from commons.runtime_lifecycle import RuntimeCleanupError


def _settings(*, events_enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        llm_client=SimpleNamespace(
            base_url="http://127.0.0.1:1/llm/v1",
            token="token",
            request_timeout_ms=10,
            stream_timeout_ms=20,
        ),
        play_events=SimpleNamespace(
            enabled=events_enabled,
            token_env="TEST_PLAY_EVENT_TOKEN",
            endpoint_url="http://127.0.0.1:2/events",
            token="event-token",
            timeout_ms=10,
        ),
    )


class _Gateway:
    def __init__(self, events: list[str], label: str = "") -> None:
        self.catalog = object()
        self.sessions = object()
        self.messages = object()
        self._events = events
        self._label = label

    def initialize(self) -> None:
        self._events.append(f"gateway{self._label}.initialize")

    def close(self) -> None:
        self._events.append(f"gateway{self._label}.close")


@pytest.mark.asyncio
async def test_runtime_start_failure_cleans_configured_resources() -> None:
    events: list[str] = []

    class LLM:
        @classmethod
        async def aconfigure(cls, **_kwargs: object) -> None:
            events.append("llm.configure")
            raise ValueError("configure failed")

        @classmethod
        async def areset(cls) -> None:
            events.append("llm.reset")

    class Manager:
        @classmethod
        async def areset(cls) -> None:
            events.append("agents.reset")

    with pytest.raises(ValueError, match="configure failed"):
        await AgentServiceRuntime.create(
            gateway=_Gateway(events),
            settings=_settings(),
            agent_manager=Manager,
            llm_manager=LLM,
        )

    assert events == [
        "gateway.initialize",
        "llm.configure",
        "agents.reset",
        "llm.reset",
        "gateway.close",
    ]


@pytest.mark.asyncio
async def test_runtime_close_continues_after_failures_and_is_idempotent() -> None:
    events: list[str] = []

    class Worker:
        async def stop(self) -> None:
            events.append("worker.stop")
            raise RuntimeError("worker failed")

        async def interrupt_stale_jobs(self) -> bool:
            events.append("worker.interrupt")
            return True

    class Manager:
        @classmethod
        async def areset(cls) -> None:
            events.append("agents.reset")
            raise RuntimeError("agents failed")

    class Publisher:
        async def close(self) -> None:
            events.append("publisher.close")

    class LLM:
        @classmethod
        async def areset(cls) -> None:
            events.append("llm.reset")

    gateway = _Gateway(events)
    runtime = AgentServiceRuntime(
        catalog=gateway.catalog,
        session_data=gateway.sessions,
        messages=gateway.messages,
        session_catalog=object(),  # type: ignore[arg-type]
        session_roles=object(),  # type: ignore[arg-type]
        derivations=object(),  # type: ignore[arg-type]
        deletion=object(),  # type: ignore[arg-type]
        main_llm_selection=object(),  # type: ignore[arg-type]
        agent_manager=Manager,
        derivation_worker=Worker(),  # type: ignore[arg-type]
        _gateway=gateway,  # type: ignore[arg-type]
        _llm_manager=LLM,
        _event_publisher=Publisher(),  # type: ignore[arg-type]
        _llm_configured=True,
    )

    with pytest.raises(RuntimeCleanupError) as exc_info:
        await runtime.close()

    assert [failure.resource for failure in exc_info.value.failures] == [
        "derivation_worker",
        "agent_manager",
    ]
    assert events == [
        "worker.stop",
        "agents.reset",
        "worker.interrupt",
        "publisher.close",
        "llm.reset",
        "gateway.close",
    ]

    await runtime.close()
    assert events[-1] == "gateway.close"
    assert len(events) == 6


@pytest.mark.asyncio
async def test_two_runtime_entries_create_fresh_workers_and_resources() -> None:
    events: list[str] = []
    workers: list[object] = []

    class Worker:
        def __init__(self, **_kwargs: object) -> None:
            self.label = str(len(workers) + 1)
            workers.append(self)

        async def start(self) -> None:
            events.append(f"worker{self.label}.start")

        async def stop(self) -> None:
            events.append(f"worker{self.label}.stop")

        async def interrupt_stale_jobs(self) -> bool:
            events.append(f"worker{self.label}.interrupt")
            return True

    class Manager:
        @classmethod
        async def areset(cls) -> None:
            events.append("agents.reset")

    class LLM:
        @classmethod
        async def aconfigure(cls, **_kwargs: object) -> None:
            events.append("llm.configure")

        @classmethod
        async def areset(cls) -> None:
            events.append("llm.reset")

    runtimes: list[AgentServiceRuntime] = []
    for label in ("1", "2"):
        runtime = await AgentServiceRuntime.create(
            gateway=_Gateway(events, label),
            settings=_settings(),
            agent_manager=Manager,
            llm_manager=LLM,
            derivation_worker_factory=Worker,  # type: ignore[arg-type]
        )
        runtimes.append(runtime)
        await runtime.close()

    assert runtimes[0] is not runtimes[1]
    assert workers[0] is not workers[1]
    assert events == [
        "gateway1.initialize",
        "llm.configure",
        "worker1.start",
        "worker1.stop",
        "agents.reset",
        "worker1.interrupt",
        "llm.reset",
        "gateway1.close",
        "gateway2.initialize",
        "llm.configure",
        "worker2.start",
        "worker2.stop",
        "agents.reset",
        "worker2.interrupt",
        "llm.reset",
        "gateway2.close",
    ]
