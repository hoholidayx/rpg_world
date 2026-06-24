"""Telegram runner tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from channels.config import TelegramBotSettings


def _make_bot(name: str, enabled: bool = True) -> TelegramBotSettings:
    return TelegramBotSettings(
        name=name,
        enabled=enabled,
        token=f"token-{name}",
        workspace=f"data/{name}",
        streaming=True,
        proxy="",
        stream_edit_interval_ms=800,
        stream_edit_min_chars=24,
        request_timeout_ms=5000,
    )


@pytest.mark.asyncio
async def test_start_enabled_bots_creates_one_task_per_enabled_bot(monkeypatch):
    import channels.telegram.runner as runner_module

    created_adapters = []
    client_calls = []

    class FakeChannelsSettings:
        telegram_bots = [_make_bot("main"), _make_bot("prod"), _make_bot("off", enabled=False)]

    class FakeAgentClient:
        def __init__(self):
            client_calls.append("created")

    class FakeTelegramAdapter:
        def __init__(self, **kwargs):  # noqa: ANN003
            created_adapters.append(kwargs)

        async def start(self):
            return None

        async def stop(self):
            return None

    monkeypatch.setattr(runner_module, "channels_settings", FakeChannelsSettings())
    monkeypatch.setattr(runner_module, "AgentClient", FakeAgentClient)
    monkeypatch.setattr(runner_module, "TelegramAdapter", FakeTelegramAdapter)

    stop_event = asyncio.Event()
    runtimes = await runner_module._start_enabled_bots(stop_event)
    await asyncio.gather(*(runtime.start_task for runtime in runtimes))

    assert [runtime.bot_name for runtime in runtimes] == ["main", "prod"]
    assert client_calls == ["created", "created"]
    assert created_adapters[0]["bot_name"] == "main"
    assert created_adapters[0]["token"] == "token-main"
    assert created_adapters[0]["workspace"] == "data/main"
    assert created_adapters[0]["streaming"] is True
    assert created_adapters[1]["bot_name"] == "prod"
    assert created_adapters[1]["token"] == "token-prod"
    assert created_adapters[1]["workspace"] == "data/prod"


@pytest.mark.asyncio
async def test_main_stops_adapters_on_shutdown(monkeypatch):
    import channels.telegram.runner as runner_module

    class FakeAdapter:
        def __init__(self):
            self.stop_called = 0

        async def stop(self):
            self.stop_called += 1

    adapter = FakeAdapter()
    start_task = asyncio.create_task(asyncio.sleep(3600))
    runtime = SimpleNamespace(bot_name="main", adapter=adapter, start_task=start_task)

    async def fake_start_enabled_bots(stop_event, fatal_error=None):  # noqa: ANN001
        stop_event.set()
        return [runtime]

    monkeypatch.setattr(runner_module, "_start_enabled_bots", fake_start_enabled_bots)
    monkeypatch.setattr(runner_module, "_install_stop_handlers", lambda stop_event: None)

    code = await runner_module.main()

    assert code == 0
    assert adapter.stop_called == 1
    assert start_task.cancelled()


@pytest.mark.asyncio
async def test_main_returns_nonzero_on_startup_failure(monkeypatch):
    import channels.telegram.runner as runner_module

    class FakeAdapter:
        def __init__(self):
            self.stop_called = 0

        async def stop(self):
            self.stop_called += 1

    adapter = FakeAdapter()
    start_task = asyncio.create_task(asyncio.sleep(3600))
    runtime = SimpleNamespace(bot_name="main", adapter=adapter, start_task=start_task)

    async def fake_start_enabled_bots(stop_event, fatal_error=None):  # noqa: ANN001
        if fatal_error is not None:
            fatal_error.set()
        stop_event.set()
        return [runtime]

    monkeypatch.setattr(runner_module, "_start_enabled_bots", fake_start_enabled_bots)
    monkeypatch.setattr(runner_module, "_install_stop_handlers", lambda stop_event: None)

    code = await runner_module.main()

    assert code == 1
    assert adapter.stop_called == 1
    assert start_task.cancelled()
