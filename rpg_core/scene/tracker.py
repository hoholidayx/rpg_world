"""SceneTracker — active scene status table adapter.

通过 StatusManager 直接读写 rpg_data 当前 session 的 active scene 状态表，
自行渲染 ``[scene]...[/scene]`` 注入到用户消息的 user_before 位置，不走通用
status_tables.jinja。

MemorySubAgent 过滤 system 角色消息，场景信息必须在 user 消息中才能被
总结归纳可见。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from rpg_core.status.manager import StatusManager


class SceneTracker:
    """场景状态管理器，所有状态读写都直接委托给 rpg_data。"""

    TIME_ATTR = "时间"
    LOCATION_ATTR = "位置"
    PRESENT_CHARACTERS_ATTR = "在场人物"
    TIME_STATE_FIELDS = ("year", "month", "day", "hour", "minute")
    DEFAULT_ATTRS: dict[str, str] = {
        TIME_ATTR: "第 1 年 1 月 1 日 6 时",
        LOCATION_ATTR: "",
        PRESENT_CHARACTERS_ATTR: "",
    }
    MAX_ATTRS = 8
    """场景属性总数上限（含默认属性），超出后 set_attr 返回错误。"""
    RUNTIME_GUIDANCE = (
        "（scene 数据可能不准确，需根据上下文内容裁定是否使用工具更新，"
        "需遵循核心状态同步协议。）"
    )

    def __init__(self, *, allow_runtime_key_changes: bool = False) -> None:
        self._allow_runtime_key_changes = allow_runtime_key_changes

        # 结构化时间字段
        self._year: int = 1
        self._month: int = 1
        self._day: int = 1
        self._hour: int = 6
        self._minute: int = 0

        # StatusManager 引用（None = 不持久化）
        self._status_mgr: StatusManager | None = None
        self._scene_table_id: int | None = None
        self._table_key: tuple[str, str] | None = None

    # ── 常量访问 ─────────────────────────────────────────────────────

    @property
    def table_key(self) -> tuple[str, str] | None:
        """供 builder 排除通用状态表时使用，避免硬编码。"""
        return self._table_key

    @property
    def allow_runtime_key_changes(self) -> bool:
        """Whether LLM scene tools may add or delete keys."""
        return self._allow_runtime_key_changes

    @property
    def attr_keys(self) -> tuple[str, ...]:
        """Current scene keys in document order for tool schema allowlists."""
        return tuple(self._current_attrs())

    # ── 持久化绑定 ──────────────────────────────────────────────────

    def bind_status_manager(self, mgr: StatusManager | None) -> None:
        """绑定 StatusManager 引用，用于读写 active scene 状态表。"""
        self._status_mgr = mgr

    def load_from_status_table(self) -> bool:
        """绑定 active scene 表引用；不缓存表内容。"""
        if self._status_mgr is None:
            return False

        mgr = self._status_mgr
        scene_ref = mgr.get_active_scene_table_ref()
        if scene_ref is None:
            self._scene_table_id = None
            self._table_key = None
            return False

        self._scene_table_id, self._table_key = scene_ref
        return True

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

    def get_time_state(self) -> dict[str, int]:
        """Return the structured scene time fields for scratch tracker cloning."""
        return {
            "year": self._year,
            "month": self._month,
            "day": self._day,
            "hour": self._hour,
            "minute": self._minute,
        }

    def set_time_state(self, state: Mapping[str, int]) -> None:
        """Restore structured scene time fields from another tracker."""
        for field in self.TIME_STATE_FIELDS:
            if field in state:
                setattr(self, f"_{field}", int(state[field]))

    def set_time(self, **kwargs: int) -> dict[str, str]:
        """直接设置绝对时间值（非增量推进）。

        支持 year/month/day/hour/minute 字段，hour 使用 24h 制。
        例::

            tracker.set_time(year=3, month=6, day=15, hour=14, minute=30)
            # → 时间变为 "第 3 年 6 月 15 日 14 时 30 分"

        其余关键字参数直接写入状态表（不参与 _format_time）。
        """
        pending_attrs: dict[str, str] = {}
        next_time_state = self.get_time_state()
        for k, v in kwargs.items():
            if k in self.TIME_STATE_FIELDS:
                next_time_state[k] = v
            else:
                pending_attrs[k] = str(v)

        if (
            not self._allow_runtime_key_changes
            and self._status_mgr is not None
            and self._scene_table_id is not None
        ):
            existing_keys = set(self._current_attrs())
            missing_keys = {
                self.TIME_ATTR,
                *pending_attrs,
            } - existing_keys
            if missing_keys:
                raise PermissionError(
                    "LLM 只能修改场景中已有字段的值，不能新增字段："
                    + "、".join(sorted(missing_keys))
                )

        self.set_time_state(next_time_state)

        attrs = self._runtime_set_attr(self.TIME_ATTR, self._format_time())
        for key, value in pending_attrs.items():
            attrs = self._runtime_set_attr(key, value)
        return attrs

    @property
    def attr_count(self) -> int:
        return len(self._current_attrs())

    # ── 场景属性操作 ────────────────────────────────────────────────

    def set_attr(self, key: str, value: str) -> dict[str, str]:
        """创建或更新场景属性。

        超出 ``MAX_ATTRS`` 上限时抛 ``ValueError``。
        """
        attrs = self._current_attrs()
        if not self._allow_runtime_key_changes and key not in attrs:
            raise PermissionError(
                f"LLM 只能修改场景中已有字段的值，不能新增字段：{key}"
            )
        if key not in attrs and len(attrs) >= self.MAX_ATTRS:
            raise ValueError(
                f"场景属性已达上限（{self.MAX_ATTRS} 个），"
                f"请先删除不再需要的属性再新增"
            )
        return self._runtime_set_attr(key, value)

    def delete_attr(self, key: str) -> dict[str, str]:
        """删除场景属性；失败时返回 rpg_data 当前状态。"""
        if not self._allow_runtime_key_changes:
            raise PermissionError("LLM 不允许删除或重命名场景字段")
        if self._status_mgr is not None and self._scene_table_id is not None:
            try:
                table = self._status_mgr.runtime_delete_key_value(self._scene_table_id, key)
                return self._attrs_from_table(table)
            except (FileNotFoundError, PermissionError):
                return self._current_attrs()
        return self._current_attrs()

    # ── 上下文渲染 ──────────────────────────────────────────────────

    def get_context(self) -> str:
        """渲染供 LLM 使用的 ``[scene]...[/scene]``。

        运行时提示只存在于本轮 LLM Context；持久化历史应使用
        :meth:`get_snapshot_context`，避免把提示词写入消息正文。
        """
        lines = self._snapshot_lines()
        lines.extend(("", self.RUNTIME_GUIDANCE, "[/scene]"))
        return "\n".join(lines)

    def get_snapshot_context(self) -> str:
        """渲染只包含场景数据的快照，供持久化历史使用。"""
        return "\n".join((*self._snapshot_lines(), "[/scene]"))

    def _snapshot_lines(self) -> list[str]:
        lines = ["[scene]"]
        for k, v in self._current_attrs().items():
            if v:
                lines.append(f"{k}: {v}")
            else:
                lines.append(f"{k}: ")
        return lines

    def _runtime_set_attr(self, key: str, value: str) -> dict[str, str]:
        if self._status_mgr is None or self._scene_table_id is None:
            return self._current_attrs()
        table = self._status_mgr.runtime_set_key_value(self._scene_table_id, key, value)
        return self._attrs_from_table(table)

    def _current_attrs(self) -> dict[str, str]:
        if self._status_mgr is None:
            return {}
        return dict(self._status_mgr.get_scene_attrs() or {})

    def _attrs_from_table(self, table: dict[str, object]) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for row in table.get("rows", []):
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                attrs[str(row[0])] = str(row[1])
        return attrs

    # ── 工具注册 ────────────────────────────────────────────────────

    def get_tools(self) -> list:
        """Return only the scene tools allowed by the current document/policy."""
        from rpg_core.scene.tools import (
            DeleteAttrTool,
            SetAttrTool,
            SetTimeTool,
        )

        if self._allow_runtime_key_changes:
            return [
                SetTimeTool(self),
                SetAttrTool(self),
                DeleteAttrTool(self),
            ]

        attrs = self._current_attrs()
        tools = []
        if self.TIME_ATTR in attrs:
            tools.append(SetTimeTool(self))
        if attrs:
            tools.append(SetAttrTool(self))
        return tools
