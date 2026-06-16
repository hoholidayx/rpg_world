"""ChannelsSettings — 渠道独立配置加载器。

与 ``rpg_world/settings.json``（agent 配置/工作区/数据路径）分离，
``channels.json`` 统一存放各模块（api / telegram / cli 等）的开关和参数。

所有模块名和配置字段名封装为属性，外部调用不做字符串拼接。
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "channels.json"


class ChannelsSettings:
    """模块配置加载器。

    读取 ``channels.json`` 的 ``modules.{name}`` 结构，提供类型化属性。
    文件不存在或格式异常时返回空配置/默认值，不抛异常。
    """

    def __init__(self) -> None:
        self._data: dict = self._load()

    def _load(self) -> dict:
        if not _CONFIG_PATH.exists():
            return {}
        try:
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            return raw
        except (json.JSONDecodeError, OSError):
            return {}

    def _modules(self) -> dict:
        raw = self._data.get("modules", {})
        return raw if isinstance(raw, dict) else {}

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
        return [
            name for name in ("api", "telegram", "cli")
            if self._bool(name, "enabled", False)
        ]

    # ── API 模块配置 ─────────────────────────────────────────────────────

    @property
    def api_enabled(self) -> bool:
        return self._bool("api", "enabled", False)

    @property
    def api_host(self) -> str:
        return str(self._mod_cfg("api").get("host", "127.0.0.1"))

    @property
    def api_port(self) -> int:
        return self._int("api", "port", 8000)

    @property
    def api_reload(self) -> bool:
        return self._bool("api", "reload", False)

    # ── Telegram 模块配置 ────────────────────────────────────────────────

    @property
    def telegram_enabled(self) -> bool:
        return self._bool("telegram", "enabled", False)

    @property
    def telegram_token(self) -> str:
        return str(self._mod_cfg("telegram").get("bot_token", ""))

    @property
    def telegram_streaming(self) -> bool:
        return self._bool("telegram", "streaming", True)

    @property
    def telegram_proxy(self) -> str:
        """Telegram 请求代理地址。

        为空字符串或未配置时表示不启用代理。
        """
        return str(self._mod_cfg("telegram").get("proxy", ""))

    @property
    def telegram_stream_edit_interval_ms(self) -> int:
        """Telegram 流式编辑的最小间隔，单位毫秒。"""
        return self._int("telegram", "stream_edit_interval_ms", 800)

    @property
    def telegram_stream_edit_min_chars(self) -> int:
        """Telegram 流式编辑的最小增量字符数。"""
        return self._int("telegram", "stream_edit_min_chars", 24)

    @property
    def telegram_request_timeout_ms(self) -> int:
        """Telegram 单次请求超时，单位毫秒。"""
        return self._int("telegram", "request_timeout_ms", 5000)

    @property
    def telegram_workspace(self) -> str:
        """Telegram 渠道绑定的 workspace 标识。

        若 ``channels.json`` 中未配置则返回渠道默认值
        ``"data/telegram_default_workspace"``。
        """
        from rpg_world.rpg_core.utils.path_utils import default_workspace_name

        configured = str(self._mod_cfg("telegram").get("workspace", ""))
        return configured if configured else default_workspace_name("telegram")

    # ── CLI 模块配置 ─────────────────────────────────────────────────────

    @property
    def cli_enabled(self) -> bool:
        return self._bool("cli", "enabled", False)

    @property
    def cli_workspace(self) -> str:
        """CLI 渠道绑定的 workspace 标识。

        若 ``channels.json`` 中未配置则返回渠道默认值
        ``"data/cli_default_workspace"``。
        """
        from rpg_world.rpg_core.utils.path_utils import default_workspace_name

        configured = str(self._mod_cfg("cli").get("workspace", ""))
        return configured if configured else default_workspace_name("cli")

    # ── 旧格式兼容（废弃，暂保留） ─────────────────────────────────────

    def get_channel_config(self, name: str) -> dict:
        val = self._data.get(name, {})
        return val if isinstance(val, dict) else {}


settings = ChannelsSettings()
"""模块级单例，导入即可使用。"""
