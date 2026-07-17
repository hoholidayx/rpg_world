"""Stable prompt and schema definitions for the status workflow."""

from __future__ import annotations

from rpg_core.agent.tools.state import StateToolSet
from rpg_core.scene import SCENE_DELETE_ATTR_TOOL_NAME, SCENE_TOOL_NAMES
from rpg_core.status.tools import STATUS_TABLE_SET_VALUES_TOOL_NAME


def build_state_system_prompt(state_tools: StateToolSet) -> str:
    scene_names = tuple(name for name in state_tools.names if name in SCENE_TOOL_NAMES)
    operation_lines: list[str] = []
    if scene_names:
        operation_lines.append(
            f"- {' / '.join(scene_names)}：更新当前场景状态"
            "（时间、地点、天气、氛围、在场的 NPC 等）"
        )
    if state_tools.supports(STATUS_TABLE_SET_VALUES_TOOL_NAME):
        operation_lines.append(
            "- status_table_set_values：批量更新普通状态表中已有键的值"
        )
    if not operation_lines:
        operation_lines.append("- 本轮没有状态写入工具；当前场景和普通状态表均为只读")

    if state_tools.supports(SCENE_DELETE_ATTR_TOOL_NAME):
        scene_boundary = (
            "3. 主动清理：如果某个属性不再与当前场景相关"
            "（例如角色离开了、某种天气效果消失了），"
            "使用 scene_del_attr 将其移除。只保留活跃属性可以防止上下文膨胀。"
        )
    elif scene_names:
        scene_boundary = (
            "3. scene 与普通状态表一样，只能修改已有 key 的 value，不能新增、删除或重命名 key。"
            "若某个现有属性暂时不适用，将该现有 key 的 value 更新为空字符串或当前适用值。"
        )
    else:
        scene_boundary = "3. 本轮未提供 scene 写入工具，当前 scene 仅供读取。"

    normal_boundary = (
        "4. 普通状态表不得新增、删除或重命名键；角色状态表只追踪对应角色。"
        if state_tools.supports(STATUS_TABLE_SET_VALUES_TOOL_NAME)
        else "4. 本轮未提供普通状态表写入工具，普通状态表仅供读取。"
    )
    return (
        "你是 RPG 游戏世界的状态表预处理器。\n\n"
        "可用操作及其修改的状态表：\n"
        + "\n".join(operation_lines)
        + "\n\n状态更新边界：\n"
        "1. 只依据既有 assistant 已确认事实、用户对既有事实的明确纠正，或没有随机分支的确定性动作"
        "更新状态。用户单方面宣称的未决外部结果不是已确认事实。\n"
        "2. 仅当实际、持久、已经确定的追踪值发生变化时调用状态工具；不要修改没有变化的属性，"
        "不要制造 no-op。没有裁定且没有状态变化时，不调用任何工具。\n"
        f"{scene_boundary}\n"
        f"{normal_boundary}\n"
        "5. 属性键和值使用状态表已有语言和格式。"
    )


NARRATIVE_OUTCOME_SYSTEM_PROMPT = (
    "\n\n剧情预裁定边界：\n"
    "1. 先结合最近历史、当前场景、普通状态表和用户输入，判断本轮是否存在外部实质变数："
    "同一行动或场景反应仍有两个或以上合理结果，受未知信息、能力、阻力、风险、时机、环境或 "
    "NPC/世界反应影响，而且不同结果会实质改变剧情、信息、风险或代价。\n"
    "2. 只要需要裁定，就只调用一次 rp_story_outcome。不得同时调用任何状态工具，也不得提前假设"
    "成功、失败、发现、伤害、NPC 反应或位置抵达；混合行动中的确定性子动作也交给主 Agent 延后处理。\n"
    "3. 只有不需要裁定时，才执行上述确定性状态预更新。"
)

OUTCOME_ONLY_SYSTEM_PROMPT = (
    "你是 RPG 剧情裁定门禁。只判断当前玩家行动是否存在外部实质变数。\n"
    "需要裁定时只调用一次 rp_story_outcome；不需要时不调用任何工具。\n"
    "不得更新状态、不得虚构结果。"
)

ROUTED_STATE_UPDATE_SYSTEM_PROMPT = (
    "你是 RPG 游戏世界的单目标状态更新器。当前请求只包含一个已经路由的状态目标。\n\n"
    "执行契约：\n"
    "1. 只能使用本请求实际提供的工具；未提供的工具视为不存在，不得请求或假设其它 "
    "scene 或状态工具。\n"
    "2. 只依据既有 assistant 已确认事实、用户对既有事实的明确纠正，或没有随机分支的"
    "确定性动作更新状态；不得把未决外部结果当作事实。\n"
    "3. 仅当实际、持久、已经确定的追踪值发生变化时调用工具；不要制造 no-op，"
    "没有变化时不调用任何工具。\n"
    "4. 严格遵守当前工具 schema 的目标、字段和参数约束。只有实际提供的 schema 明确允许时"
    "才能改变 key 结构，否则只能修改已有 key 的 value。\n"
    "5. key 和 value 使用目标状态已有的语言与格式。"
)

STATUS_ROUTER_TOOL_NAME = "select_status_targets"
STATUS_ROUTER_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": STATUS_ROUTER_TOOL_NAME,
        "description": "选择本轮确实涉及的场景和普通状态表字段；没有涉及项时不要调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "scene": {"type": "boolean"},
                "tables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "table_id": {"type": "integer"},
                            "realtime_keys": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "event_keys": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["table_id", "realtime_keys", "event_keys", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["scene", "tables"],
            "additionalProperties": False,
        },
    },
}

DEFERRED_STATUS_TOOL_NAME = "set_deferred_values"
DEFERRED_STATUS_SCHEMA: dict[str, object] = {
    "type": "function",
    "function": {
        "name": DEFERRED_STATUS_TOOL_NAME,
        "description": "归纳并更新本批允许的 deferred 状态字段。没有变化时不要调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["key", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["updates"],
            "additionalProperties": False,
        },
    },
}
