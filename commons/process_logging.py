"""Shared process-level logging configuration.

The runtime uses both Loguru and the standard library logging package.  This
module gives every standalone process one consistent console and rolling-file
pipeline without requiring business modules to care which logging API they
use.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Mapping

from loguru import logger

from commons.settings import optional_bool
from commons.types import YamlValue


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SUPPORTED_COMPRESSIONS = frozenset(
    {
        "bz2",
        "gz",
        "lzma",
        "tar",
        "tar.bz2",
        "tar.gz",
        "tar.xz",
        "xz",
        "zip",
    }
)
_CONFIGURE_LOCK = RLock()
_configured_signature: tuple[object, ...] | None = None


@dataclass(frozen=True)
class ProcessLoggingSettings:
    """Logging settings shared by every independent process."""

    log_level: str = "DEBUG"
    directory: str = "logs"
    rotation_size_mb: int = 20
    retention_count: int = 10
    compression: str = "zip"
    console_enabled: bool = True


def parse_process_logging_settings(
    raw: Mapping[str, YamlValue],
    *,
    label: str,
) -> ProcessLoggingSettings:
    """Parse and validate one process's logging mapping."""
    directory = str(raw.get("directory", "logs") or "").strip()
    if not directory:
        raise ValueError(f"{label}.directory must not be empty")

    rotation_size_mb = _positive_int(
        raw.get("rotation_size_mb", 20),
        label=f"{label}.rotation_size_mb",
    )
    retention_count = _positive_int(
        raw.get("retention_count", 10),
        label=f"{label}.retention_count",
    )
    compression = str(raw.get("compression", "zip") or "").strip().lower()
    if compression not in _SUPPORTED_COMPRESSIONS:
        supported = ", ".join(sorted(_SUPPORTED_COMPRESSIONS))
        raise ValueError(
            f"{label}.compression must be one of {supported}; got {compression!r}"
        )

    return ProcessLoggingSettings(
        log_level=str(raw.get("log_level", "DEBUG") or "DEBUG").strip().upper(),
        directory=directory,
        rotation_size_mb=rotation_size_mb,
        retention_count=retention_count,
        compression=compression,
        console_enabled=optional_bool(raw.get("console_enabled", True), True),
    )


def configure_process_logging(
    process_name: str,
    settings: ProcessLoggingSettings,
) -> Path:
    """Configure console and rolling-file output for one standalone process."""
    normalized_name = process_name.strip()
    if not normalized_name:
        raise ValueError("process_name must not be empty")

    log_directory = _resolve_log_directory(settings.directory)
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / f"{normalized_name}.log"
    signature = (
        normalized_name,
        log_path,
        settings.log_level,
        settings.rotation_size_mb,
        settings.retention_count,
        settings.compression,
        settings.console_enabled,
    )

    global _configured_signature
    with _CONFIGURE_LOCK:
        if _configured_signature == signature:
            return log_path

        logger.remove()
        logger.configure(extra={"process": normalized_name})
        sink_options = {
            "level": settings.log_level,
            "format": _format_record,
            "backtrace": False,
            "diagnose": False,
            "enqueue": True,
        }
        if settings.console_enabled:
            logger.add(sys.stderr, colorize=True, **sink_options)
        logger.add(
            log_path,
            colorize=False,
            encoding="utf-8",
            rotation=f"{settings.rotation_size_mb} MB",
            retention=settings.retention_count,
            compression=settings.compression,
            **sink_options,
        )

        _configure_standard_logging(settings.log_level)
        _configured_signature = signature
    return log_path


def build_uvicorn_log_config(
    process_name: str,
    settings: ProcessLoggingSettings,
) -> dict[str, object]:
    """Build a spawn-safe Uvicorn logging config for the process pipeline.

    Uvicorn applies ``log_config`` again inside reload/worker subprocesses.
    The handler factory therefore re-establishes the Loguru sinks in each
    spawned application process before forwarding standard-library records.
    """
    handler_name = "process_logging"
    logger_config = {
        "handlers": [],
        "level": settings.log_level,
        "propagate": True,
    }
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            handler_name: {
                "()": _create_uvicorn_intercept_handler,
                "process_name": process_name,
                "settings": settings,
            }
        },
        "root": {
            "handlers": [handler_name],
            "level": settings.log_level,
        },
        "loggers": {
            name: dict(logger_config)
            for name in (
                "uvicorn",
                "uvicorn.access",
                "uvicorn.asgi",
                "uvicorn.error",
            )
        },
    }


def _create_uvicorn_intercept_handler(
    *,
    process_name: str,
    settings: ProcessLoggingSettings,
) -> logging.Handler:
    configure_process_logging(process_name, settings)
    return _InterceptHandler()


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


def _resolve_log_directory(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path.resolve()


def _format_record(record: dict) -> str:
    extra = record["extra"]
    extra["source"] = extra.get("stdlib_logger_name", record["name"])
    extra["source_function"] = extra.get("stdlib_function", record["function"])
    return (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{extra[process]} | {extra[source]}:{extra[source_function]} - {message}\n"
        "{exception}"
    )


class _InterceptHandler(logging.Handler):
    """Forward standard-library records into the configured Loguru sinks."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.bind(
            stdlib_logger_name=record.name,
            stdlib_function=record.funcName,
        ).opt(exception=record.exc_info).log(level, "{}", record.getMessage())


def _configure_standard_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.DEBUG)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(_InterceptHandler())
    root.setLevel(level)
    logging.captureWarnings(True)

    # Uvicorn loggers must propagate into the root bridge both before and after
    # Uvicorn applies the spawn-safe config returned above.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        stdlib_logger = logging.getLogger(logger_name)
        stdlib_logger.handlers.clear()
        stdlib_logger.propagate = True
        stdlib_logger.setLevel(level)


def _reset_process_logging_for_tests() -> None:
    """Clear process logging state for isolated tests."""
    global _configured_signature
    with _CONFIGURE_LOCK:
        logger.remove()
        logger.configure(extra={})
        logging.getLogger().handlers.clear()
        logging.captureWarnings(False)
        _configured_signature = None
