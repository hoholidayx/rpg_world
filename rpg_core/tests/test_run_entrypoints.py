from __future__ import annotations

import asyncio
import logging

import run_agent
import run_cli
import run_play_api
import run_telegram


def test_run_play_api_main_invokes_uvicorn(monkeypatch):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    configured: list[bool] = []

    def _fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(run_play_api.uvicorn, "run", _fake_run)
    monkeypatch.setattr(run_play_api, "_configure_standard_logging", lambda: configured.append(True))

    assert run_play_api.main() is None
    assert configured == [True]
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("play_api.main:app",)
    assert kwargs["host"] == run_play_api.play_settings.service.host
    assert kwargs["port"] == run_play_api.play_settings.service.port
    assert kwargs["reload"] == run_play_api.play_settings.service.reload
    assert kwargs["log_level"] == run_play_api.play_settings.logging.log_level.lower()


def test_run_play_api_configures_application_logging(monkeypatch):
    root = logging.getLogger()
    old_level = root.level
    old_play_level = logging.getLogger("play_api").level
    old_data_level = logging.getLogger("rpg_data").level

    try:
        run_play_api._configure_standard_logging()

        expected_level = getattr(
            logging,
            run_play_api.play_settings.logging.log_level.upper(),
            logging.DEBUG,
        )
        assert root.level == expected_level
        assert logging.getLogger("play_api").level == expected_level
        assert logging.getLogger("rpg_data").level == expected_level
    finally:
        root.setLevel(old_level)
        logging.getLogger("play_api").setLevel(old_play_level)
        logging.getLogger("rpg_data").setLevel(old_data_level)


def test_run_agent_main_invokes_uvicorn(monkeypatch):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(run_agent.uvicorn, "run", _fake_run)

    assert run_agent.main() is None
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("agent_service.main:app",)
    assert kwargs["host"] == run_agent.agent_service_settings.service.host
    assert kwargs["port"] == run_agent.agent_service_settings.service.port


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
