from __future__ import annotations

import asyncio

import run_all
import run_dashboard_api
import run_cli
import run_telegram


def test_run_dashboard_api_main_invokes_uvicorn(monkeypatch):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(run_dashboard_api.uvicorn, "run", _fake_run)

    assert run_dashboard_api.main() is None
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("dashboard_api.main:app",)
    assert kwargs["host"] == run_dashboard_api.channels_settings.dashboard_api_host
    assert kwargs["port"] == run_dashboard_api.channels_settings.dashboard_api_port
    assert kwargs["reload"] == run_dashboard_api.channels_settings.dashboard_api_reload
    assert kwargs["log_level"] == run_dashboard_api.api_settings.log_level.lower()


def test_run_telegram_main_forwards(monkeypatch):
    called = False

    async def _fake_main() -> int:
        nonlocal called
        called = True
        return 7

    monkeypatch.setattr(run_telegram, "_telegram_main", _fake_main)

    assert asyncio.run(run_telegram.main()) == 7
    assert called is True


def test_run_cli_main_forwards(monkeypatch):
    called = False

    async def _fake_main() -> int:
        nonlocal called
        called = True
        return 3

    monkeypatch.setattr(run_cli, "_cli_main", _fake_main)

    assert asyncio.run(run_cli.main()) == 3
    assert called is True


def test_run_all_main_forwards(monkeypatch):
    called = False

    async def _fake_main() -> int:
        nonlocal called
        called = True
        return 11

    monkeypatch.setattr(run_all, "_supervisor_main", _fake_main)

    assert asyncio.run(run_all.main()) == 11
    assert called is True
