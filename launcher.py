"""Process launcher helpers for rpg_world supervisor entrypoints."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from loguru import logger

from rpg_world.channels.config import settings as channels_settings


@dataclass(frozen=True)
class ProcessSpec:
    """Specification for a subprocess managed by the supervisor."""

    name: str
    argv: tuple[str, ...]


def resolve_modules(args: argparse.Namespace) -> list[str]:
    """Resolve enabled modules from CLI args, env, and settings."""
    modules_str = args.modules or os.environ.get("MODULES", "")
    if modules_str:
        return [module.strip() for module in modules_str.split(",") if module.strip()]
    return channels_settings.enabled_module_names


def python_module_command(module: str, *args: str) -> tuple[str, ...]:
    """Build a ``python -m`` command tuple."""
    return (sys.executable, "-m", module, *args)


def build_process_spec(module: str) -> ProcessSpec | None:
    """Build the subprocess launch spec for a logical module name."""
    if module == "api":
        if channels_settings.api_reload:
            raise ValueError(
                "supervisor 模式不支持 modules.api.reload=true；"
                "请改用直接 uvicorn 调试命令启动 API。",
            )
        return ProcessSpec(
            name="api",
            argv=python_module_command(
                "uvicorn",
                "rpg_world.api.main:app",
                "--host",
                channels_settings.api_host,
                "--port",
                str(channels_settings.api_port),
                "--log-level",
                "info",
            ),
        )

    if module == "telegram":
        enabled_bots = [bot for bot in channels_settings.telegram_bots if bot.enabled]
        if not enabled_bots:
            logger.warning("Telegram 模块已请求启动，但没有 enabled=true 的 bot")
            return None
        return ProcessSpec(
            name="telegram",
            argv=python_module_command("rpg_world.channels.telegram.runner"),
        )

    if module == "cli":
        if not channels_settings.cli_enabled:
            logger.warning("CLI 模块已请求启动，但 settings.yaml 中未启用")
            return None
        return ProcessSpec(
            name="cli",
            argv=python_module_command("rpg_world.channels.cli.repl"),
        )

    logger.warning("未知模块，跳过: {}", module)
    return None
