"""SummaryStore — persist conversation summaries as a list of text entries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def _register_watcher(file_path: Path, callback: Callable[[], None]) -> None:
    """向 FileWatcher 注册单个文件的变更回调。

    轻量工具函数，不引入 BaseManager 的完整开销。
    在 watcher start 之前或之后都可以注册。
    """
    from rpg_core.utils.watcher import get_watcher

    get_watcher().register(file_path.resolve(), callback)


class SummaryStore:
    """摘要持久化存储。

    文件位置: sessions/{session_id}/rpg_summaries.json
    数据格式: ["summary text 1", "summary text 2", ...]

    注册 FileWatcher 监听文件变更，异步/离线归纳后自动同步。
    """

    def __init__(self, file_path: Path) -> None:
        self._file = file_path
        self._summaries: list[str] = self._load()
        if not self._file.exists():
            self._save()  # ensure file exists for FileWatcher
        _register_watcher(self._file, self.reload)

    # ── public API ────────────────────────────────────────

    def reload(self) -> None:
        """从磁盘重新加载，响应 FileWatcher 事件。"""
        self._summaries = self._load()

    # ── public API ────────────────────────────────────────

    def get_all_summaries(self) -> list[str]:
        """返回所有摘要文本列表。"""
        return list(self._summaries)

    def set_summary(self, text: str) -> None:
        """追加一条摘要文本。"""
        self._summaries.append(text)
        self._save()

    # ── I/O ───────────────────────────────────────────────

    def _load(self) -> list[str]:
        try:
            raw = self._file.read_text(encoding="utf-8")
            data = json.loads(raw)
            # New format: ["text1", "text2", ...]
            if isinstance(data, list):
                return [s for s in data if isinstance(s, str)]
            # Legacy format: {"summaries": [{"round_start": ..., "round_end": ..., "text": ...}]}
            if isinstance(data, dict):
                old = data.get("summaries", [])
                return [s["text"] for s in old if isinstance(s, dict) and "text" in s]
            return []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(self._summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
