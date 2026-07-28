from __future__ import annotations

from types import SimpleNamespace

import pytest

from commons.runtime_lifecycle import RuntimeCleanupError
from play_api import main as play_main
from play_api import runtime as runtime_module
from play_api.runtime import PlayServiceRuntime


class _Closeable:
    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        fail: bool = False,
    ) -> None:
        self.name = name
        self.events = events
        self.fail = fail

    async def aclose(self) -> None:
        self.events.append(f"{self.name}.close")
        if self.fail:
            raise RuntimeError(f"{self.name} failed")


@pytest.mark.asyncio
async def test_play_runtime_start_failure_closes_partial_resources(
    monkeypatch,
) -> None:
    events: list[str] = []

    class Hub:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def close(self) -> None:
            events.append("hub.close")

    class Data:
        @classmethod
        def create(cls):  # noqa: ANN206
            events.append("data.create")
            return cls()

        def close(self) -> None:
            events.append("data.close")

    monkeypatch.setattr(runtime_module, "uses_default_play_event_token", lambda _env: False)
    monkeypatch.setattr(runtime_module, "PlayEventHub", Hub)
    monkeypatch.setattr(runtime_module, "PlayDataRuntime", Data)
    monkeypatch.setattr(
        runtime_module,
        "create_agent_client",
        lambda: _Closeable("agent", events),
    )
    monkeypatch.setattr(
        runtime_module,
        "create_dream_client",
        lambda: _Closeable("dream", events),
    )
    monkeypatch.setattr(
        runtime_module,
        "create_media_client",
        lambda: _Closeable("media", events),
    )

    def fail_tts():
        raise ValueError("tts construction failed")

    monkeypatch.setattr(runtime_module, "create_tts_client", fail_tts)
    settings = SimpleNamespace(
        events=SimpleNamespace(
            token_env="TEST_TOKEN",
            subscriber_queue_capacity=4,
            token="token",
            heartbeat_seconds=1.0,
            retry_ms=100,
        )
    )

    with pytest.raises(ValueError, match="tts construction failed"):
        await PlayServiceRuntime.create(settings=settings)  # type: ignore[arg-type]

    assert events == [
        "data.create",
        "hub.close",
        "dream.close",
        "media.close",
        "agent.close",
        "data.close",
    ]


@pytest.mark.asyncio
async def test_play_runtime_close_order_continues_and_is_idempotent() -> None:
    events: list[str] = []

    class Hub:
        async def close(self) -> None:
            events.append("hub.close")

    class Data:
        def close(self) -> None:
            events.append("data.close")

    runtime = PlayServiceRuntime(
        events=SimpleNamespace(),  # type: ignore[arg-type]
        data=Data(),  # type: ignore[arg-type]
        agent_client=_Closeable("agent", events),  # type: ignore[arg-type]
        dream_client=_Closeable("dream", events, fail=True),  # type: ignore[arg-type]
        media_client=_Closeable("media", events),  # type: ignore[arg-type]
        tts_client=_Closeable("tts", events),  # type: ignore[arg-type]
        _event_hub=Hub(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeCleanupError) as exc_info:
        await runtime.close()

    assert [failure.resource for failure in exc_info.value.failures] == [
        "dream_client"
    ]
    assert events == [
        "hub.close",
        "dream.close",
        "media.close",
        "tts.close",
        "agent.close",
        "data.close",
    ]
    await runtime.close()
    assert len(events) == 6


@pytest.mark.asyncio
async def test_play_lifespan_reentry_uses_fresh_runtime(monkeypatch) -> None:
    created: list[object] = []

    class Runtime:
        def __init__(self) -> None:
            self.events = object()
            self.data = object()
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    async def create(**_kwargs: object):  # noqa: ANN202
        runtime = Runtime()
        created.append(runtime)
        return runtime

    monkeypatch.setattr(
        play_main.PlayServiceRuntime,
        "create",
        staticmethod(create),
    )

    for _ in range(2):
        async with play_main.lifespan(play_main.app):
            assert play_main.app.state.play_runtime is created[-1]
            assert play_main.app.state.play_events is created[-1].events
            assert play_main.app.state.play_data is created[-1].data
        assert not hasattr(play_main.app.state, "play_runtime")
        assert not hasattr(play_main.app.state, "play_events")
        assert not hasattr(play_main.app.state, "play_data")

    assert created[0] is not created[1]
    assert all(runtime.closed for runtime in created)
