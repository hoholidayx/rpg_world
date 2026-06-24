from __future__ import annotations

from types import SimpleNamespace

import pytest

import launcher


def test_resolve_modules_prefers_cli_args(monkeypatch):
    monkeypatch.setattr(launcher, "channels_settings", SimpleNamespace(enabled_module_names=["dashboard_api"]))
    args = SimpleNamespace(modules="telegram, cli")

    assert launcher.resolve_modules(args) == ["telegram", "cli"]


def test_resolve_modules_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(launcher, "channels_settings", SimpleNamespace(enabled_module_names=["dashboard_api", "cli"]))
    args = SimpleNamespace(modules="")

    assert launcher.resolve_modules(args) == ["dashboard_api", "cli"]


def test_build_process_spec_for_api(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "channels_settings",
        SimpleNamespace(
            dashboard_api_reload=False,
            dashboard_api_host="127.0.0.1",
            dashboard_api_port=8000,
            telegram_bots=[],
            cli_enabled=False,
        ),
    )

    spec = launcher.build_process_spec("dashboard_api")
    assert spec is not None
    assert spec.name == "dashboard_api"
    assert spec.argv[:3] == (launcher.sys.executable, "-m", "uvicorn")
    assert spec.argv[3:5] == ("dashboard_api.main:app", "--host")


def test_build_process_spec_skips_disabled_cli(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "channels_settings",
        SimpleNamespace(
            dashboard_api_reload=False,
            dashboard_api_host="127.0.0.1",
            dashboard_api_port=8000,
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
            dashboard_api_reload=False,
            dashboard_api_host="127.0.0.1",
            dashboard_api_port=8000,
            telegram_bots=[SimpleNamespace(enabled=False)],
            cli_enabled=False,
        ),
    )

    assert launcher.build_process_spec("telegram") is None


def test_build_process_spec_rejects_dashboard_api_reload(monkeypatch):
    monkeypatch.setattr(
        launcher,
        "channels_settings",
        SimpleNamespace(
            dashboard_api_reload=True,
            dashboard_api_host="127.0.0.1",
            dashboard_api_port=8000,
            telegram_bots=[],
            cli_enabled=False,
        ),
    )

    with pytest.raises(ValueError, match="modules.dashboard_api.reload=true"):
        launcher.build_process_spec("dashboard_api")
