"""StoryMemoryStore — persistent small story details for the Dynamic Layer.

Lifecycle:
  1. Agent records small story beats (e.g. "颜沁记住了沈听洲唱歌很好")
  2. These appear in the context between milestones and status tables
  3. During offline PM/summary distillation, they're refined into Persistent Memory
  4. Story memory is cleared to make room for new details
"""

from __future__ import annotations

import json
from pathlib import Path


def _register_watcher(file_path: Path, callback) -> None:
    """向 FileWatcher 注册单个文件的变更回调。

    轻量工具函数，不引入 BaseManager 的完整开销。
    在 watcher start 之前或之后都可以注册。
    """
    from rpg_world.rpg_core.utils.watcher import get_watcher

    get_watcher().register(file_path.resolve(), callback)


class StoryMemoryStore:
    """剧情记忆 —— 对应动态层中"剧情记忆"模块。

    构造时传入完整文件路径（见 :func:`Settings.workspace_root`），
    内容为剧情推进中产生的需要记住的小细节，
    总量可控，定期提炼到常驻记忆后清空。

    通过 FileWatcher 监听文件变更，外部修改后自动 reload。
    """

    def __init__(self, file_path: Path) -> None:
        self._file = file_path
        self._details: list[dict[str, object]] = self._load()
        if not self._file.exists():
            self._save()  # ensure file exists for FileWatcher
        _register_watcher(self._file, self.reload)

    # ── public API ────────────────────────────────────────

    def reload(self) -> None:
        """从磁盘重新加载，响应 FileWatcher 事件。"""
        self._details = self._load()

    # ── public API ────────────────────────────────────────

    def get_all(self) -> list[dict[str, object]]:
        """返回所有剧情记忆条目。"""
        return list(self._details)

    def add_detail(self, text: str, metadata: dict[str, object] | None = None) -> None:
        """追加一条剧情细节。"""
        self._details.append({
            "text": text,
            "metadata": metadata or {},
        })
        self._save()

    def set_details(self, details: list[dict[str, object]]) -> None:
        """批量设置剧情记忆（替换全部）。"""
        self._details = list(details)
        self._save()

    def clear(self) -> None:
        """清空全部剧情记忆（提炼到常驻记忆后调用）。"""
        self._details.clear()
        self._save()

    # ── I/O ───────────────────────────────────────────────

    def _load(self) -> list[dict[str, object]]:
        try:
            raw = self._file.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(self._details, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
