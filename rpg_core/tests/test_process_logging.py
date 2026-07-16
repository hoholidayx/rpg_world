from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path

import pytest
from loguru import logger

from agent_service.settings import settings as agent_settings
from channels.config import settings as channel_settings
from commons import process_logging
from commons.process_logging import (
    ProcessLoggingSettings,
    build_uvicorn_log_config,
    configure_process_logging,
    parse_process_logging_settings,
)
from llm_service.settings import settings as llm_settings
from media_service.settings import settings as media_settings
from play_api.settings import play_settings


@pytest.fixture(autouse=True)
def _isolated_logging():
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    old_uvicorn_state = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
    }
    process_logging._reset_process_logging_for_tests()
    try:
        yield
    finally:
        process_logging._reset_process_logging_for_tests()
        root.handlers[:] = old_handlers
        root.setLevel(old_level)
        for name, (handlers, level, propagate) in old_uvicorn_state.items():
            configured = logging.getLogger(name)
            configured.handlers[:] = handlers
            configured.setLevel(level)
            configured.propagate = propagate
        logger.add(sys.stderr)


def test_process_logging_persists_loguru_stdlib_and_uvicorn_once(tmp_path):
    settings = ProcessLoggingSettings(directory=str(tmp_path), console_enabled=False)

    path = configure_process_logging("agent", settings)
    assert configure_process_logging("agent", settings) == path
    logger.info("loguru message")
    logging.getLogger("rpg_data.catalog").warning("stdlib message")
    logging.getLogger("uvicorn.access").info("uvicorn message")
    logger.complete()

    content = path.read_text(encoding="utf-8")
    assert content.count("loguru message") == 1
    assert content.count("stdlib message") == 1
    assert content.count("uvicorn message") == 1
    assert "| agent |" in content
    assert "rpg_data.catalog" in content
    assert "uvicorn.access" in content


def test_process_logging_keeps_console_output(capsys, tmp_path):
    configure_process_logging(
        "play_api",
        ProcessLoggingSettings(directory=str(tmp_path), console_enabled=True),
    )

    logger.info("console message")
    logger.complete()

    assert "console message" in capsys.readouterr().err


def test_uvicorn_log_config_reinitializes_spawned_process_logging(monkeypatch):
    settings = ProcessLoggingSettings()
    configured = []
    monkeypatch.setattr(
        process_logging,
        "configure_process_logging",
        lambda name, value: configured.append((name, value)),
    )
    config = build_uvicorn_log_config("agent", settings)
    handler_config = config["handlers"]["process_logging"]

    handler = handler_config["()"](
        process_name=handler_config["process_name"],
        settings=handler_config["settings"],
    )

    assert isinstance(handler, logging.Handler)
    assert configured == [("agent", settings)]
    assert config["loggers"]["uvicorn.asgi"]["propagate"] is True


def test_relative_log_directory_is_resolved_from_project_root(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    working_directory = tmp_path / "elsewhere"
    project_root.mkdir()
    working_directory.mkdir()
    monkeypatch.setattr(process_logging, "_PROJECT_ROOT", project_root)
    monkeypatch.chdir(working_directory)

    path = configure_process_logging(
        "cli",
        ProcessLoggingSettings(directory="logs", console_enabled=False),
    )

    assert path == project_root / "logs" / "cli.log"


def test_process_logging_rotates_compresses_and_limits_archives(tmp_path):
    path = configure_process_logging(
        "rolling",
        ProcessLoggingSettings(
            directory=str(tmp_path),
            rotation_size_mb=1,
            retention_count=2,
            compression="zip",
            console_enabled=False,
        ),
    )
    payload = "x" * 700_000
    for index in range(6):
        logger.info("batch={} {}", index, payload)
    logger.complete()

    archives = sorted(tmp_path.glob("rolling.*.log.zip"))
    assert path.is_file()
    assert len(archives) == 2
    assert all(zipfile.is_zipfile(archive) for archive in archives)


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ({"rotation_size_mb": 0}, "rotation_size_mb"),
        ({"retention_count": -1}, "retention_count"),
        ({"compression": "rar"}, "compression"),
        ({"directory": ""}, "directory"),
    ],
)
def test_process_logging_rejects_invalid_rolling_settings(raw, error):
    with pytest.raises(ValueError, match=error):
        parse_process_logging_settings(raw, label="test.logging")


def test_all_process_settings_expose_bounded_logging_defaults():
    settings = (
        agent_settings.logging,
        llm_settings.logging,
        media_settings.logging,
        play_settings.logging,
        channel_settings.logging,
    )

    assert all(item.directory == "logs" for item in settings)
    assert all(item.rotation_size_mb == 20 for item in settings)
    assert all(item.retention_count == 10 for item in settings)
    assert all(item.compression == "zip" for item in settings)
    assert all(item.console_enabled is True for item in settings)
