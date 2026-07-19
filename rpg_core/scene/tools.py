"""LLM 工具 —— 场景状态操作。

所有工具继承 ``BaseTool``，绑定 ``SceneTracker`` 实例。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.tooling.base import BaseTool

if TYPE_CHECKING:
    from rpg_core.scene.tracker import SceneTracker

SCENE_TIME_TOOL_NAME = "scene_time"
SCENE_ATTR_TOOL_NAME = "scene_attr"
SCENE_DELETE_ATTR_TOOL_NAME = "scene_del_attr"
SCENE_TOOL_NAMES = frozenset({
    SCENE_TIME_TOOL_NAME,
    SCENE_ATTR_TOOL_NAME,
    SCENE_DELETE_ATTR_TOOL_NAME,
})


class SetTimeTool(BaseTool):
    """直接设置场景的绝对时间（非增量推进）。"""

    name = SCENE_TIME_TOOL_NAME
    description = (
        "直接设置当前场景的绝对时间。hour 使用 24h 制（0-23）。"
        " 使用示例：\n"
        '  - set_time(year=3, month=6, day=15, hour=14)  —— 设置第 3 年 6 月 15 日 14 时\n'
        '  - set_time(hour=9, minute=30)                 —— 仅调整到上午 9:30，年月日不变\n'
        '  - set_time(day=1, hour=0)                     —— 重置到当月第 1 天 0 时（午夜）\n'
        "  不支持增量推进（如 +1 天），所有参数都是直接设定值。"
    )

    def __init__(self, tracker: SceneTracker) -> None:
        self._tracker = tracker
        if not tracker.allow_runtime_key_changes:
            self.description = (
                "修改当前场景已有的“时间”字段值。hour 使用 24h 制（0-23）。"
                "该工具不能创建“时间”字段，也不能增删或重命名任何 key。"
            )

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "年份，例如 3 表示「第 3 年」",
                },
                "month": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 12,
                    "description": "月份，1-12",
                },
                "day": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 31,
                    "description": "日期，1-31",
                },
                "hour": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 23,
                    "description": "小时，24h 制（0=午夜, 9=上午9点, 14=下午2点, 23=晚上11点）",
                },
                "minute": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 59,
                    "description": "分钟，0-59",
                },
            },
        }

    async def execute(
        self,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int | None = None,
        minute: int | None = None,
    ) -> str:
        kwargs = {}
        if year is not None:
            kwargs["year"] = year
        if month is not None:
            kwargs["month"] = month
        if day is not None:
            kwargs["day"] = day
        if hour is not None:
            kwargs["hour"] = hour
        if minute is not None:
            kwargs["minute"] = minute
        try:
            attrs = self._tracker.set_time(**kwargs)
        except (PermissionError, ValueError) as exc:
            return f"设置失败：{exc}"
        time_str = attrs.get("时间", "")
        return f"时间已设置。当前时间：{time_str}"


class SetAttrTool(BaseTool):
    """创建或更新当前场景的属性。"""

    name = SCENE_ATTR_TOOL_NAME

    def __init__(self, tracker: SceneTracker) -> None:
        self._tracker = tracker
        if tracker.allow_runtime_key_changes:
            self.description = (
                "创建或更新当前场景属性。可新增非锁定字段，场景属性总数仍受上限约束。"
            )
        else:
            self.description = (
                "修改当前场景已有字段的 value。只能使用 schema 枚举的现有 key，"
                "不能新增、删除或重命名 key。"
            )

    def parameters(self) -> dict[str, object]:
        defaults = ", ".join(self._tracker.DEFAULT_ATTRS)
        key_schema: dict[str, object]
        if self._tracker.allow_runtime_key_changes:
            key_schema = {
                "type": "string",
                "description": (
                    f"属性名，如 {defaults} 等。"
                    f"建议优先复用现有属性名而非创建新属性。"
                    f"总数上限 {self._tracker.MAX_ATTRS} 个（含默认属性），"
                    f"超出需先删除不再需要的属性。"
                ),
            }
        else:
            key_schema = {
                "type": "string",
                "enum": list(self._tracker.attr_keys),
                "description": "当前 scene 中已经存在、仅允许修改 value 的字段名。",
            }
        return {
            "type": "object",
            "properties": {
                "key": key_schema,
                "value": {
                    "type": "string",
                    "description": "属性值",
                },
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        }

    async def execute(self, key: str, value: str) -> str:
        try:
            self._tracker.set_attr(key, value)
            return f"场景属性已设置：{key} = {value}"
        except (PermissionError, ValueError) as e:
            return f"设置失败：{e}"


class DeleteAttrTool(BaseTool):
    """删除当前场景的一个属性。"""

    name = SCENE_DELETE_ATTR_TOOL_NAME

    def __init__(self, tracker: SceneTracker) -> None:
        self._tracker = tracker

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "要删除的属性名。",
                },
            },
            "required": ["key"],
        }

    async def execute(self, key: str) -> str:
        before = self._tracker.get_context()
        try:
            attrs = self._tracker.delete_attr(key)
        except PermissionError as exc:
            return f"设置失败：{exc}"
        if key in attrs and before == self._tracker.get_context():
            return f"场景属性未删除：{key}"
        return f"场景属性已删除：{key}"
