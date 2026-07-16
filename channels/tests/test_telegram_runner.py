"""Telegram runner tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from channels.config import TelegramBotSettings


@pytest.fixture(autouse=True)
def _disable_real_process_logging(monkeypatch):
    import channels.telegram.runner as runner_module

    monkeypatch.setattr(
        runner_module,
        "configure_process_logging",
        lambda _name, _settings: None,
    )


def _make_bot(name: str, enabled: bool = True) -> TelegramBotSettings:
    return TelegramBotSettings(
        name=name,
        enabled=enabled,
        token=f"token-{name}",
        workspace_id=f"{name}_workspace",
        story_id=1,
        session_id="",
        session_title=name,
        streaming=True,
        proxy="",
        stream_edit_interval_ms=800,
        stream_edit_min_chars=24,
        request_timeout_ms=5000,
    )


@pytest.mark.asyncio
async def test_main_configures_telegram_process_logging(monkeypatch):
    import channels.telegram.runner as runner_module

    configured = []

    async def fake_start_enabled_bots(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        runner_module,
        "configure_process_logging",
        lambda name, settings: configured.append((name, settings)),
    )
    monkeypatch.setattr(
        runner_module,
        "_start_enabled_bots",
        fake_start_enabled_bots,
    )

    assert await runner_module.main() == 0
    assert configured == [("telegram", runner_module.channels_settings.logging)]


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

        async def ensure_session(self, workspace_id, story_id, *, session_id=None, title=""):  # noqa: ANN001
            return {
                "workspace": f"data/{workspace_id}",
                "story_id": story_id,
                "session_id": f"resolved_{workspace_id}",
                "title": title,
            }

        async def aclose(self):
            client_calls.append("closed")

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
    assert created_adapters[0]["workspace"] == "data/main_workspace"
    assert created_adapters[0]["workspace_id"] == "main_workspace"
    assert created_adapters[0]["story_id"] == 1
    assert created_adapters[0]["session_id"] == "resolved_main_workspace"
    assert created_adapters[0]["streaming"] is True
    assert created_adapters[1]["bot_name"] == "prod"
    assert created_adapters[1]["token"] == "token-prod"
    assert created_adapters[1]["workspace"] == "data/prod_workspace"
    assert all(runtime.client is not None for runtime in runtimes)


@pytest.mark.asyncio
async def test_startup_ensure_failure_closes_new_client(monkeypatch):
    import channels.telegram.runner as runner_module

    events = []

    class FakeChannelsSettings:
        telegram_bots = [_make_bot("main")]

    class FakeAgentClient:
        async def ensure_session(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            events.append("ensure")
            raise RuntimeError("boom")

        async def aclose(self):
            events.append("close")

    monkeypatch.setattr(runner_module, "channels_settings", FakeChannelsSettings())
    monkeypatch.setattr(runner_module, "AgentClient", FakeAgentClient)

    with pytest.raises(RuntimeError, match="boom"):
        await runner_module._start_enabled_bots(asyncio.Event())

    assert events == ["ensure", "close"]


@pytest.mark.asyncio
async def test_later_startup_failure_closes_prior_runtime_and_all_clients(monkeypatch):
    import channels.telegram.runner as runner_module

    events = []
    client_count = 0

    class FakeChannelsSettings:
        telegram_bots = [_make_bot("first"), _make_bot("second")]

    class FakeAgentClient:
        def __init__(self):
            nonlocal client_count
            client_count += 1
            self.number = client_count

        async def ensure_session(self, workspace_id, story_id, **_kwargs):  # noqa: ANN001
            events.append(f"ensure:{self.number}")
            if self.number == 2:
                raise RuntimeError("second failed")
            return {
                "workspace": f"data/{workspace_id}",
                "story_id": story_id,
                "session_id": "first_session",
                "title": "first",
            }

        async def aclose(self):
            events.append(f"client_close:{self.number}")

    class FakeTelegramAdapter:
        def __init__(self, **_kwargs):
            pass

        async def start(self):
            await asyncio.sleep(3600)

        async def stop(self):
            events.append("adapter_stop:1")

    monkeypatch.setattr(runner_module, "channels_settings", FakeChannelsSettings())
    monkeypatch.setattr(runner_module, "AgentClient", FakeAgentClient)
    monkeypatch.setattr(runner_module, "TelegramAdapter", FakeTelegramAdapter)

    with pytest.raises(RuntimeError, match="second failed"):
        await runner_module._start_enabled_bots(asyncio.Event())

    assert events == [
        "ensure:1",
        "ensure:2",
        "client_close:2",
        "adapter_stop:1",
        "client_close:1",
    ]


@pytest.mark.asyncio
async def test_main_stops_adapters_on_shutdown(monkeypatch):
    import channels.telegram.runner as runner_module

    events = []

    class FakeAdapter:
        def __init__(self):
            self.stop_called = 0

        async def stop(self):
            self.stop_called += 1
            events.append("adapter_stop")

    class FakeClient:
        async def aclose(self):
            events.append("client_close")

    adapter = FakeAdapter()
    start_task = asyncio.create_task(asyncio.sleep(3600))
    runtime = SimpleNamespace(
        bot_name="main",
        adapter=adapter,
        start_task=start_task,
        client=FakeClient(),
    )

    async def fake_start_enabled_bots(stop_event, fatal_error=None):  # noqa: ANN001
        stop_event.set()
        return [runtime]

    monkeypatch.setattr(runner_module, "_start_enabled_bots", fake_start_enabled_bots)
    monkeypatch.setattr(runner_module, "_install_stop_handlers", lambda stop_event: None)

    code = await runner_module.main()

    assert code == 0
    assert adapter.stop_called == 1
    assert start_task.cancelled()
    assert events == ["adapter_stop", "client_close"]


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
    runtime = SimpleNamespace(bot_name="main", adapter=adapter, start_task=start_task, client=None)

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
