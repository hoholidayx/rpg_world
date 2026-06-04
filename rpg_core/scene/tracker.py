"""SceneTracker — 纯内存场景状态管理器。

维护当前场景的时间、地点、人物等上下文，通过 StatusManager 持久化到
``status/全局状态/当前场景.csv``，自行渲染 ``[scene]...[/scene]`` 注入到
用户消息的 user_before 位置，不走通用 status_tables.jinja。

MemorySubAgent 过滤 system 角色消息，场景信息必须在 user 消息中才能被
总结归纳可见。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SceneTracker:
    """场景状态管理器——维护当前场景的时间、空间、人物等上下文。

    常量：
        TABLE_TYPE: 状态类型目录名。
        TABLE_NAME: 状态表文件名（不含 .csv）。
        DEFAULT_ATTRS: 首次初始化时的默认属性行。

    用法::

        tracker = SceneTracker()
        tracker.bind_status_manager(status_mgr)
        tracker.load_from_status_table()

        tracker.set_time(year=3, month=6, day=15, hour=14)
        tracker.set_attr("位置", "城堡")
        tracker.delete_attr("天气")

        context = tracker.get_context()
        # → "[scene]\\n时间: ...\\n位置: 城堡\\n[/scene]"
    """

    TABLE_TYPE = "全局状态"
    TABLE_NAME = "当前场景"
    DEFAULT_ATTRS: dict[str, str] = {
        "时间": "第 1 年 1 月 1 日 6 时",
        "位置": "",
    }

    def __init__(self) -> None:
        # 结构化时间字段
        self._year: int = 1
        self._month: int = 1
        self._day: int = 1
        self._hour: int = 6
        self._minute: int = 0

        # 场景属性（key-value，与状态表行对应）
        self._attrs: dict[str, str] = dict(self.DEFAULT_ATTRS)

        # StatusManager 引用（None = 不持久化）
        self._status_mgr: Any = None

    # ── 常量访问 ─────────────────────────────────────────────────────

    @property
    def table_key(self) -> tuple[str, str]:
        """供 builder 排除通用状态表时使用，避免硬编码。"""
        return (self.TABLE_TYPE, self.TABLE_NAME)

    # ── 持久化绑定 ──────────────────────────────────────────────────

    def bind_status_manager(self, mgr: Any) -> None:
        """绑定 StatusManager 引用，用于读写 ``当前场景`` 状态表。"""
        self._status_mgr = mgr

    def load_from_status_table(self) -> bool:
        """从 ``全局状态/当前场景`` 表恢复场景属性。

        表不存在时用 ``DEFAULT_ATTRS`` 创建并写入。
        结构化时间字段从默认值开始（历史消息中的 ``[scene]`` 标签
        已包含时间变化轨迹，供 LLM 参考）。
        """
        if self._status_mgr is None:
            return False

        mgr = self._status_mgr
        try:
            tables = mgr.list_tables(self.TABLE_TYPE)
        except Exception:
            tables = []

        if self.TABLE_NAME in tables:
            try:
                tbl = mgr.get_table(self.TABLE_TYPE, self.TABLE_NAME)
                for row in tbl.get("rows", []):
                    if len(row) >= 2:
                        self._attrs[row[0]] = row[1]
                return True
            except Exception:
                pass

        # 表不存在 → 创建
        self._save_to_status_table()
        return False

    def _save_to_status_table(self) -> None:
        """将 ``_attrs`` 全量写入 ``全局状态/当前场景`` 表。"""
        if self._status_mgr is None:
            return

        mgr = self._status_mgr
        headers = ["属性", "值"]
        rows = [[k, v] for k, v in self._attrs.items()]

        try:
            mgr.create_table(self.TABLE_TYPE, self.TABLE_NAME, headers, rows)
        except ValueError:
            # 表已存在 → save
            mgr.save_table(self.TABLE_TYPE, self.TABLE_NAME, headers, rows)
        except FileNotFoundError:
            # 类型目录不存在 → 先创建类型再 save
            try:
                mgr.create_type(self.TABLE_TYPE)
            except ValueError:
                pass
            try:
                mgr.create_table(self.TABLE_TYPE, self.TABLE_NAME, headers, rows)
            except ValueError:
                mgr.save_table(self.TABLE_TYPE, self.TABLE_NAME, headers, rows)

    # ── 时间操作 ─────────────────────────────────────────────────────

    def _format_time(self) -> str:
        """结构化时间 → 显示字符串（24h 制）。"""
        parts = []
        if self._year:
            parts.append(f"第 {self._year} 年")
        if self._month:
            parts.append(f"{self._month} 月")
        if self._day:
            parts.append(f"{self._day} 日")
        if self._hour is not None:
            parts.append(f"{self._hour} 时")
        if self._minute:
            parts.append(f"{self._minute} 分")
        return " ".join(parts)

    def set_time(self, **kwargs: int) -> dict[str, str]:
        """直接设置绝对时间值（非增量推进）。

        支持 year/month/day/hour/minute 字段，hour 使用 24h 制。
        例::

            tracker.set_time(year=3, month=6, day=15, hour=14, minute=30)
            # → 时间变为 "第 3 年 6 月 15 日 14 时 30 分"

        其余关键字参数直接写入 ``_attrs``（不参与 _format_time）。
        """
        STRUCT_FIELDS = {"year", "month", "day", "hour", "minute"}
        for k, v in kwargs.items():
            if k in STRUCT_FIELDS:
                setattr(self, f"_{k}", v)
            else:
                self._attrs[k] = str(v)

        self._attrs["时间"] = self._format_time()
        self._save_to_status_table()
        return dict(self._attrs)

    # ── 场景属性操作 ────────────────────────────────────────────────

    def set_attr(self, key: str, value: str) -> dict[str, str]:
        """创建或更新场景属性。"""
        self._attrs[key] = value
        self._save_to_status_table()
        return dict(self._attrs)

    def delete_attr(self, key: str) -> dict[str, str]:
        """删除场景属性。key 不存在时静默忽略。"""
        self._attrs.pop(key, None)
        self._save_to_status_table()
        return dict(self._attrs)

    # ── 上下文渲染 ──────────────────────────────────────────────────

    def get_context(self) -> str:
        """渲染 ``[scene]...[/scene]``，用于注入到用户消息 user_before。

        末尾附带简短引导提示，指引 LLM 使用场景工具更新数据。
        """
        lines = ["[scene]"]
        for k, v in self._attrs.items():
            if v:
                lines.append(f"{k}: {v}")
            else:
                lines.append(f"{k}: ")
        lines.append("")
        lines.append("（场景状态已由 StatusSubAgent 自动预处理。如需手动修正，可使用 set_time / set_attr / delete_attr 工具）")
        lines.append("[/scene]")
        return "\n".join(lines)

    # ── 工具注册 ────────────────────────────────────────────────────

    def get_tools(self) -> list:
        """返回绑定了此实例的 LLM 工具列表。"""
        from rpg_world.rpg_core.scene.tools import (
            DeleteAttrTool,
            SetAttrTool,
            SetTimeTool,
        )

        return [
            SetTimeTool(self),
            SetAttrTool(self),
            DeleteAttrTool(self),
        ]
