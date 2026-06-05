"""PersistentMemoryStore — wraps persistent_memory.json for the Fixed Layer."""

from __future__ import annotations

import json
from pathlib import Path


class PersistentMemoryStore:
    """常驻记忆 —— 对应固定层的"常驻memory"模块。

    数据来自 sessions/{session_id}/persistent_memory.json，由 Dream 进程维护。
    以结构化 section 列表存储（{title, content}），通过 Jinja 模板渲染到上下文。
    """

    def __init__(self, file_path: Path) -> None:
        self._memory_file = file_path

    def get_content(self) -> str:
        """向后兼容：以纯文本形式返回全部内容。

        新代码应使用 :meth:`get_sections` 获取结构化数据。
        """
        try:
            return self._memory_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def get_sections(self) -> list[dict[str, str]]:
        """返回结构化 section 列表 ``[{title, content}, …]``。

        期望 JSON 格式为 ``[{"title": "…", "content": "…"}, …]``。
        文件不存在或 JSON 解析失败时报错并直接抛出异常。
        """
        try:
            raw = self._memory_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []

        data = json.loads(raw)
        if isinstance(data, list):
            return data
        # 兜底：整个文件当一段 content
        return [{"title": "", "content": str(data)}] if data else []
