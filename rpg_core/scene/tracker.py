"""SceneTracker — active scene status table adapter.

通过 StatusManager 直接读写 rpg_data 当前 session 的 active scene 状态表，
自行渲染 ``[scene]...[/scene]`` 注入到用户消息的 user_before 位置，不走通用
status_tables.jinja。

MemorySubAgent 过滤 system 角色消息，场景信息必须在 user 消息中才能被
总结归纳可见。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from commons.scene_time import SceneTime
from rpg_core.scene.status import (
    SCENE_LOCATION_ATTR,
    SCENE_PRESENT_CHARACTERS_ATTR,
    SCENE_TIME_ATTR,
)

if TYPE_CHECKING:
    from rpg_core.status.manager import StatusManager


class SceneTracker:
    """场景状态管理器，所有状态读写都直接委托给 rpg_data。"""

    TIME_ATTR = SCENE_TIME_ATTR
    LOCATION_ATTR = SCENE_LOCATION_ATTR
    PRESENT_CHARACTERS_ATTR = SCENE_PRESENT_CHARACTERS_ATTR
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

        self._scene_time: SceneTime | None = SceneTime(1, 1, 1, 6)
        self._scene_time_error = ""

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
            self._scene_table_id = None
            self._table_key = None
            self._scene_time = None
            self._scene_time_error = "当前 Session 没有 Scene 状态表"
            return False

        mgr = self._status_mgr
        scene_ref = mgr.get_active_scene_table_ref()
        if scene_ref is None:
            self._scene_table_id = None
            self._table_key = None
            self._scene_time = None
            self._scene_time_error = "当前 Session 没有 Scene 状态表"
            return False

        self._scene_table_id, self._table_key = scene_ref
        raw_time = self._current_attrs().get(self.TIME_ATTR, "").strip()
        if not raw_time:
            self._scene_time = None
            self._scene_time_error = "当前场景缺少非空“时间”字段"
        else:
            try:
                self._scene_time = SceneTime.parse(raw_time)
                self._scene_time_error = ""
            except ValueError as exc:
                self._scene_time = None
                self._scene_time_error = str(exc)
        return True

    # ── 时间操作 ─────────────────────────────────────────────────────

    def _format_time(self) -> str:
        """结构化时间 → 显示字符串（24h 制）。"""
        if self._scene_time is None:
            return ""
        return self._scene_time.format()

    def get_time_state(self) -> dict[str, int] | None:
        """Return the structured scene time fields for scratch tracker cloning."""
        return self._scene_time.to_dict() if self._scene_time is not None else None

    def set_time_state(self, state: Mapping[str, int] | SceneTime | None) -> None:
        """Restore structured scene time fields from another tracker."""
        if state is None:
            self._scene_time = None
            self._scene_time_error = "Scene 时间不可用"
            return
        self._scene_time = state if isinstance(state, SceneTime) else SceneTime.from_mapping(state)
        self._scene_time_error = ""

    def get_scene_time(self) -> SceneTime | None:
        """Return the parsed scene time, or ``None`` when persisted data is invalid."""
        return self._scene_time

    @property
    def scene_time_error(self) -> str:
        return self._scene_time_error

    def set_time(self, **kwargs: int) -> dict[str, str]:
        """直接设置绝对时间值（非增量推进）。

        支持 year/month/day/hour/minute 字段，hour 使用 24h 制。
        例::

            tracker.set_time(year=3, month=6, day=15, hour=14, minute=30)
            # → 时间变为 "第 3 年 6 月 15 日 14 时 30 分"

        其余关键字参数直接写入状态表（不参与 _format_time）。
        """
        pending_attrs: dict[str, str] = {}
        time_values: dict[str, int] = {}
        for k, v in kwargs.items():
            if k in self.TIME_STATE_FIELDS:
                if isinstance(v, bool) or not isinstance(v, int):
                    raise ValueError(f"SceneTime {k} must be an integer")
                time_values[k] = v
            else:
                pending_attrs[k] = str(v)

        if self._scene_time is None:
            required = {"year", "month", "day", "hour"}
            missing = sorted(required - set(time_values))
            if missing:
                raise ValueError(
                    "当前 scene 时间无效，修复时必须同时提供 year/month/day/hour"
                )
            next_scene_time = SceneTime(
                year=time_values["year"],
                month=time_values["month"],
                day=time_values["day"],
                hour=time_values["hour"],
                minute=time_values.get("minute", 0),
            )
        else:
            next_scene_time = self._scene_time.update(**time_values)

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

        attrs = self._runtime_set_attr(self.TIME_ATTR, next_scene_time.format())
        self._scene_time = next_scene_time
        self._scene_time_error = ""
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
        parsed_time: SceneTime | None = None
        if key == self.TIME_ATTR:
            parsed_time = SceneTime.parse(value)
            value = parsed_time.format()
        result = self._runtime_set_attr(key, value)
        if parsed_time is not None:
            self._scene_time = parsed_time
            self._scene_time_error = ""
        return result

    def delete_attr(self, key: str) -> dict[str, str]:
        """删除场景属性；失败时返回 rpg_data 当前状态。"""
        if not self._allow_runtime_key_changes:
            raise PermissionError("LLM 不允许删除或重命名场景字段")
        if self._status_mgr is not None and self._scene_table_id is not None:
            try:
                table = self._status_mgr.runtime_delete_key_value(self._scene_table_id, key)
                attrs = self._attrs_from_table(table)
                if key == self.TIME_ATTR and self.TIME_ATTR not in attrs:
                    self._scene_time = None
                    self._scene_time_error = "当前场景缺少非空“时间”字段"
                return attrs
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

    def get_recall_context(self) -> dict[str, str]:
        """Return only scene time/location fields used by memory query planning."""
        attrs = self._current_attrs()
        return {
            "time": _first_scene_value(attrs, ("时间", "日期", "时刻", "time", "date")),
            "location": _first_scene_value(
                attrs,
                ("地点", "位置", "场景", "location", "place"),
            ),
        }

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


def _first_scene_value(attrs: dict[str, str], keys: tuple[str, ...]) -> str:
    lowered = {str(key).strip().casefold(): str(value).strip() for key, value in attrs.items()}
    for key in keys:
        value = lowered.get(key.casefold(), "")
        if value:
            return value
    return ""
