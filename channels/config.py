"""ChannelsSettings — 渠道独立配置加载器。

与 ``rpg_world/settings.json``（agent 配置/工作区/数据路径）分离，
``channels.json`` 专门存放各渠道的 token、开关、策略等。
"""

from __future__ import annotations

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "channels.json"


class ChannelsSettings:
    """渠道配置加载器。

    读取 ``channels.json``，提供按渠道名称查询配置的方法。
    文件不存在或格式异常时返回空配置，不抛异常。
    """

    def __init__(self) -> None:
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not _CONFIG_PATH.exists():
            return {}
        try:
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            return {k: v for k, v in raw.items() if isinstance(v, dict)}
        except (json.JSONDecodeError, OSError):
            return {}

    def is_enabled(self, name: str) -> bool:
        """指定渠道是否已启用。"""
        return bool(self._data.get(name, {}).get("enabled", False))

    def get_channel_config(self, name: str) -> dict:
        """获取指定渠道的完整配置 dict。"""
        return self._data.get(name, {}) or {}

    def get(self, name: str, key: str, default: object = None) -> object:
        """获取指定渠道的某个配置项。"""
        return self._data.get(name, {}).get(key, default)


settings = ChannelsSettings()
"""模块级单例，导入即可使用。"""
