"""RecalledMemoryStore — in-memory buffer for externally-injected recalled context.

External modules (RAG, vector search, etc.) call ``inject()`` or ``set_items()``
before ``RPGContextBuilder.build()`` is invoked.  Content is ephemeral —
not persisted to disk — because recalled context is recomputed per request.
"""

from __future__ import annotations


class RecalledMemoryStore:
    """召回记忆 —— 外部模块动态注入的临时上下文。

    无持久化，每次 ``build()`` 前由外部模块写入。
    """

    def __init__(self) -> None:
        self._items: list[str] = []

    # ── public API ────────────────────────────────────────

    def get_items(self) -> list[str]:
        """返回当前会话的召回记忆条目列表。"""
        return list(self._items)

    def inject(self, item: str) -> None:
        """追加一条召回记忆。"""
        self._items.append(item)

    def set_items(self, items: list[str]) -> None:
        """批量设置召回记忆（替换全部）。由外部模块在 build() 前调用。"""
        self._items = list(items)

    def clear(self) -> None:
        """清空全部召回记忆。"""
        self._items.clear()
