from __future__ import annotations

from types import SimpleNamespace

import pytest

from channels.config import ChannelLoggingSettings


def test_cli_logging_uses_shared_process_pipeline(monkeypatch):
    import channels.cli.repl as repl

    logging_settings = ChannelLoggingSettings()
    configured = []
    monkeypatch.setattr(
        repl,
        "channels_settings",
        SimpleNamespace(logging=logging_settings),
    )
    monkeypatch.setattr(
        repl,
        "configure_process_logging",
        lambda name, settings: configured.append((name, settings)),
    )

    repl._configure_logging()

    assert configured == [("cli", logging_settings)]


@pytest.mark.asyncio
async def test_cli_main_configures_logging_before_agent_client(monkeypatch):
    import channels.cli.repl as repl

    events = []

    class FakeAgentClient:
        def __init__(self):
            events.append("client")

        async def ensure_session(self, *_args, **_kwargs):
            events.append("ensure")
            return {
                "session_id": "session_1",
                "workspace": "data/demo",
                "title": "CLI",
            }

    class FakeAdapter:
        def __init__(self, **_kwargs):
            events.append("adapter")

        def bind_agent_client(self, _client):
            events.append("bind")

        async def start(self):
            events.append("start")

    settings = SimpleNamespace(
        cli_player_character_id=0,
        cli_workspace_id="demo",
        cli_story_id=1,
        cli_session_id="",
        cli_session_title="CLI",
        cli_streaming=True,
    )
    monkeypatch.setattr(repl, "_configure_logging", lambda: events.append("logging"))
    monkeypatch.setattr(repl, "channels_settings", settings)
    monkeypatch.setattr(repl, "AgentClient", FakeAgentClient)
    monkeypatch.setattr(repl, "CLIAdapter", FakeAdapter)

    assert await repl.main() == 0
    assert events == ["logging", "client", "ensure", "adapter", "bind", "start"]
