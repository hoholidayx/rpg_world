"""SceneTracker — RPG 场景状态管理。

维护当前故事场景的时间、空间、人物等上下文，
通过 StatusManager 持久化到 rpg_data active scene 状态表。
"""

from commons.scene_time import SceneTime
from rpg_core.scene.tracker import SceneTracker
from rpg_core.scene.tools import (
    DeleteAttrTool,
    SCENE_ATTR_TOOL_NAME,
    SCENE_DELETE_ATTR_TOOL_NAME,
    SCENE_TIME_TOOL_NAME,
    SCENE_TOOL_NAMES,
    SetAttrTool,
    SetTimeTool,
)

__all__ = [
    "SceneTracker",
    "SceneTime",
    "DeleteAttrTool",
    "SCENE_ATTR_TOOL_NAME",
    "SCENE_DELETE_ATTR_TOOL_NAME",
    "SCENE_TIME_TOOL_NAME",
    "SCENE_TOOL_NAMES",
    "SetAttrTool",
    "SetTimeTool",
]
