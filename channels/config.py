"""ChannelsSettings — 渠道独立配置加载器。

与 ``rpg_world/settings.json``（agent 配置/工作区/数据路径）分离，
``channels.json`` 统一存放各模块（api / telegram / cli 等）的开关和参数。
"""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "channels.json"


class ChannelsSettings:
    """模块配置加载器。

    读取 ``channels.json`` 的 ``modules.{name}`` 结构，提供以下能力：
    - ``is_module_enabled(name)`` — 判断模块是否启用
    - ``get_module_config(name)`` — 获取模块的完整配置 dict
    - 向下兼容：仍可通过 ``is_enabled(name)`` 直接读取顶层 key（旧格式）

    文件不存在或格式异常时返回空配置，不抛异常。
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
        """获取 ``modules`` 段（不存在时返回空 dict）。"""
        raw = self._data.get("modules", {})
        return raw if isinstance(raw, dict) else {}

    # ── 新格式：modules.{name}.enabled ──────────────────────────────────

    def is_module_enabled(self, name: str) -> bool:
        """指定模块是否启用（从 ``modules.{name}.enabled`` 读取）。"""
        mod = self._modules().get(name, {})
        return bool(mod.get("enabled", False) if isinstance(mod, dict) else False)

    def get_module_config(self, name: str) -> dict:
        """获取指定模块的完整配置 dict。"""
        mod = self._modules().get(name, {})
        return mod if isinstance(mod, dict) else {}

    # ── 旧格式兼容：直接读取顶层 key ──────────────────────────────────

    def is_enabled(self, name: str) -> bool:
        """旧格式兼容：从顶层 ``{name}.enabled`` 读取。"""
        val = self._data.get(name, {})
        return bool(val.get("enabled", False) if isinstance(val, dict) else False)

    def get_channel_config(self, name: str) -> dict:
        """旧格式兼容：从顶层 ``{name}`` 读取。"""
        val = self._data.get(name, {})
        return val if isinstance(val, dict) else {}

    def get(self, name: str, key: str, default: object = None) -> object:
        """旧格式兼容：从顶层 ``{name}.{key}`` 读取。"""
        val = self._data.get(name, {})
        return val.get(key, default) if isinstance(val, dict) else default


settings = ChannelsSettings()
"""模块级单例，导入即可使用。"""
