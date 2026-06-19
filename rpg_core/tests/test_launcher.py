from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg_world import launcher


def test_resolve_modules_prefers_cli_args(monkeypatch):
    monkeypatch.setattr(launcher, "channels_settings", SimpleNamespace(enabled_module_names=["api"]))
    args = SimpleNamespace(modules="telegram, cli")

    assert launcher.resolve_modules(args) == ["telegram", "cli"]


def test_resolve_modules_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(launcher, "channels_settings", SimpleNamespace(enabled_module_names=["api", "cli"]))
    args = SimpleNamespace(modules="")

    assert launcher.resolve_modules(args) == ["api", "cli"]


def test_build_process_spec_for_api(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "channels_settings",
        SimpleNamespace(
            api_reload=False,
            api_host="127.0.0.1",
            api_port=8000,
            telegram_bots=[],
            cli_enabled=False,
        ),
    )

    spec = launcher.build_process_spec("api")
    assert spec is not None
    assert spec.name == "api"
    assert spec.argv[:3] == (launcher.sys.executable, "-m", "uvicorn")
    assert spec.argv[3:5] == ("rpg_world.api.main:app", "--host")


def test_build_process_spec_skips_disabled_cli(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "channels_settings",
        SimpleNamespace(
            api_reload=False,
            api_host="127.0.0.1",
            api_port=8000,
            telegram_bots=[],
            cli_enabled=False,
        ),
    )

    assert launcher.build_process_spec("cli") is None


def test_build_process_spec_skips_telegram_without_enabled_bot(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "channels_settings",
        SimpleNamespace(
            api_reload=False,
            api_host="127.0.0.1",
            api_port=8000,
            telegram_bots=[SimpleNamespace(enabled=False)],
            cli_enabled=False,
        ),
    )

    assert launcher.build_process_spec("telegram") is None


def test_build_process_spec_rejects_api_reload(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "channels_settings",
        SimpleNamespace(
            api_reload=True,
            api_host="127.0.0.1",
            api_port=8000,
            telegram_bots=[],
            cli_enabled=False,
        ),
    )

    with pytest.raises(ValueError, match="modules.api.reload=true"):
        launcher.build_process_spec("api")
