"""DeltaMemoryStore — session-scoped working memory for the Dynamic Layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DeltaMemoryStore:
    """会话级实时记忆 —— 对应动态层的"实时memory"模块。

    文件位置: data/delta_memory/{session_id}.json
    内容为纯文本（Markdown 格式），最终渲染到动态层 system 消息中。
    """

    def __init__(self, data_path: Path, session_id: str = "default") -> None:
        self._file = data_path / f"{session_id}.json"
        self._data: list[str] = self._load()

    # ── public API ────────────────────────────────────────

    def get_content(self) -> str:
        """返回当前会话的实时记忆内容（Markdown 字符串）。

        内容将直接传入 Jinja 模板的 realtime_memory 模块。
        返回空字符串表示无实时记忆。
        """
        if not self._data:
            return ""
        return "\n".join(f"- {item}" for item in self._data)

    def append(self, text: str) -> None:
        """追加一条实时记忆记录。"""
        self._data.append(text)
        self._save()

    def clear(self) -> None:
        """清空当前会话的实时记忆。"""
        self._data.clear()
        self._save()

    # ── I/O ───────────────────────────────────────────────

    def _load(self) -> list[str]:
        try:
            raw = self._file.read_text(encoding="utf-8")
            data: list[str] = json.loads(raw)
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
