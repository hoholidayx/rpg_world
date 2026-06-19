"""rpg_world.run supervisor tests."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from rpg_world import launcher


def test_build_process_specs(monkeypatch):
    import rpg_world.run as run_module

    class FakeChannelsSettings:
        api_reload = False
        api_host = "127.0.0.1"
        api_port = 8123
        cli_enabled = True
        telegram_bots = [
            SimpleNamespace(enabled=True),
        ]

    monkeypatch.setattr(launcher, "channels_settings", FakeChannelsSettings())

    api_spec = launcher.build_process_spec("api")
    telegram_spec = launcher.build_process_spec("telegram")
    cli_spec = launcher.build_process_spec("cli")

    assert api_spec is not None
    assert api_spec.name == "api"
    assert api_spec.argv[:4] == (sys.executable, "-m", "uvicorn", "rpg_world.api.main:app")
    assert "--port" in api_spec.argv
    assert "8123" in api_spec.argv

    assert telegram_spec is not None
    assert telegram_spec.name == "telegram"
    assert telegram_spec.argv == (sys.executable, "-m", "rpg_world.channels.telegram.runner")

    assert cli_spec is not None
    assert cli_spec.name == "cli"
    assert cli_spec.argv == (sys.executable, "-m", "rpg_world.channels.cli.repl")


def test_build_process_spec_rejects_api_reload(monkeypatch):
    class FakeChannelsSettings:
        api_reload = True
        api_host = "127.0.0.1"
        api_port = 8000
        cli_enabled = True
        telegram_bots = []

    monkeypatch.setattr(launcher, "channels_settings", FakeChannelsSettings())

    with pytest.raises(ValueError, match="supervisor 模式不支持"):
        launcher.build_process_spec("api")


@pytest.mark.asyncio
async def test_main_returns_child_exit_code_on_unexpected_exit(monkeypatch):
    import rpg_world.run as run_module

    class FakeProcess:
        returncode = 7

        def terminate(self):
            return None

        def kill(self):
            return None

    exit_future = asyncio.get_running_loop().create_future()
    exit_future.set_result(7)

    fake_child = run_module.RunningProcess(
        spec=launcher.ProcessSpec(name="api", argv=("python",)),
        process=FakeProcess(),
        wait_task=exit_future,
    )

    async def fake_launch_children(modules):  # noqa: ANN001
        assert modules == ["api"]
        return [fake_child]

    stop_calls = []

    async def fake_stop_all(children):  # noqa: ANN001
        stop_calls.append(list(children))

    monkeypatch.setattr(run_module, "_launch_children", fake_launch_children)
    monkeypatch.setattr(run_module, "_stop_all_processes", fake_stop_all)
    monkeypatch.setattr(run_module, "_install_stop_handlers", lambda stop_event: None)
    monkeypatch.setattr(run_module, "resolve_modules", lambda args: ["api"])
    monkeypatch.setattr(run_module, "_parse_args", lambda: SimpleNamespace(modules="api"))

    code = await run_module.main()

    assert code == 7
    assert stop_calls and stop_calls[0] == []
