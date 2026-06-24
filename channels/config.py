"""ChannelsSettings — unified module configuration accessors.

Module configuration is read from the merged ``settings.yaml`` via the core
``Settings`` singleton.  This module only keeps the channel-facing typed
properties so callers do not do string lookups directly.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from rpg_core.settings import TelegramBotSettings
from rpg_core.settings import settings as core_settings


class ChannelsSettings:
    """模块配置访问器。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = core_settings.module_settings

    def _modules(self) -> dict:
        return self._data if isinstance(self._data, dict) else {}

    def _mod_cfg(self, name: str) -> dict:
        mod = self._modules().get(name, {})
        return mod if isinstance(mod, dict) else {}

    def _bool(self, module: str, key: str, default: bool) -> bool:
        value = self._mod_cfg(module).get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        logger.warning(
            "channels config: invalid bool modules.{}.{}={!r}, fallback={}",
            module,
            key,
            value,
            default,
        )
        return default

    def _int(self, module: str, key: str, default: int) -> int:
        value = self._mod_cfg(module).get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning(
                "channels config: invalid int modules.{}.{}={!r}, fallback={}",
                module,
                key,
                value,
                default,
            )
            return default

    # ── 模块列表 ──────────────────────────────────────────────────────────

    @property
    def enabled_module_names(self) -> list[str]:
        """返回所有已启用的模块名列表。"""
        enabled = []
        if self.dashboard_api_enabled:
            enabled.append("dashboard_api")
        if self.telegram_enabled:
            enabled.append("telegram")
        if self.cli_enabled:
            enabled.append("cli")
        return enabled

    # ── Dashboard API 模块配置 ──────────────────────────────────────────

    @property
    def dashboard_api_enabled(self) -> bool:
        return self._bool("dashboard_api", "enabled", False)

    @property
    def dashboard_api_host(self) -> str:
        return str(self._mod_cfg("dashboard_api").get("host", "127.0.0.1"))

    @property
    def dashboard_api_port(self) -> int:
        return self._int("dashboard_api", "port", 8000)

    @property
    def dashboard_api_reload(self) -> bool:
        return self._bool("dashboard_api", "reload", False)

    # ── Telegram 模块配置 ────────────────────────────────────────────────

    @property
    def telegram_enabled(self) -> bool:
        return self._bool("telegram", "enabled", False) and any(
            bot.enabled for bot in self.telegram_bots
        )

    @property
    def telegram_bots(self) -> list[TelegramBotSettings]:
        return core_settings.telegram_bots

    # ── CLI 模块配置 ─────────────────────────────────────────────────────

    @property
    def cli_enabled(self) -> bool:
        return self._bool("cli", "enabled", False)

    @property
    def cli_workspace(self) -> str:
        """CLI 渠道绑定的 workspace 标识。

        若 ``settings.yaml`` 中未配置则返回渠道默认值
        ``"data/cli_default_workspace"``。
        """
        from rpg_core.utils.path_utils import default_workspace_name

        configured = str(self._mod_cfg("cli").get("workspace", ""))
        return configured if configured else default_workspace_name("cli")


settings = ChannelsSettings()
"""模块级单例，导入即可使用。"""
