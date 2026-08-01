"""Stable prompt and schema definitions for the status workflow."""

from __future__ import annotations

OUTCOME_ONLY_SYSTEM_PROMPT = (
    "你是 RPG 剧情裁定门禁。只判断当前用户输入是否存在外部实质变数。\n"
    "需要裁定时只调用一次 rp_story_outcome；不需要时不调用任何工具。\n"
    "只裁定当前输入，不得重新裁定近期历史里的旧行动或悬念。"
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
    "4. 严格遵守当前工具 schema 的目标、字段和参数约束。已有字段值使用 "
    "status_table_set_values；只有实际提供 status_table_edit_fields 时才能新增、"
    "重命名或删除字段。runtimeKeyLocked 只禁止重命名和删除，不禁止更新 value。\n"
    "5. 状态表 description 中的整表共同规则始终适用；目标字段存在非空 "
    "updateRule 时，还必须确认该字段专属条件已经满足；空规则仍使用通用事实变化"
    "条件。\n"
    "6. 只有属于当前表、真实持久且无法由现有字段表达的当前事实才新增字段；"
    "暂时失效通常更新 value，不要机械删除；字段身份确实错误时才改名。"
    "状态表不是历史流水。\n"
    "7. key 和 value 使用目标状态已有的语言与格式。"
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
                            "keys": {
                                "type": "array",
                                "description": "需要更新 value、重命名或删除的已有字段。",
                                "items": {"type": "string"},
                            },
                            "structure": {
                                "type": "boolean",
                                "description": (
                                    "该表是否需要新增、重命名或删除字段；"
                                    "纯新增时 keys 可以为空。"
                                ),
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["table_id", "keys", "structure", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["scene", "tables"],
            "additionalProperties": False,
        },
    },
}
