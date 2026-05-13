"""PersistentMemoryStore — wraps MEMORY.md for the Fixed Layer's "常驻memory" module."""

from __future__ import annotations

from pathlib import Path


class PersistentMemoryStore:
    """常驻记忆 —— 对应固定层的"常驻memory"模块。

    数据来自 MEMORY.md 文件，由 Dream 进程维护。
    在 Builder 中只读读取，内容直接传入 Jinja 模板。
    """

    def __init__(self, file_path: Path) -> None:
        self._memory_file = file_path

    def get_content(self) -> str:
        """读取 MEMORY.md 全部内容（Markdown 字符串）。

        返回空字符串表示无常驻记忆。
        """
        try:
            return self._memory_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
