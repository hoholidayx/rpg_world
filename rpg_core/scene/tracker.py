"""SceneTracker — 纯内存场景状态管理器。

维护当前场景的时间、地点、人物等上下文，通过 StatusManager 持久化到
rpg_data 当前 session 的 active scene 状态表，自行渲染 ``[scene]...[/scene]``
注入到用户消息的 user_before 位置，不走通用 status_tables.jinja。

MemorySubAgent 过滤 system 角色消息，场景信息必须在 user 消息中才能被
总结归纳可见。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_core.status.manager import StatusManager


class SceneTracker:
    """场景状态管理器——维护当前场景的时间、空间、人物等上下文。

    常量：
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

    TIME_ATTR = "时间"
    LOCATION_ATTR = "位置"
    PRESENT_CHARACTERS_ATTR = "在场人物"
    DEFAULT_ATTRS: dict[str, str] = {
        TIME_ATTR: "第 1 年 1 月 1 日 6 时",
        LOCATION_ATTR: "",
        PRESENT_CHARACTERS_ATTR: "",
    }
    MAX_ATTRS = 8
    """场景属性总数上限（含默认属性），超出后 set_attr 返回错误。"""

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
        self._status_mgr: StatusManager | None = None
        self._scene_table_id: int | None = None
        self._table_key: tuple[str, str] | None = None

    # ── 常量访问 ─────────────────────────────────────────────────────

    @property
    def table_key(self) -> tuple[str, str] | None:
        """供 builder 排除通用状态表时使用，避免硬编码。"""
        return self._table_key

    # ── 持久化绑定 ──────────────────────────────────────────────────

    def bind_status_manager(self, mgr: StatusManager | None) -> None:
        """绑定 StatusManager 引用，用于读写 active scene 状态表。"""
        self._status_mgr = mgr

    def load_from_status_table(self) -> bool:
        """从 active scene 表恢复场景属性。

        表未挂载时返回 ``False``，不自动创建。
        结构化时间字段从默认值开始（历史消息中的 ``[scene]`` 标签
        已包含时间变化轨迹，供 LLM 参考）。
        """
        if self._status_mgr is None:
            return False

        mgr = self._status_mgr
        scene_ref = mgr.get_active_scene_table_ref()
        if scene_ref is None:
            self._scene_table_id = None
            self._table_key = None
            return False

        self._scene_table_id, self._table_key = scene_ref
        attrs = mgr.get_scene_attrs() or {}
        if attrs:
            self._attrs = dict(self.DEFAULT_ATTRS)
            self._attrs.update({str(key): str(value) for key, value in attrs.items()})
            return True

        # 已挂载但内容为空 → 只初始化现有 active scene 表
        self._save_to_status_table()
        return False

    def _save_to_status_table(self) -> None:
        """将 ``_attrs`` 写入已挂载 active scene 表。"""
        if self._status_mgr is None or self._scene_table_id is None:
            return

        for key, value in self._attrs.items():
            self._persist_attr(key, value)

    def _persist_attr(self, key: str, value: str) -> None:
        if self._status_mgr is None or self._scene_table_id is None:
            return
        self._status_mgr.set_key_value(self._scene_table_id, key, value)

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

        self._attrs[self.TIME_ATTR] = self._format_time()
        self._persist_attr(self.TIME_ATTR, self._attrs[self.TIME_ATTR])
        return dict(self._attrs)

    @property
    def protected_attrs(self) -> set[str]:
        """不可被删除的默认属性 key 集合。"""
        return set(self.DEFAULT_ATTRS.keys())

    @property
    def attr_count(self) -> int:
        return len(self._attrs)

    # ── 场景属性操作 ────────────────────────────────────────────────

    def set_attr(self, key: str, value: str) -> dict[str, str]:
        """创建或更新场景属性。

        超出 ``MAX_ATTRS`` 上限时抛 ``ValueError``。
        """
        if key not in self._attrs and len(self._attrs) >= self.MAX_ATTRS:
            raise ValueError(
                f"场景属性已达上限（{self.MAX_ATTRS} 个），"
                f"请先删除不再需要的属性再新增"
            )
        self._attrs[key] = value
        self._persist_attr(key, value)
        return dict(self._attrs)

    def delete_attr(self, key: str) -> dict[str, str]:
        """删除场景属性。默认属性（如时间、位置）不可删除，静默忽略。"""
        if key in self.protected_attrs:
            return dict(self._attrs)
        self._attrs.pop(key, None)
        if self._status_mgr is not None and self._scene_table_id is not None:
            try:
                self._status_mgr.delete_key_value(self._scene_table_id, key)
            except FileNotFoundError:
                pass
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
        lines.append("（场景状态已由 StatusSubAgent 自动预处理。需要手动调整时可使用 scene_time / scene_attr / scene_del_attr 工具。注意及时清理已过期的属性，避免堆积。）")
        lines.append("[/scene]")
        return "\n".join(lines)

    # ── 工具注册 ────────────────────────────────────────────────────

    def get_tools(self) -> list:
        """返回绑定了此实例的 LLM 工具列表。"""
        from rpg_core.scene.tools import (
            DeleteAttrTool,
            SetAttrTool,
            SetTimeTool,
        )

        return [
            SetTimeTool(self),
            SetAttrTool(self),
            DeleteAttrTool(self),
        ]
