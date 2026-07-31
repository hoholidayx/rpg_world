"""Versioned Story authoring semantics and deterministic diagnostics.

The catalog in this module is the single source for generated Schema
descriptions, portable field references, the Viewer field guide, and MCP
validation diagnostics.  It deliberately depends only on the neutral MCP
contracts so design mode never imports RPG runtime modules.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from rpg_mcp.contracts import (
    OBJECTIVE_CHARACTER_DETAIL_TAGS,
    PORTRAYAL_CHARACTER_DETAIL_TAGS,
    StoryDesignDocument,
    StoryPack,
    digest_json,
)

AUTHORING_RULES_VERSION = "1.5"
AUTHORING_RULES_SCHEMA_VERSION = "story-authoring-rules/1.0"
AUTHORING_RULES_RELATIVE_PATH = (
    "schemas/story-authoring-rules-v1.json"
)
AuthoringProfile = Literal["draft", "package"]


_MODEL_INFO: dict[str, dict[str, str]] = {
    "StoryDesignDocument": {
        "token": "design",
        "domain": "project",
        "path": "",
        "title": "Story Design 根文档",
        "description": "一个可持久修订、可构建 Story Pack 的单 Story 设计文档。",
    },
    "StoryPack": {
        "token": "pack",
        "domain": "package",
        "path": "",
        "title": "Story Pack 根文档",
        "description": "从一个已确认 revision 构建的单 Story、merge-only 导入包。",
    },
    "ProjectIdentity": {
        "token": "project",
        "domain": "project",
        "path": "/project",
        "title": "设计项目身份",
        "description": "描述便携 DesignProject 自身，而不是 RPG World Workspace。",
    },
    "RuntimeTarget": {
        "token": "target",
        "domain": "project",
        "path": "/target",
        "title": "运行时目标",
        "description": "构建或预览 Story Pack 时使用的 RPG World 目标。",
    },
    "StoryCore": {
        "token": "story",
        "domain": "story",
        "path": "/story",
        "title": "Story 核心",
        "description": "Story 的管理摘要、固定提示、主题、边界与时间背景。",
    },
    "StoryResources": {
        "token": "resources",
        "domain": "project",
        "path": "/resources",
        "title": "Story 资源集合",
        "description": "直接归当前 Story 所有的创作资源和调度配置。",
    },
    "OpeningSpec": {
        "token": "opening",
        "domain": "story",
        "path": "/resources/openings/*",
        "title": "Opening",
        "description": "新 Session 绑定玩家角色后可选择的一条开场正文。",
    },
    "CharacterSpec": {
        "token": "character",
        "domain": "character",
        "path": "/resources/characters/*",
        "title": "角色卡",
        "description": "Story 直属角色的客观身份卡、详情与视觉锚点。",
    },
    "CharacterDetailSpec": {
        "token": "character-detail",
        "domain": "character",
        "path": "/resources/characters/*/details/*",
        "title": "角色详情",
        "description": "一条职责单一、带 kind 标签的客观或演绎详情。",
    },
    "LorebookSpec": {
        "token": "lorebook",
        "domain": "lorebook",
        "path": "/resources/lorebook/*",
        "title": "世界书条目",
        "description": "地点、组织、时代、物件或世界规则的一条事实资料。",
    },
    "StatusTableSpec": {
        "token": "status-table",
        "domain": "status",
        "path": "/resources/statusTables/*",
        "title": "状态表",
        "description": "创建或重置 Session 时复制的 Story 状态定义。",
    },
    "StatusRowSpec": {
        "token": "status-row",
        "domain": "status",
        "path": "/resources/statusTables/*/rows/*",
        "title": "状态字段",
        "description": "当前 turn 可即时判断并更新的一个状态键值。",
    },
    "NarrativeStyleSpec": {
        "token": "narrative-style",
        "domain": "composer",
        "path": "/resources/narrativeStyles/*",
        "title": "叙事风格",
        "description": "Workspace 侧创建并绑定到 Story 的固定写作风格 Prompt。",
    },
    "QuickReplySpec": {
        "token": "quick-reply",
        "domain": "composer",
        "path": "/resources/quickReplies/*",
        "title": "快捷回复",
        "description": "Story Composer 中供玩家主动选择的输入模板。",
    },
    "RPModuleSpec": {
        "token": "rp-module",
        "domain": "rp-module",
        "path": "/resources/rpModules/*",
        "title": "RP Module",
        "description": "Story 挂载的内置 RP 玩法模块及其允许配置。",
    },
    "PlotScheduleSpec": {
        "token": "plot-schedule",
        "domain": "plot",
        "path": "/resources/plotSchedule",
        "title": "剧情调度",
        "description": (
            "事件池、事件和大纲的 Story 级调度投影；自动选择由已提交 Scene"
            " 文档的净变化产生一次机会。"
        ),
    },
    "PlotPoolSpec": {
        "token": "plot-pool",
        "domain": "plot",
        "path": "/resources/plotSchedule/pools/*",
        "title": "剧情事件池",
        "description": (
            "在一次 Scene 调度机会中共享启用、加权抽取、候选批次和池级冷却策略的一组"
            "剧情事件。"
        ),
    },
    "PlotEventSpec": {
        "token": "plot-event",
        "domain": "plot",
        "path": "/resources/plotSchedule/events/*",
        "title": "剧情事件",
        "description": "可被事件池、大纲节点或 Session 临时标记引用的一条世界/NPC指令。",
    },
    "PlotOutlineSpec": {
        "token": "plot-outline",
        "domain": "plot",
        "path": "/resources/plotSchedule/outlines/*",
        "title": "剧情大纲",
        "description": "按位置和最早 SceneTime 资格门槛组织的一组一次性大纲节点。",
    },
    "PlotNodeSpec": {
        "token": "plot-node",
        "domain": "plot",
        "path": "/resources/plotSchedule/outlines/*/nodes/*",
        "title": "大纲节点",
        "description": "在一次 Scene 调度机会中按最早 SceneTime 引用剧情事件的节点。",
    },
    "VisualSpec": {
        "token": "visual",
        "domain": "visual",
        "path": "/resources/visualCatalog/*",
        "title": "视觉规格",
        "description": "可独立复用、可直接交给生图流程的归档 brief。",
    },
    "DecisionRecord": {
        "token": "decision",
        "domain": "workflow",
        "path": "/decisions/*",
        "title": "设计决策",
        "description": "已确认、暂定或被取代的结构化设计结论。",
    },
    "OpenQuestion": {
        "token": "open-question",
        "domain": "workflow",
        "path": "/openQuestions/*",
        "title": "开放问题",
        "description": "尚需用户决策、延期或已解决的设计问题。",
    },
    "SourceRecord": {
        "token": "source",
        "domain": "workflow",
        "path": "/sources/*",
        "title": "来源记录",
        "description": "只作为参考定位的来源，不自动获得导入授权。",
    },
    "StoryPackApplyPolicy": {
        "token": "apply-policy",
        "domain": "package",
        "path": "/applyPolicy",
        "title": "导入策略",
        "description": "Story Pack v2 固定的 merge-only、非删除策略。",
    },
}


_FIELD_DESCRIPTIONS: dict[str, str] = {
    "schemaVersion": "固定的文档 Schema 版本；只接受当前 v2 值。",
    "contractVersion": "固定的 MCP/Story Pack 合约版本；只接受 2.0。",
    "project": "DesignProject 的便携身份、语言和当前设计阶段。",
    "target": "构建或同步时的 Workspace/Story 目标；不是 Story 内容。",
    "story": "当前唯一 Story 的核心设定。",
    "resources": "当前 Story 的可导入资源集合。",
    "decisions": "结构化设计决策历史；不保存原始聊天记录。",
    "openQuestions": "仍待决策、已解决或延期的结构化问题。",
    "sources": "参考来源定位；来源存在不等于获准导入其全部内容。",
    "notes": "简短工作备忘；不要用作正式字段或聊天记录的替代品。",
    "stableId": "跨 revision、分包和运行时绑定保持稳定的文本 ID。",
    "projectId": "DesignProject 的稳定 ID；不是 Workspace ID。",
    "name": "面向作者和管理界面的名称。",
    "language": "主要创作语言的 BCP 47 风格标记。",
    "phase": "当前设计成熟阶段，用于恢复工作而非运行时剧情状态。",
    "workspaceId": "目标 RPG World Workspace 的稳定文本 ID。",
    "workspaceName": "仅在允许创建 Workspace 时使用的显示名。",
    "workspaceRoot": "目标 Workspace 的安全相对运行目录。",
    "storyId": "已存在目标 Story 的运行时数字 ID；新建时留空。",
    "allowCreateWorkspace": "目标 Workspace 不存在时是否允许导入流程创建它。",
    "title": "面向作者、玩家或管理界面的短标题。",
    "summary": "Story 的短管理摘要，说明体验与前提，不写执行指令。",
    "storyPrompt": "每个 Agent 正文 turn 使用的固定 Story 规则与叙事约束。",
    "timeSetting": "故事虚拟年代、历法与时间锚点的文字说明。",
    "logline": "一句话核心冲突：主角、目标、阻力和主要代价。",
    "themes": "需要持续回响的主题关键词或短语。",
    "boundaries": "内容安全边界与明确不可发生的叙事行为。",
    "metadata": "仅放没有正式字段承载的中立扩展数据。",
    "message": "实际提交给玩家或 Agent 的正文文本。",
    "sortOrder": "稳定显示顺序；数值越小越靠前。",
    "description": "供作者和管理界面理解对象用途的说明。",
    "aliases": "角色可被识别的别名、称呼或旧名。",
    "details": "按职责拆分的角色客观详情或 NPC 演绎详情。",
    "visual": "与本资源绑定的视觉身份锚点和可变造型资料。",
    "content": "该详情或世界书条目的完整正文事实。",
    "tags": "检索和运行时过滤使用的去重标签。",
    "key": "状态字段名；同一表内唯一。",
    "value": "当前初始值；运行时可在本 turn 依据已确认事实即时更新。",
    "runtimeKeyLocked": (
        "为 true 时只禁止运行时删除或重命名该字段；不锁定 value，"
        "也不禁止在同表新增其他字段。"
    ),
    "updateRule": "在通用明确事实规则之上的额外即时更新语义指导。",
    "statusKind": "scene 表示当前场景；normal 表示普通 Story/角色状态。",
    "characterRef": "可选的同 Story 角色 stableId，用于角色状态分组。",
    "rows": "该状态表的有序字段定义。",
    "prompt": "提供给对应生成环节的正向指令正文。",
    "isBase": "是否作为唯一基础叙事风格；同一 Story 最多一个。",
    "enabled": "是否在导入后启用该资源或模块。",
    "moduleName": "仓库内置 RP Module 的代码名称。",
    "config": "模块公开契约允许的 Story 配置；message_mode 必须为空。",
    "pools": "剧情事件池定义。",
    "events": "剧情事件定义；每条事件只归一个池。",
    "outlines": "顺序大纲定义。",
    "selectionMode": "有 Scene 调度机会时，池内候选的 random 或 sequential 抽取方式。",
    "priority": "一次 Scene 调度机会内，同类候选之间的相对优先级。",
    "selectionWeight": "稳定加权抽取使用的正整数相对权重；默认 1。",
    "candidateBatchSize": (
        "random 池的 soft 主候选用于一次适宜性重排的召回批次大小；"
        "范围 1–5，默认 3。"
    ),
    "cooldownMinutes": (
        "事件池最近一次由自动调度成功注入任意池内事件后，需要经过的"
        " SceneTime 分钟冷却；0 表示不启用池级冷却。"
    ),
    "poolRef": "该事件所属事件池的 stableId。",
    "directive": "触发后主 Agent 必须落实的世界与 NPC 行动要求。",
    "suitabilityHint": "自动 soft 候选通过 judge 判断此刻是否适合开始事件的补充条件。",
    "dispatchMode": (
        "一次 Scene 调度机会内的自动候选满足 SceneTime 窗口后，forced 跳过"
        " soft judge，soft 仍需适宜性判断；手动标记不读取此字段。"
    ),
    "scheduledTime": (
        "仅在 Scene 调度机会存在时作为自动候选最早资格门槛的 SceneTime；"
        "不是定时器。"
    ),
    "deadlineTime": (
        "仅在 Scene 调度机会存在时作为自动事件候选窗口的排他上界；"
        "不是定时器。"
    ),
    "position": "同一容器内的稳定顺序位置。",
    "allowRepeat": "该事件自动触发后是否允许在后续 Scene 调度机会再次候选。",
    "repeatCooldownMinutes": "重复事件两次自动触发之间的 SceneTime 分钟冷却。",
    "nodes": "该大纲按 position 排列的节点。",
    "eventRef": "该节点引用的剧情事件 stableId。",
    "assetType": "视觉资产用途类别，例如角色立绘、场景或地图。",
    "negativePrompt": "明确需要排除的视觉元素、瑕疵或风格。",
    "subjectRefs": "该视觉 brief 涉及的 Story 资源 stableId。",
    "visualAnchors": "跨图片应保持稳定的身份、形制和辨识特征。",
    "topic": "本次决策处理的简短主题。",
    "decision": "实际确认或暂定的设计结论。",
    "rationale": "选择该方案的简短理由和关键权衡。",
    "status": "该记录当前的工作流状态。",
    "decidedAt": "决策落入 revision 时的 UTC 时间。",
    "id": "该决策、问题或来源在项目内保持稳定的文本 ID。",
    "question": "需要用户回答的单一、可决策问题。",
    "options": "可供比较的具体选项，不代替用户确认。",
    "context": "理解该问题所需的背景和影响。",
    "sourceType": "来源类别，例如本地文档、导出会话或外部网址。",
    "locator": "外部 URL/ID 或 DesignProject 内安全相对路径。",
    "packId": "由 revision、目标和 sections 确定的不可变 Story Pack ID。",
    "storyStableId": "Story 的稳定 ID，必须与 story.stableId 相同。",
    "sourceRevision": "构建本包的不可变 DesignProject revision。",
    "sourceDigest": "构建时源 Story Design 的 SHA-256 摘要。",
    "generatedAt": "包构建时沿用的确定性 UTC 时间。",
    "includedSections": "本包实际携带的 merge-only sections。",
    "applyPolicy": "固定的 merge-only、deleteMissing=false 导入策略。",
    "mode": "Story Pack v2 固定为 merge。",
    "deleteMissing": "Story Pack v2 固定为 false；遗漏资源不代表删除。",
    "openings": "最多三条按 sortOrder 排序的 Opening。",
    "characters": "直接归当前 Story 所有的角色卡。",
    "lorebook": "直接归当前 Story 所有的世界书条目。",
    "statusTables": "直接归当前 Story 所有的状态定义。",
    "narrativeStyles": "需在 Workspace 创建并绑定到 Story 的叙事风格。",
    "quickReplies": "Story Composer 的快捷玩家输入。",
    "rpModules": "Story 允许启用的内置 RP Module。",
    "plotSchedule": (
        "Story 级事件池、大纲和事件调度配置；自动 selector 只在已提交 Scene"
        " 净变化留下机会后运行。"
    ),
    "visualCatalog": "只归档、不自动创建媒体任务的独立视觉 brief。",
}


_FIELD_OVERRIDES: dict[tuple[str, str], str] = {
    ("CharacterSpec", "description"): (
        "只写角色身份、经历和客观事实；性格、口癖、行为倾向与心理必须拆到"
        "带演绎 kind 标签的 details。"
    ),
    ("CharacterDetailSpec", "name"): "该条详情的职责标题，例如“外貌”或“NPC 说话方式”。",
    ("CharacterDetailSpec", "content"): "只写当前 kind 对应的一类信息，避免客观事实与演绎要求混写。",
    ("CharacterDetailSpec", "tags"): (
        "使用一个主要 kind 标签；演绎 kind 会自动附加 scope:npc_portrayal。"
    ),
    ("LorebookSpec", "description"): "供作者浏览的短管理摘要，不代替 content 世界事实。",
    ("LorebookSpec", "content"): "Agent 可使用的完整世界事实、规则、地点或组织资料。",
    ("StatusTableSpec", "description"): (
        "说明该表追踪什么，并集中写整表共同语义、value 格式和即时更新规则；"
        "字段专属条件写入 row.updateRule。normal 表若存在无法预先穷举的字段，"
        "还应说明动态 key 的业务域、命名与 value 格式，以及创建、改名和删除条件；"
        "无需预定义全部未来字段。"
    ),
    ("StatusRowSpec", "value"): (
        "当前初始值，以字符串表达；可按表约定表示数值、枚举、列表、简短描述或"
        "当前事实状态。"
        "运行时可在本 turn 依据已确认事实即时更新。"
    ),
    ("StatusRowSpec", "updateRule"): (
        "只写该字段专属的额外即时语义条件；整表共同规则写入表 description。"
        "不得写频率、延迟、后台调度、人工只读或数据库权限。留空时使用"
        "“事实明确且值实际变化”的通用规则。"
    ),
    ("StatusRowSpec", "runtimeKeyLocked"): (
        "为 true 时只保护该字段不被运行时删除或重命名；仍允许更新 value，"
        "也不妨碍同表新增其他未锁字段。"
    ),
    ("PlotPoolSpec", "description"): (
        "说明池的主题、用途、自动候选边界和建议冷却档位，不写单个事件指令。"
    ),
    ("PlotPoolSpec", "enabled"): (
        "是否允许该池参与有 Scene 调度机会的自动候选；手动标记忽略此字段。"
    ),
    ("PlotPoolSpec", "selectionWeight"): (
        "事件池通过全部确定性资格规则后，在可用池之间稳定加权抽取的相对权重；"
        "正整数且默认 1。它表达长期概率，不是严格顺序或有限轮次保底。"
    ),
    ("PlotPoolSpec", "candidateBatchSize"): (
        "random 池按事件权重抽到 soft 主候选后，本轮最多召回多少个 soft 事件"
        "交给一次 LLM 适宜性重排；范围 1–5、默认 3，1 表示单候选。"
        "sequential 池忽略此字段。"
    ),
    ("PlotPoolSpec", "cooldownMinutes"): (
        "池内任意事件最近一次以 scheduler 来源在 pool lane 成功注入后，整个池"
        "需等待的 SceneTime 分钟；0 表示关闭。手动标记、大纲注入、延期和错误"
        "都不启动、刷新或清除池级冷却。创作时可按强度分池：日常现实扰动建议"
        "半天到一天，人际/信息/工作压力建议数天，改变关系结构的戏剧性巧合"
        "建议十天到数周；这些只是调参建议，不是 schema 默认值。"
    ),
    ("PlotEventSpec", "description"): "管理摘要：事件是什么、为什么存在；不承担触发指令。",
    ("PlotEventSpec", "directive"): (
        "事件触发后必须落实的世界/NPC行为；保留玩家选择，不把后果提前写成事实。"
    ),
    ("PlotEventSpec", "suitabilityHint"): (
        "只说明自动 soft 候选何时适合开始，包括阶段、地点、在场角色、前置"
        "事实和安全边界；不重复 directive，手动标记不会执行该判断。"
    ),
    ("PlotEventSpec", "enabled"): (
        "是否允许事件参与自动 pool lane 候选；大纲节点是否候选由大纲与节点"
        "自身开关决定，Session 手动标记的临时注入也忽略此字段。"
    ),
    ("PlotEventSpec", "poolRef"): (
        "该事件所属事件池的 stableId，用于归属、展示及未绑定大纲时的 pool lane"
        "调度；只要仍被任意大纲节点引用，就不参与自动 pool lane。"
    ),
    ("PlotEventSpec", "selectionWeight"): (
        "random 池在结构性可用事件中选择主候选和补充 soft 候选时使用的正整数"
        "召回权重；默认 1。最终注入仍由场景适宜性重排决定，不承诺同等最终频率。"
        "sequential 池和大纲 lane 忽略此字段。"
    ),
    ("PlotEventSpec", "allowRepeat"): (
        "事件自动触发后是否可在后续 Scene 调度机会再次候选；手动标记忽略"
        "重复限制。"
    ),
    ("PlotEventSpec", "repeatCooldownMinutes"): (
        "重复事件两次自动触发之间的 SceneTime 分钟冷却；手动标记忽略冷却，"
        "且无 SceneTime 的手动注入会解除该事件已有的事件级冷却锚点，但不"
        "影响池级冷却。"
    ),
    ("PlotOutlineSpec", "description"): (
        "说明大纲线的主题、节点顺序与用途；节点仍只在 Scene 调度机会中成为"
        "自动候选。"
    ),
    ("PlotOutlineSpec", "enabled"): (
        "是否允许该大纲参与有 Scene 调度机会的自动候选；不限制其事件被手动"
        "标记。"
    ),
    ("PlotNodeSpec", "dispatchMode"): (
        "一次 Scene 调度机会内，节点满足 SceneTime 门槛后，forced 跳过 soft"
        " judge，soft 仍需适宜性判断；手动标记事件不读取节点字段。"
    ),
    ("PlotNodeSpec", "scheduledTime"): (
        "仅在 Scene 调度机会存在时作为节点自动候选的最早资格门槛；不是"
        "定时器。注入只代表触发 directive，不代表章节完成。"
    ),
    ("PlotNodeSpec", "enabled"): (
        "是否允许节点参与有 Scene 调度机会的自动候选；不限制事件被手动标记。"
    ),
    ("VisualSpec", "prompt"): "可直接生图的正向 brief，写主体、场景、构图、光线和风格。",
    ("VisualSpec", "visualAnchors"): "只放跨变体必须稳定的身份或物件特征，不放姿势和光线。",
    ("SourceRecord", "locator"): (
        "只定位参考资料；不得使用绝对路径、file: URL 或 .. 逃逸项目根目录。"
    ),
    ("RPModuleSpec", "config"): (
        "只填写模块公开 Schema 支持的配置；message_mode 是代码内置空配置模块。"
    ),
}


_FIELD_AVOID: dict[tuple[str, str], str] = {
    ("StoryCore", "summary"): "不要写固定 Prompt、逐场景正文或当前 Session 状态。",
    ("StoryCore", "storyPrompt"): "不要写易变 Scene、当前状态值或 message_mode 提示。",
    ("StoryCore", "timeSetting"): "不要用“1 年”代替已确定的 2019、2020 等虚拟年份。",
    ("StoryCore", "metadata"): "不要写 _rpgStoryDesign；该键由运行时适配器保留。",
    ("CharacterSpec", "description"): "不要写性格、说话方式、行为倾向或心理活动。",
    ("CharacterDetailSpec", "content"): "不要在同一 detail 混合客观信息和 NPC 演绎要求。",
    ("CharacterDetailSpec", "tags"): "不要发明 kind:/scope: 保留标签或手工移除演绎 scope。",
    ("StatusTableSpec", "description"): (
        "不要逐字段复制相同规则，也不要把表当作无限追加的历史流水。当前事实、"
        "承诺、联系或事件状态可以成为字段；按时间累积的叙事历史更适合 Memory。"
        "normal 表需要动态字段时，不要省略可创建字段的领域、格式与删除边界。"
    ),
    ("StatusRowSpec", "runtimeKeyLocked"): (
        "不要把它理解为 value 只读，也不要理解成禁止同表新增其他字段。"
    ),
    ("StatusRowSpec", "updateRule"): (
        "不要重复表 description 的共同规则，也不要预设 value 是数值或写每 N "
        "回合、延迟、定时、manual 或 read-only 规则；不要用无事实变化的"
        " Scene 更新轮询 Plot。"
    ),
    ("PlotEventSpec", "description"): "不要用命令语气要求主 Agent 落实剧情。",
    ("PlotEventSpec", "directive"): "不要替玩家决定行动、同意或情绪，也不要预写未发生后果。",
    ("PlotEventSpec", "suitabilityHint"): (
        "不要把它当确定性 DSL、手动注入条件或重复剧情正文。"
    ),
    ("PlotEventSpec", "dispatchMode"): (
        "不要把 forced 理解成定时器；没有 Scene 调度机会时不会因此自动运行。"
    ),
    ("PlotEventSpec", "scheduledTime"): (
        "不要把时间门槛解释成后台定时器或每 turn 轮询触发器。"
    ),
    ("PlotEventSpec", "deadlineTime"): (
        "不要把截止时间解释成会自行唤醒 selector 的定时器。"
    ),
    ("PlotEventSpec", "allowRepeat"): (
        "不要把手动标记的临时注入计入自动重复资格。"
    ),
    ("PlotEventSpec", "repeatCooldownMinutes"): (
        "不要把冷却写成现实时间、turn 数或手动注入限制。"
    ),
    ("PlotEventSpec", "selectionWeight"): (
        "不要把召回权重解释成最终注入概率、严格优先级或有限轮次保底。"
    ),
    ("PlotPoolSpec", "selectionWeight"): (
        "不要用 0 表示停用；停用使用 enabled，也不要把权重解释成严格优先级。"
    ),
    ("PlotPoolSpec", "candidateBatchSize"): (
        "不要把批次大小解释成多次 Judge 调用或一轮注入多个池事件。"
    ),
    ("PlotNodeSpec", "dispatchMode"): (
        "不要把 forced 节点理解成定时器；没有 Scene 调度机会时不会因此"
        "自动运行。"
    ),
    ("PlotNodeSpec", "scheduledTime"): (
        "不要把节点时间解释成章节完成时间、后台定时器或每 turn 轮询触发器。"
    ),
    ("VisualSpec", "prompt"): "不要把排除项混入正向 prompt；排除项写 negativePrompt。",
    ("VisualSpec", "visualAnchors"): "不要写可变服装、姿势、镜头或照明，除非它们是身份锚点。",
    ("SourceRecord", "locator"): "不要因来源已登记就自动导入其全部内容。",
    ("RPModuleSpec", "config"): "不要为 message_mode 创建 Prompt、模式标签或 Workspace 配置。",
    ("StoryPackApplyPolicy", "deleteMissing"): "不要把小包遗漏解释成删除授权。",
}


_EXAMPLES: dict[str, Any] = {
    "schemaVersion": "story-design/2.0",
    "contractVersion": "2.0",
    "project": {},
    "target": {"workspaceId": "my_world"},
    "story": {"stableId": "story-main", "title": "雨夜来信"},
    "resources": {},
    "decisions": [],
    "openQuestions": [],
    "sources": [],
    "notes": ["下一步确认玩家角色。"],
    "stableId": "character-lin-che",
    "projectId": "rain-letter-design",
    "name": "林澈",
    "language": "zh-CN",
    "phase": "architecture",
    "workspaceId": "rain_world",
    "workspaceName": "雨夜世界",
    "workspaceRoot": "data/rain_world",
    "storyId": 42,
    "allowCreateWorkspace": False,
    "title": "停电前的证词",
    "summary": "一名调查员在城市停电前追查被主动删除的证词。",
    "storyPrompt": "保持悬疑节奏；所有关键选择由玩家作出。",
    "timeSetting": "2020 年上海，故事从 7 月 18 日开始。",
    "logline": "失忆调查员必须在全城停电前找回自己主动删除的证词。",
    "themes": ["记忆与责任", "信任"],
    "boundaries": ["不得替玩家决定行动或同意。"],
    "metadata": {},
    "message": "雨水敲打窗面，一封没有寄件人的信滑进门缝。",
    "sortOrder": 10,
    "description": "供作者识别用途的简短摘要。",
    "aliases": ["阿澈"],
    "details": [],
    "visual": {"identityAnchors": ["黑色短发", "旧银色录音笔"]},
    "content": "白鸢咖啡馆位于旧城区河岸，二层不对外开放。",
    "tags": ["kind:appearance"],
    "key": "信任",
    "value": "初次见面",
    "runtimeKeyLocked": True,
    "updateRule": "仅在双方明确表达并确认新的关系定位时更新。",
    "statusKind": "normal",
    "characterRef": "character-lin-che",
    "rows": [],
    "prompt": "使用克制的近距离感官描写，避免解释人物未说出口的动机。",
    "isBase": True,
    "enabled": True,
    "moduleName": "message_mode",
    "config": {},
    "pools": [],
    "events": [],
    "outlines": [],
    "selectionMode": "sequential",
    "priority": 10,
    "selectionWeight": 1,
    "candidateBatchSize": 3,
    "cooldownMinutes": 1440,
    "poolRef": "pool-main",
    "directive": "让停电警报响起，并由在场 NPC 提出两种可调查方向。",
    "suitabilityHint": "玩家已抵达旧城区，且尚未取得录音笔中的第二段录音。",
    "dispatchMode": "soft",
    "scheduledTime": "2020 年 7 月 18 日 9 时",
    "deadlineTime": "2020 年 7 月 21 日 18 时",
    "position": 10,
    "allowRepeat": False,
    "repeatCooldownMinutes": 0,
    "nodes": [],
    "eventRef": "event-blackout-warning",
    "assetType": "character_portrait",
    "negativePrompt": "文字、水印、多余手指",
    "subjectRefs": ["character-lin-che"],
    "visualAnchors": ["黑色短发", "左眉浅疤"],
    "topic": "核心冲突",
    "decision": "主角曾主动删除自己的证词。",
    "rationale": "让失忆与玩家能动性直接相关。",
    "status": "confirmed",
    "decidedAt": "2026-07-24T09:00:00Z",
    "id": "decision-core-conflict",
    "question": "玩家角色是否知道自己删除过证词？",
    "options": ["开局知情", "中段揭示"],
    "context": "影响开局悬念与玩家能动性。",
    "sourceType": "local_document",
    "locator": "design/sources/background.md",
    "packId": "rain-letter-r000012-a1b2c3d4e5f6",
    "storyStableId": "story-main",
    "sourceRevision": "r000012",
    "sourceDigest": "0" * 64,
    "generatedAt": "2026-07-24T09:00:00Z",
    "includedSections": ["story", "characters"],
    "applyPolicy": {"mode": "merge", "deleteMissing": False},
    "mode": "merge",
    "deleteMissing": False,
    "openings": [],
    "characters": [],
    "lorebook": [],
    "statusTables": [],
    "narrativeStyles": [],
    "quickReplies": [],
    "rpModules": [],
    "plotSchedule": {"pools": [], "events": [], "outlines": []},
    "visualCatalog": [],
}


_EXAMPLE_OVERRIDES: dict[tuple[str, str], Any] = {
    ("StoryPack", "schemaVersion"): "rpg-story-pack/2.0",
    ("ProjectIdentity", "name"): "雨夜来信故事设计",
    ("StoryCore", "stableId"): "story-main",
    ("StoryCore", "title"): "雨夜来信",
    ("OpeningSpec", "stableId"): "opening-anonymous-letter",
    ("OpeningSpec", "title"): "匿名来信",
    ("CharacterSpec", "description"): "调查记者，2018 年起追查旧城区失踪案。",
    ("CharacterDetailSpec", "stableId"): "detail-lin-che-speech",
    ("CharacterDetailSpec", "name"): "NPC 说话方式",
    ("CharacterDetailSpec", "content"): "句子短，避免夸张修辞；紧张时会先确认事实。",
    ("CharacterDetailSpec", "tags"): [
        "kind:speech",
        "scope:npc_portrayal",
    ],
    ("LorebookSpec", "stableId"): "lore-white-kite-cafe",
    ("LorebookSpec", "name"): "白鸢咖啡馆",
    ("LorebookSpec", "description"): "旧城区的中立会面地点。",
    ("LorebookSpec", "tags"): ["地点", "旧城区"],
    ("LorebookSpec", "visual"): {
        "identityAnchors": ["临河红砖外墙", "二层窄拱窗"],
    },
    ("StatusTableSpec", "stableId"): "status-current-scene",
    ("StatusTableSpec", "name"): "当前场景",
    ("StatusTableSpec", "statusKind"): "scene",
    ("StatusTableSpec", "characterRef"): None,
    ("StatusTableSpec", "description"): (
        "追踪当前 Session 的时间、位置与在场人物。"
    ),
    ("StatusTableSpec", "rows"): [
        {
            "key": "时间",
            "value": "2020 年 7 月 18 日 9 时",
            "runtimeKeyLocked": True,
            "updateRule": "当当前 Scene 中已确认发生时间推进时立即更新。",
            "metadata": {},
        },
        {
            "key": "位置",
            "value": "白鸢咖啡馆",
            "runtimeKeyLocked": True,
            "updateRule": "当当前 Scene 的地点已明确改变时立即更新。",
            "metadata": {},
        },
        {
            "key": "在场人物",
            "value": "林澈",
            "runtimeKeyLocked": True,
            "updateRule": "当人物明确进入或离开当前 Scene 时立即更新。",
            "metadata": {},
        },
    ],
    ("StatusRowSpec", "key"): "时间",
    ("StatusRowSpec", "value"): "2020 年 7 月 18 日 9 时",
    ("StatusRowSpec", "updateRule"): (
        "当当前 Scene 中已确认发生时间推进时，立即更新为新的故事虚拟时间。"
    ),
    ("NarrativeStyleSpec", "stableId"): "style-close-suspense",
    ("NarrativeStyleSpec", "name"): "克制悬疑",
    ("QuickReplySpec", "stableId"): "quick-check-envelope",
    ("QuickReplySpec", "title"): "检查信封",
    ("QuickReplySpec", "message"): "我先检查信封和门外是否留下痕迹。",
    ("PlotPoolSpec", "stableId"): "pool-main",
    ("PlotPoolSpec", "name"): "主线事件池",
    ("PlotPoolSpec", "description"): "承载推动失踪案调查的主线事件。",
    ("PlotPoolSpec", "selectionWeight"): 2,
    ("PlotPoolSpec", "candidateBatchSize"): 3,
    ("PlotPoolSpec", "cooldownMinutes"): 4320,
    ("PlotEventSpec", "stableId"): "event-blackout-warning",
    ("PlotEventSpec", "title"): "停电警报",
    ("PlotEventSpec", "description"): "停电前第一次公开警报，为调查线提供转向机会。",
    ("PlotEventSpec", "selectionWeight"): 1,
    ("PlotOutlineSpec", "stableId"): "outline-main",
    ("PlotOutlineSpec", "name"): "主线大纲",
    ("PlotOutlineSpec", "description"): "按故事虚拟时间推进失踪案调查。",
    ("PlotNodeSpec", "stableId"): "node-blackout-warning",
    ("VisualSpec", "stableId"): "visual-lin-che-portrait",
    ("VisualSpec", "title"): "林澈基础立绘",
    ("VisualSpec", "prompt"): "半身角色立绘，黑色短发调查员，雨夜窗边，冷蓝侧光。",
    ("SourceRecord", "id"): "source-background",
    ("SourceRecord", "title"): "故事背景设定",
    ("SourceRecord", "notes"): "仅作为背景参考，正式内容需写入当前 revision。",
    ("OpenQuestion", "id"): "question-player-knowledge",
    ("OpenQuestion", "status"): "open",
    ("DecisionRecord", "id"): "decision-core-conflict",
}


_RUNTIME_EFFECTS: dict[str, str] = {
    "project": "只影响 DesignProject 恢复、构建目标和作者工作流。",
    "story": "进入 Story 固定层或 Story 管理数据，并影响后续 Session。",
    "character": "进入角色卡；演绎 detail 会按玩家/NPC与 GM turn 过滤。",
    "lorebook": "作为 Story 世界知识进入运行时检索与 Context。",
    "status": (
        "创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。"
        "已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；"
        "Scene 的结构权限继续由专用 Scene 配置控制。"
    ),
    "composer": "影响 Story 叙事风格绑定或玩家快捷输入。",
    "rp-module": "限定 Story 可用的内置 RP 能力；Session 只能在其内覆盖。",
    "plot": (
        "影响 Scene 净变化所产生的一次性自动调度机会，以及下一次非 OOC"
        " turn 的候选、判断和 directive 注入。"
    ),
    "visual": "仅归档可生图规格，不创建媒体资产、任务或消息。",
    "workflow": "只影响设计恢复与决策追踪，不直接进入运行时 Story。",
    "package": "控制 Story Pack 身份、范围和 merge-only 导入行为。",
}


_RUNTIME_EFFECT_OVERRIDES: dict[tuple[str, str], str] = {
    ("StoryDesignDocument", "story"): _RUNTIME_EFFECTS["story"],
    ("StoryDesignDocument", "resources"): (
        "承载可进入 Story Pack 的 Story 直属资源；各子字段按其资源类型影响运行时。"
    ),
    ("StoryResources", "openings"): (
        "进入 Story Opening 定义；首次有效绑定角色且历史为空时可追加所选开场。"
    ),
    ("StoryResources", "characters"): _RUNTIME_EFFECTS["character"],
    ("StoryResources", "lorebook"): _RUNTIME_EFFECTS["lorebook"],
    ("StoryResources", "statusTables"): _RUNTIME_EFFECTS["status"],
    ("StoryResources", "narrativeStyles"): _RUNTIME_EFFECTS["composer"],
    ("StoryResources", "quickReplies"): _RUNTIME_EFFECTS["composer"],
    ("StoryResources", "rpModules"): _RUNTIME_EFFECTS["rp-module"],
    ("StoryResources", "plotSchedule"): _RUNTIME_EFFECTS["plot"],
    ("StoryResources", "visualCatalog"): _RUNTIME_EFFECTS["visual"],
}


_PRINCIPLES: tuple[dict[str, str], ...] = (
    {
        "ruleId": "principle.story-owned-resources",
        "domain": "project",
        "title": "Story 直属资源",
        "description": (
            "Character、Lorebook 与 Status 都直接归 Story 所有；不得设计"
            " Workspace 资产库或 mount 层。"
        ),
        "runtimeEffect": "运行时 CRUD 和稳定绑定都以 workspaceId + storyId 校验归属。",
    },
    {
        "ruleId": "principle.current-revision-publishes",
        "domain": "workflow",
        "title": "只有当前 revision 可发布",
        "description": (
            "本地 revision 不等于发布；只从 current revision 构建 Story Pack。"
        ),
        "runtimeEffect": "历史 revision 和 source 文件不会因存在而进入运行时。",
    },
    {
        "ruleId": "principle.sources-are-reference-only",
        "domain": "workflow",
        "title": "来源不自动获得导入授权",
        "description": (
            "历史导出和 sources 只作为参考；内容必须重新选择、编写并确认后"
            "进入当前 revision。"
        ),
        "runtimeEffect": "导入只消费 Story Pack，不扫描 sources。",
    },
    {
        "ruleId": "principle.status-immediate",
        "domain": "status",
        "title": "状态值即时判断",
        "description": (
            "所有状态 value 都在 neutral、ic 或 gm 的当前正文 turn 根据明确"
            "事实判断更新。整表共同语义、value 格式和即时更新规则写入"
            " description；row.updateRule 只补充字段专属条件，不预设数值"
            "模型。状态表保存需要每轮可见和更新的当前状态；Memory 更适合按"
            "时间累积的叙事历史，但当前事实仍可成为状态字段。"
        ),
        "runtimeEffect": (
            "StatusSubAgent 在 neutral、ic 或 gm 正文 turn 按目标即时处理"
            "状态；OOC 与命令不推进状态事实。"
        ),
    },
    {
        "ruleId": "principle.status-normal-field-crud",
        "domain": "status",
        "title": "普通状态表允许字段级运行时 CRUD",
        "description": (
            "neutral、ic 或 gm 正文 turn 可在已有 normal Session 状态表内按"
            "明确事实创建、读取、更新、改名和删除字段，但不能创建、删除或"
            "重命名整张表。读取来自每轮完整状态 Context；结构变化只用于当前"
            "事实模型，不把状态表变成历史流水。OOC 与命令只读。"
        ),
        "runtimeEffect": (
            "已有字段 value 使用 status_table_set_values；字段新增、改名或删除"
            "使用 status_table_edit_fields，并与消息一起在 turn 事务中提交。"
            "runtimeKeyLocked=true 只禁止该字段改名和删除，不限制 value 更新"
            "或同表新增其他字段。Scene 不继承 normal 权限，仍遵循"
            " agent.scene.allow_runtime_key_changes。"
        ),
    },
    {
        "ruleId": "principle.message-mode-code-owned",
        "domain": "rp-module",
        "title": "message_mode 由代码内置",
        "description": (
            "message_mode 只声明启用且 config 为空；neutral/ic/ooc/gm 的"
            "标签和 Prompt 不属于设计数据。"
        ),
        "runtimeEffect": (
            "neutral、ic 与 gm 是非 OOC 正文 turn；OOC 不推进 Plot、Status、"
            "Scene 或 Memory 事实，命令也不属于正文 turn。"
        ),
    },
    {
        "ruleId": "principle.plot-scene-opportunity",
        "domain": "plot",
        "title": "Scene 净变化产生一次自动调度机会",
        "description": (
            "自动 selector 不按每个 turn 运行。只有成功提交 turn 后整个 active"
            " Scene document 的最终内容发生净变化，才为下一次非 OOC turn"
            " 留下一次机会；变化覆盖时间、位置、在场人物、其他字段及获准的"
            " key 结构变化。不要用无事实变化的 Scene 写入轮询事件。"
        ),
        "runtimeEffect": (
            "下一次 neutral、ic 或 gm turn 在 StatusPreflight 后使用最新 scratch"
            " Scene 消费机会，最多选择一个大纲节点和一个池事件；消费 turn 若"
            "再次改变 Scene，则为再下一轮留下新机会。OOC、命令、Plot 模块"
            "禁用、失败或取消既不消费也不创建机会；无机会时不运行 selector"
            " 或 soft judge。"
        ),
    },
    {
        "ruleId": "principle.plot-outline-binding-isolates-pool-lane",
        "domain": "plot",
        "title": "大纲绑定事件不占事件池调度",
        "description": (
            "只要剧情事件仍被任意大纲节点引用，就永久从自动 pool lane 候选中"
            "排除，不受大纲、节点或 Session 覆盖当前是否启用影响。删除该事件"
            "的全部节点引用后，它才重新成为池内候选。"
        ),
        "runtimeEffect": (
            "大纲 lane 仍按自身节点独立调度；结构绑定避免同一事件同时消耗大纲"
            "和事件池额度。Session 手动标记仍可绕过该结构隔离。"
        ),
    },
    {
        "ruleId": "principle.plot-stable-weighted-rerank",
        "domain": "plot",
        "title": "事件池使用稳定加权召回与单次重排",
        "description": (
            "自动 pool lane 先在通过确定性资格规则的池之间按 selectionWeight"
            " 稳定加权选池。random 池再按事件 selectionWeight 抽取主候选；"
            "soft 主候选可按 candidateBatchSize 加权无放回补充 soft 候选，并"
            "通过一次 Judge 选择当前最适合的一项。池权重表达选池概率，事件"
            "权重只表达进入候选批次的召回概率，都不提供有限轮次保底。"
        ),
        "runtimeEffect": (
            "相同 Session、turn、定义和决策快照得到相同选择。forced 主候选"
            "直接注入且不构造批次；sequential 池忽略事件权重和批次大小。"
            "未被重排选中的候选不写决策、不启动 retry 或冷却，最终仍最多注入"
            "一个 pool directive。"
        ),
    },
    {
        "ruleId": "principle.plot-pool-cooldown",
        "domain": "plot",
        "title": "事件池共享自动注入冷却",
        "description": (
            "cooldownMinutes 是非负 SceneTime 分钟。池内任意事件最近一次由自动"
            " scheduler 在 pool lane 成功注入后，只要 elapsed 小于当前池配置，"
            "整个池都不参与候选；elapsed 大于或等于配置时恢复。高强度巧合还应"
            "只在已有关系、信息或利益张力时通过 suitabilityHint 表达适宜性。"
        ),
        "runtimeEffect": (
            "冷却锚点只认 sourceKind=pool、selectionOrigin=scheduler、"
            "decisionStatus=triggered 的已提交决策及其 containerId。手动注入、"
            "大纲注入、deferred 和 error 均不启动、刷新或清除池级冷却。"
        ),
    },
    {
        "ruleId": "principle.plot-manual-snapshot-runtime-only",
        "domain": "plot",
        "title": "手动下一轮标记是 Session 临时快照",
        "description": (
            "`plot_event_mark_next` 只在 OOC/GM 运行时把现有事件冻结为"
            " Session 一次性快照；可临时覆盖 title/directive，省略时保留原"
            "内容，event_id=null 清空。该快照及工具参数不是 Story Design 或"
            " Story Pack 字段，也不修改原事件。"
        ),
        "runtimeEffect": (
            "快照在下一次 neutral、ic 或 gm turn 强制注入，忽略 Scene 调度"
            "机会、SceneTime、enabled、时间窗、大纲绑定、重复和冷却等全部"
            "自动规则；即使无 SceneTime 也可触发并解除该事件已有的事件级冷却"
            "锚点，但不会启动、刷新或清除事件池级冷却锚点。"
        ),
    },
    {
        "ruleId": "principle.plot-trigger-not-resolution",
        "domain": "plot",
        "title": "节点触发不等于章节完成",
        "description": (
            "Plot 的 triggered 只表示事件或大纲节点已被选择并把 directive"
            " 注入当前请求，不代表模型已落实，也不代表玩家完成、跳过或解决"
            "了章节。"
        ),
        "runtimeEffect": (
            "当前 Plot ledger 记录 selected-and-injected 的 triggered，不提供"
            "语义验收或章节完成生命周期。"
        ),
    },
)


_DIAGNOSTIC_RULES: tuple[dict[str, Any], ...] = (
    {
        "ruleId": "package.story-title-required",
        "domain": "package",
        "severity": "error",
        "profiles": ["package"],
        "pathPattern": "/story/title",
        "message": "构建 Story Pack 前必须填写 story.title。",
        "suggestion": "填写面向玩家和管理界面的 Story 标题。",
        "runtimeEffect": "运行时 Story 创建和匹配需要非空标题。",
    },
    {
        "ruleId": "package.workspace-required",
        "domain": "package",
        "severity": "error",
        "profiles": ["package"],
        "pathPattern": "/target/workspaceId",
        "message": "构建 Story Pack 前必须确定 target.workspaceId。",
        "suggestion": "在设计目标或 build override 中提供 Workspace ID。",
        "runtimeEffect": "所有 Story 资源写入都必须有明确 Workspace 归属。",
    },
    {
        "ruleId": "package.workspace-name-required",
        "domain": "package",
        "severity": "error",
        "profiles": ["package"],
        "pathPattern": "/target/workspaceName",
        "message": "允许创建 Workspace 时必须填写 workspaceName。",
        "suggestion": "填写新 Workspace 的显示名，或关闭 allowCreateWorkspace。",
        "runtimeEffect": "创建 Workspace 需要明确显示名。",
    },
    {
        "ruleId": "package.workspace-root-required",
        "domain": "package",
        "severity": "error",
        "profiles": ["package"],
        "pathPattern": "/target/workspaceRoot",
        "message": "允许创建 Workspace 时必须填写安全相对 workspaceRoot。",
        "suggestion": "例如填写 data/my_world，或关闭 allowCreateWorkspace。",
        "runtimeEffect": "Workspace 运行目录必须可移植且不得逃逸数据根目录。",
    },
    {
        "ruleId": "quality.story-title-empty",
        "domain": "story",
        "severity": "warning",
        "profiles": ["draft"],
        "pathPattern": "/story/title",
        "message": "Story 标题仍为空，当前适合脑暴但尚不可构建。",
        "suggestion": "在核心前提稳定后补充简短标题。",
        "runtimeEffect": "空标题不会进入可导入 Story Pack。",
    },
    {
        "ruleId": "quality.target-unset",
        "domain": "project",
        "severity": "warning",
        "profiles": ["draft"],
        "pathPattern": "/target/workspaceId",
        "message": "尚未设置运行时 Workspace 目标。",
        "suggestion": "可以继续设计；准备构建时再填写 target 或 build override。",
        "runtimeEffect": "目标为空时不能生成可导入 Story Pack。",
    },
    {
        "ruleId": "quality.opening-missing",
        "domain": "story",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/openings",
        "message": "当前没有 Opening。",
        "suggestion": "若希望新 Session 有作者编写的开场，请添加 1–3 条 Opening。",
        "runtimeEffect": "新 Session 绑定角色后不会追加作者 Opening。",
    },
    {
        "ruleId": "quality.story-prompt-empty",
        "domain": "story",
        "severity": "warning",
        "profiles": ["package"],
        "pathPattern": "/story/storyPrompt",
        "message": "Story Prompt 为空，运行时只能依赖系统通用规则。",
        "suggestion": "补充本故事固定且跨 turn 稳定的叙事约束。",
        "runtimeEffect": "Story 固定层缺少本故事专属指令。",
    },
    {
        "ruleId": "workflow.open-question-unresolved",
        "domain": "workflow",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/openQuestions/*",
        "message": "设计中仍有未解决的开放问题。",
        "suggestion": "决策后更新设计字段，并把问题标记为 resolved。",
        "runtimeEffect": "开放问题不会自动阻止导入，但可能造成设计含义不完整。",
    },
    {
        "ruleId": "quality.story-summary-too-long",
        "domain": "story",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/story/summary",
        "message": "story.summary 过长，可能混入了 Prompt 或场景正文。",
        "suggestion": "压缩为约 240 字以内的管理摘要，细节移到对应资源。",
        "runtimeEffect": "摘要用于管理展示，不应承担固定 Prompt 职责。",
    },
    {
        "ruleId": "character.description-portrayal-leak",
        "domain": "character",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/characters/*/description",
        "message": "角色 description 疑似包含性格、说话、行为或心理演绎。",
        "suggestion": "description 只保留身份/经历/客观事实；演绎内容拆到带 kind 标签的 details。",
        "runtimeEffect": "description 会进入玩家角色 Fixed Layer，混入演绎会错误约束玩家。",
    },
    {
        "ruleId": "character.detail-mixed-kinds",
        "domain": "character",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/characters/*/details/*/tags",
        "message": "同一角色 detail 同时包含客观 kind 与演绎 kind。",
        "suggestion": "拆成两条 detail；整条演绎 detail 会按 npc_portrayal 过滤。",
        "runtimeEffect": "混写会导致客观事实随演绎 scope 一起从玩家 Fixed Layer 被过滤。",
    },
    {
        "ruleId": "character.detail-kind-missing",
        "domain": "character",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/characters/*/details/*/tags",
        "message": "角色 detail 没有主要 kind 标签。",
        "suggestion": "选择一个 objective 或 portrayal kind；自定义普通标签可额外保留。",
        "runtimeEffect": "没有 kind 时无法稳定判断玩家/NPC演绎过滤职责。",
    },
    {
        "ruleId": "status.update-rule-scheduling",
        "domain": "status",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/statusTables/*/rows/*/updateRule",
        "message": "updateRule 疑似包含频率、延迟、定时或读写权限语义。",
        "suggestion": (
            "改写为当前非 OOC 正文 turn 的事实判定条件；删除每 N 回合、延迟、"
            "manual/read-only 等内容，也不要用无事实变化的 Scene 写入轮询 Plot。"
        ),
        "runtimeEffect": "运行时不会执行这些调度或权限语义，保留会误导状态 Agent。",
    },
    {
        "ruleId": "status.scene-placeholder-year",
        "domain": "status",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/statusTables/*/rows/*/value",
        "message": "Scene 时间使用了疑似占位年份。",
        "suggestion": "若故事已锚定现实年代，使用 2019 年、2020 年等虚拟年份。",
        "runtimeEffect": (
            "仅当已有 Scene 调度机会时，Plot Scheduler 才按 SceneTime 判断"
            "自动候选资格。"
        ),
    },
    {
        "ruleId": "plot.soft-event-hint-empty",
        "domain": "plot",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/plotSchedule/events/*/suitabilityHint",
        "message": "soft 事件没有 suitabilityHint。",
        "suggestion": "补充适合开始的阶段、地点、在场人物、前置事实与安全边界。",
        "runtimeEffect": (
            "有 Scene 调度机会且事件进入自动 soft 候选后，judge 只能依赖"
            "通用 Context，事件更容易在不合适时机触发。"
        ),
    },
    {
        "ruleId": "plot.forced-event-unused-hint",
        "domain": "plot",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/plotSchedule/events/*/suitabilityHint",
        "message": "forced 事件填写了 suitabilityHint，但自动 forced 候选不会等待 soft 判断。",
        "suggestion": "若条件必须被判断，改用 soft；否则把必要内容移入 directive 或管理说明。",
        "runtimeEffect": (
            "有 Scene 调度机会且满足 SceneTime 窗口后，自动 forced 候选"
            "跳过 soft judge 直接注入；时间字段本身不会唤醒 selector。"
        ),
    },
    {
        "ruleId": "plot.event-description-empty",
        "domain": "plot",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/plotSchedule/events/*/description",
        "message": "剧情事件缺少管理摘要 description。",
        "suggestion": "用一两句话说明事件是什么及其设计用途，不重复 directive。",
        "runtimeEffect": "不影响注入，但会降低作者预览和维护可读性。",
    },
    {
        "ruleId": "plot.directive-controls-player",
        "domain": "plot",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/plotSchedule/events/*/directive",
        "message": "剧情 directive 疑似替玩家决定行动、同意或结果。",
        "suggestion": "只控制世界与 NPC，给出有意义选择，并把后果留到玩家行动后确认。",
        "runtimeEffect": "directive 会被主 Agent 当作必须落实的指令。",
    },
    {
        "ruleId": "lorebook.content-empty",
        "domain": "lorebook",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/lorebook/*/content",
        "message": "世界书条目只有名称/摘要，没有可供 Agent 使用的 content。",
        "suggestion": "补充稳定的世界事实、规则或关系；纯视觉内容可改放 visualCatalog。",
        "runtimeEffect": "空 content 无法为运行时 Context 提供世界知识。",
    },
    {
        "ruleId": "composer.style-prompt-empty",
        "domain": "composer",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/narrativeStyles/*/prompt",
        "message": "叙事风格没有 Prompt。",
        "suggestion": "填写可稳定复用的写作约束，或移除无效风格。",
        "runtimeEffect": "空风格不会提供可观察的叙事约束。",
    },
    {
        "ruleId": "visual.anchors-empty",
        "domain": "visual",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/visualCatalog/*/visualAnchors",
        "message": "视觉规格没有稳定 visualAnchors。",
        "suggestion": "列出跨立绘/场景变体应保持不变的身份、形制或辨识特征。",
        "runtimeEffect": "归档仍有效，但后续多图一致性会降低。",
    },
    {
        "ruleId": "visual.subject-ref-unresolved",
        "domain": "visual",
        "severity": "warning",
        "profiles": ["draft", "package"],
        "pathPattern": "/resources/visualCatalog/*/subjectRefs/*",
        "message": "visual subjectRef 在当前 Story 中找不到对应 stableId。",
        "suggestion": "修正 stableId，或在 metadata 中记录非资源概念而不要伪造引用。",
        "runtimeEffect": "视觉规格只归档，但无法可靠关联 Story 资源。",
    },
)


_REFERENCE_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "path": "fields-project-story.md",
        "title": "项目、Story 与 Opening 字段",
        "domains": ["project", "story", "package"],
    },
    {
        "path": "fields-characters-lorebook.md",
        "title": "角色与世界书字段",
        "domains": ["character", "lorebook"],
    },
    {
        "path": "fields-status-scene.md",
        "title": "状态表与 Scene 字段",
        "domains": ["status"],
    },
    {
        "path": "fields-plot-rp-composer.md",
        "title": "剧情调度、RP Module 与 Composer 字段",
        "domains": ["plot", "rp-module", "composer"],
    },
    {
        "path": "fields-visual-workflow.md",
        "title": "视觉目录、来源与设计工作流字段",
        "domains": ["visual", "workflow"],
    },
)


def normalize_authoring_profile(value: str) -> AuthoringProfile:
    normalized = str(value or "draft").strip().lower()
    if normalized not in {"draft", "package"}:
        raise ValueError("profile must be 'draft' or 'package'")
    return normalized  # type: ignore[return-value]


def authoring_rules_catalog() -> dict[str, Any]:
    """Return the complete, portable authoring rules catalog."""

    design_schema = StoryDesignDocument.model_json_schema(
        by_alias=True,
        mode="validation",
    )
    pack_schema = StoryPack.model_json_schema(
        by_alias=True,
        mode="validation",
    )
    fields = _build_field_rules(
        {
            "StoryDesignDocument": design_schema,
            "StoryPack": pack_schema,
        }
    )
    catalog: dict[str, Any] = {
        "schemaVersion": AUTHORING_RULES_SCHEMA_VERSION,
        "authoringRulesVersion": AUTHORING_RULES_VERSION,
        "compatibleContracts": {
            "storyDesign": "story-design/2.0",
            "storyPack": "rpg-story-pack/2.0",
            "designProject": "story-design-project/2.0",
            "mcp": "2.0",
        },
        "profiles": {
            "draft": (
                "结构必须有效；未完成项、字段职责和创作质量问题以 warning "
                "提示，允许继续迭代。"
            ),
            "package": (
                "除结构有效外，还要求 Story 标题和运行时目标可构建；创作质量"
                "问题继续以 warning 提示。"
            ),
        },
        "domains": [
            {
                "id": domain,
                "runtimeEffect": effect,
            }
            for domain, effect in _RUNTIME_EFFECTS.items()
        ],
        "principles": [copy.deepcopy(item) for item in _PRINCIPLES],
        "fields": fields,
        "diagnosticRules": [
            copy.deepcopy(item) for item in _DIAGNOSTIC_RULES
        ],
        "referenceGroups": [
            copy.deepcopy(item) for item in _REFERENCE_GROUPS
        ],
    }
    catalog["catalogDigest"] = digest_json(catalog)
    return catalog


def filter_authoring_rules(
    *,
    domain: str | None = None,
    rule_id: str | None = None,
) -> dict[str, Any]:
    catalog = authoring_rules_catalog()
    normalized_domain = str(domain or "").strip()
    normalized_rule_id = str(rule_id or "").strip()
    known_domains = {
        str(item["id"]) for item in catalog["domains"]
    }
    if normalized_domain and normalized_domain not in known_domains:
        raise ValueError(
            "unknown authoring rule domain: "
            f"{normalized_domain}; expected one of {sorted(known_domains)}"
        )
    known_rule_ids = {
        str(item["ruleId"])
        for group in ("principles", "fields", "diagnosticRules")
        for item in catalog[group]
    }
    if normalized_rule_id and normalized_rule_id not in known_rule_ids:
        raise ValueError(
            f"unknown authoring rule id: {normalized_rule_id}"
        )

    def include(item: Mapping[str, Any]) -> bool:
        if normalized_domain and item.get("domain") != normalized_domain:
            return False
        return not (
            normalized_rule_id
            and item.get("ruleId") != normalized_rule_id
        )

    catalog["principles"] = [
        item for item in catalog["principles"] if include(item)
    ]
    catalog["fields"] = [
        item for item in catalog["fields"] if include(item)
    ]
    catalog["diagnosticRules"] = [
        item for item in catalog["diagnosticRules"] if include(item)
    ]
    catalog["filters"] = {
        "domain": normalized_domain or None,
        "ruleId": normalized_rule_id or None,
    }
    return catalog


def enrich_schema(
    schema: Mapping[str, Any],
    *,
    root_model: str,
    catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach catalog descriptions/examples to every Schema field."""

    output = copy.deepcopy(dict(schema))
    rules = catalog or authoring_rules_catalog()
    field_rules = {
        (str(item["model"]), str(item["field"])): item
        for item in rules["fields"]
    }
    _enrich_schema_object(output, root_model, field_rules)
    for model, definition in output.get("$defs", {}).items():
        if isinstance(definition, dict) and definition.get("properties"):
            _enrich_schema_object(definition, model, field_rules)
    output["x-authoringRulesVersion"] = AUTHORING_RULES_VERSION
    output["x-authoringRulesDigest"] = rules["catalogDigest"]
    return output


def render_reference_files(
    catalog: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    rules = catalog or authoring_rules_catalog()
    result: dict[str, str] = {}
    for group in rules["referenceGroups"]:
        domains = set(group["domains"])
        principles = [
            item for item in rules["principles"]
            if item["domain"] in domains
        ]
        fields = [
            item for item in rules["fields"]
            if item["domain"] in domains
        ]
        diagnostics = [
            item for item in rules["diagnosticRules"]
            if item["domain"] in domains
        ]
        lines = [
            f"# {group['title']}",
            "",
            (
                f"> authoringRulesVersion={rules['authoringRulesVersion']} · "
                f"catalogDigest={rules['catalogDigest']}"
            ),
            "",
            "本文由 RPG World 字段语义单一真源生成；不要手工修改。",
            "",
        ]
        if principles:
            lines.extend(["## 跨字段原则", ""])
            for item in principles:
                lines.extend([
                    f"### {item['title']}",
                    "",
                    item["description"],
                    "",
                    f"运行时影响：{item['runtimeEffect']}",
                    "",
                ])
        lines.extend([
            "## 字段规则",
            "",
            "| 对象 | 路径 | 应填写 | 避免 | 运行时影响 |",
            "| --- | --- | --- | --- | --- |",
        ])
        for item in fields:
            lines.append(
                "| "
                + " | ".join([
                    f"`{item['model']}`",
                    f"`{_markdown_cell(item['pathPattern'])}`",
                    _markdown_cell(item["description"]),
                    _markdown_cell(item["avoid"]),
                    _markdown_cell(item["runtimeEffect"]),
                ])
                + " |"
            )
        if diagnostics:
            lines.extend([
                "",
                "## 自动诊断",
                "",
                "| Rule ID | 级别 | 触发含义 | 修正建议 |",
                "| --- | --- | --- | --- |",
            ])
            for item in diagnostics:
                lines.append(
                    "| "
                    + " | ".join([
                        f"`{item['ruleId']}`",
                        item["severity"],
                        _markdown_cell(item["message"]),
                        _markdown_cell(item["suggestion"]),
                    ])
                    + " |"
                )
        result[str(group["path"])] = "\n".join(lines).rstrip() + "\n"
    return result


def render_skill_document(
    catalog: Mapping[str, Any] | None = None,
) -> str:
    rules = catalog or authoring_rules_catalog()
    digest = rules["catalogDigest"]
    return f"""---
name: rpg-story-authoring
description: Persist, resume, revise, inspect, validate, and package a portable RPG Story design, including story architecture, characters, lorebook entries, status tables, openings, composer settings, plot schedules, and image-worthy visual specifications. Use for story brainstorming or decisions, continuing after context compression or a new session, interpreting field semantics or diagnostics, opening the live read-only revision/schema/field-guide/Story Pack viewer, creating checkpoints, building full or section-scoped Story Packs, comparing a design with RPG World, and previewing or applying an explicitly confirmed runtime synchronization.
---

# RPG Story Authoring

<!-- authoring-rules-version: {rules['authoringRulesVersion']} -->
<!-- authoring-rules-digest: {digest} -->

Persist the Story design as immutable local revisions and use
`rpg-world-mcp` as the only runtime boundary. Never rely on conversation
history as the durable design source.

## Start or resume

1. Call `story_design_get_resume_context` before discussing or changing the
   design.
2. Summarize the current revision, confirmed decisions, unresolved questions,
   and the next useful decision.
3. Call `story_design_get_authoring_rules` when a field's meaning or runtime
   effect is uncertain. Do not infer semantics from its name alone.
4. If the MCP tool is unavailable, stop before editing design state and run
   `scripts/portable_doctor.py` only for read-only diagnosis.

## Discuss and persist

Offer concrete options for consequential, unresolved choices. Do not invent a
confirmation. Once the user confirms a choice:

1. Prepare one minimal JSON Patch containing the design changes.
2. Append or supersede a concise record in `/decisions`.
3. Resolve the corresponding `/openQuestions` item if present.
4. Call `story_design_patch` with the current revision as `expectedHead` and a
   specific reason.
5. Read `advisoryDiagnostics`; correct field-duty warnings or explain a
   deliberate exception.
6. Treat a stale-head response as a CAS conflict: reload resume context,
   rebase the intended change, and never overwrite the newer head.

Save confirmed decisions during the turn, not only at the end. Keep tentative
ideas as open questions or notes; do not label them confirmed. Read
`references/authoring-workflow.md` for patch examples and milestone rules.

## Model the Story

Keep one Story in the project. Character, lorebook, and status resources are
Story-owned. Include image-worthy material in both the relevant resource's
`visual` field and `/resources/visualCatalog` when it deserves an independent
generation brief. Use Story virtual calendar years such as 2019 or 2020 when
the fiction is anchored to those years; do not replace them with placeholder
year 1.

Treat `neutral | ic | gm` as non-OOC body turns; OOC and commands do not
advance world facts. Do not model automatic Plot selection as a per-turn
poll. A successfully committed net change to the entire active Scene document
creates one opportunity for the next non-OOC turn; `scheduledTime` and
`deadlineTime` only gate candidates inside that opportunity. Do not author
no-op Scene changes to poll Plot.

In an existing normal Session status table, neutral/ic/gm turns may create,
read, update, rename, and delete fields, but never CRUD the table itself.
`runtimeKeyLocked=true` blocks only rename/delete of that field; value updates
and creation of other fields remain allowed. OOC and commands are read-only,
and Scene structure still follows `agent.scene.allow_runtime_key_changes`.
When a normal table needs open-ended fields, use its `description` to define
the dynamic key domain, naming/value format, and create/rename/delete
conditions instead of predefining every possible field.

An event referenced by any outline node is exclusive to the outline lane and
does not consume pool-lane selection until every node reference is removed.
`cooldownMinutes` pauses the whole pool after any scheduler-origin pool event
is successfully injected; manual and outline injections do not change that
pool-level anchor.

Available pools use positive `selectionWeight` values as a stable probability
distribution, not strict priority or a finite-turn guarantee. A random pool
uses event `selectionWeight` for weighted recall. When its weighted primary is
soft, `candidateBatchSize` (default 3, maximum 5) recalls a small soft batch
for one suitability rerank; event weight is recall probability, not a promise
about final injection frequency. Sequential pools ignore event weight and
batch size. A forced weighted primary still injects directly.

Keep `plot_event_mark_next` state out of Story Design and Story Pack fields.
It is an OOC/GM Session runtime snapshot for the next non-OOC turn, may
temporarily override `title` and `directive`, and ignores all automatic
eligibility rules without changing the source event or pool-level cooldown.

Read the relevant generated field reference before adding or substantially
rewriting that domain:

- Project, Story, Opening, target, or Story Pack:
  `references/fields-project-story.md`
- Character or Lorebook:
  `references/fields-characters-lorebook.md`
- Status or Scene:
  `references/fields-status-scene.md`
- Plot, RP Module, Narrative Style, or Quick Reply:
  `references/fields-plot-rp-composer.md`
- Visual Catalog, sources, decisions, or open questions:
  `references/fields-visual-workflow.md`

Use `references/story-design-contract.md` for ownership and cross-resource
invariants. Do not copy the whole field catalog into the active context when
only one domain is needed.

## Validate and checkpoint

Call `story_design_validate(profile="draft")` while iterating. Before a
milestone or package build, use `profile="package"` and resolve every error;
warnings identify field-duty or quality risks and do not silently become
errors. Package builds always run the package profile again.

Create a named checkpoint after a stable architecture, resource set, or
import-ready state. Checkpoints do not replace automatic revisions. Use
`story_design_diff_revisions` before restoring a revision, and restore with
`story_design_restore_revision`; never alter or delete an old revision file.

## Run the read-only viewer

When the user asks to start, open, or inspect the Story visualization,
revision history, field guide, diagnostics, Schema, or built Story Packs:

1. Treat the current workspace as the DesignProject root and require
   `viewer/serve.py`. Do not copy the viewer elsewhere or import RPG modules.
2. If `http://127.0.0.1:8787/api/project` already returns this project's
   `projectId` and `headDigest`, reuse it. If the port is occupied by another
   process or project, do not stop it; start with `--port 0` and use the URL
   printed by the server.
3. Otherwise start a retained process from the project root with
   `python3 viewer/serve.py --port 8787`. Add `--open` only when the user asks
   to open the browser and GUI launch is permitted.
4. Verify `/api/project` reports the current revision, keep the process
   running, and return the exact loopback URL.
5. For stop or restart requests, target only the exact retained Viewer
   process; never terminate an unknown listener.

A Viewer-only request is operational and read-only; do not call mutation tools
merely to start it. Viewer failures never authorize direct edits to MCP-owned
design state or Story Packs.

## Build and synchronize

Build a full Story Pack by default. For small reviewable packages, pass only
the required sections to `story_design_build_pack`; every pack remains
merge-only and contains one Story. A status-only pack may refer to a Character
from an earlier pack, but runtime preview must confirm that stable binding.

For runtime work:

1. Validate the pack.
2. Call a preview tool and show conflicts, creates, updates, unchanged
   resources, warnings, and the opaque operation id.
3. Wait for explicit user confirmation.
4. Call the corresponding apply tool with the operation id. Do not add a
   `confirmed` input or switch to a different apply lane.
5. If the result is `applied_with_local_sync_pending`, retry the same apply
   operation after fixing the project path; do not repeat the database write.

Read `references/mcp-delivery.md` for modes, local Inspector transport,
ChatGPT Secure MCP Tunnel, relocation, rule-asset refresh, and recovery.

## Boundaries

- Do not write raw conversation transcripts.
- Do not directly edit MCP-owned revision files.
- Do not access RPG SQLite or import an `rpg_*` module from this workspace.
- Do not create Session, messages, media jobs, image binaries, or TTS jobs
  from a Story Pack.
- Do not delete runtime resources merely because a small pack omits them.
"""


def render_contract_reference(
    catalog: Mapping[str, Any] | None = None,
) -> str:
    rules = catalog or authoring_rules_catalog()
    return f"""# Story design contract

> authoringRulesVersion={rules['authoringRulesVersion']} ·
> catalogDigest={rules['catalogDigest']}

## Contract and ownership

- Support only `story-design/2.0`, `rpg-story-pack/2.0`,
  `story-design-project/2.0`, and MCP `contractVersion=2.0`.
- Keep one Story per DesignProject and one Story per Story Pack.
- Own Character, Lorebook, Status, Opening, Quick Reply, RP Module, Plot, and
  Visual Catalog resources directly from the Story. Narrative Style remains
  Workspace-owned and Story-bound because that is the runtime contract.
- Keep every stable ID durable across revision, section-scoped packs, and
  runtime synchronization. Character-detail and plot-node IDs are unique
  across the whole Story.

## Authoring rule source

The complete machine-readable catalog is
`schemas/story-authoring-rules-v1.json`. It supplies every Schema field
description/example, MCP diagnostics, the Viewer field guide, and these
domain references:

- `fields-project-story.md`
- `fields-characters-lorebook.md`
- `fields-status-scene.md`
- `fields-plot-rp-composer.md`
- `fields-visual-workflow.md`

Use the relevant domain reference instead of reinterpreting a field from its
name. The `authoringRulesVersion` evolves independently from Story Pack
`contractVersion`; adding or clarifying author guidance does not by itself
change the import contract.

## Cross-resource invariants

- Character `description` contains only objective identity/history. Put
  personality, speech, behavior, and psychology in tagged details; portrayal
  details carry `scope:npc_portrayal` and are filtered by player/NPC/GM turn.
- Scene tables contain `时间`, `位置`, and `在场人物`. Use parseable virtual
  time such as `2020 年 7 月 18 日 9 时`.
- Status table `description` contains table-wide semantics, value formats,
  and shared immediate-update rules. For open-ended normal tables it also
  defines the dynamic key domain, naming/value format, and
  create/rename/delete conditions; authors need not enumerate every future
  field.
- Status rows contain only `key`, `value`, `runtimeKeyLocked`, `updateRule`,
  and `metadata`. `value` is a string that may express a number, enum, list,
  short description, or current fact state. A row `updateRule` contains only
  field-specific immediate conditions and does not assume a numeric model.
- In an existing normal Session table, neutral/ic/gm turns may create, read,
  update, rename, and delete fields but not CRUD the table. OOC and commands
  are read-only. `runtimeKeyLocked=true` blocks only rename/delete of that
  field, not value updates or creation of other fields. Scene structure keeps
  its separate `agent.scene.allow_runtime_key_changes` policy.
- Status tables hold current state that needs per-turn visibility and updates.
  Memory is better suited to time-ordered narrative history, but current
  facts, commitments, contacts, or event states may still be status rows.
- `message_mode` is code-owned, uses `neutral | ic | ooc | gm`, and has empty
  Story config. OOC does not advance world facts.
- Plot event `description`, `suitabilityHint`, and `directive` have separate
  duties. An outline node trigger does not mean chapter completion.
- Visual Catalog is archive-only. A Story Pack never creates media binaries,
  jobs, messages, or message metadata.
- Source records are references only. Re-select, author, and confirm content
  into the current revision before it can enter a Story Pack.

## Turn and Plot scheduling

- Treat `neutral | ic | gm` as non-OOC body turns. OOC and commands do not
  advance world facts.
- Do not run the automatic Plot selector on every turn. Only a successfully
  committed net change to the active Scene document creates one scheduling
  opportunity for the next non-OOC turn. Scene change covers time, location,
  present characters, every other field, and permitted key-structure changes.
- Consume that opportunity after `StatusPreflight` using the latest scratch
  Scene. Select at most one outline node and one pool event, without injecting
  the same event twice. If the consuming turn changes Scene again, create a
  new opportunity for the following non-OOC turn.
- OOC, commands, disabled Plot scheduling, failed turns, and cancelled turns
  neither consume nor create an opportunity. Without an opportunity, do not
  run the automatic selector or soft judge. Do not use no-op Scene writes to
  poll Plot.
- Treat `scheduledTime` and `deadlineTime` only as automatic eligibility gates
  inside an existing opportunity, never as timers. A `forced` automatic
  candidate still requires an opportunity and its SceneTime window; it only
  skips the soft judge.
- Exclude an event from the automatic pool lane whenever any outline node
  references it, regardless of current outline/node enablement or Session
  overrides. Removing all such references returns it to pool eligibility.
- Apply `cooldownMinutes` to the whole pool from its latest committed
  scheduler-origin, triggered pool decision. Any pool event starts the same
  cooldown; manual, outline, deferred, and error decisions neither start nor
  clear it. The current pool setting applies to an existing anchor.
- Select among deterministically eligible pools by positive
  `selectionWeight` with a stable Session/turn seed. In a random pool, use
  event `selectionWeight` for weighted recall. A soft primary may recall up to
  `candidateBatchSize` soft events (default 3, maximum 5) for one suitability
  rerank; only the selected event produces a decision. Sequential pools
  ignore event weight and batch size, and a forced primary bypasses rerank.
  Weights are probability controls, not finite-turn fairness guarantees.
- Treat Plot `triggered` as selected-and-injected, not as semantic
  verification, completion, or resolution.
- Keep `plot_event_mark_next` outside Story Design and Story Pack schemas. It
  is an OOC/GM Session runtime snapshot for the next non-OOC turn. Temporary
  `title`/`directive` overrides do not change the source event, and
  `event_id=null` clears the snapshot. Manual injection ignores the Scene
  opportunity, SceneTime, enabled state, windows, outline binding, repeat,
  and cooldown rules. It can run without SceneTime and clear an event-level
  cooldown anchor, but never starts, refreshes, or clears a pool-level anchor.

## Story Pack behavior

Valid sections are `story`, `openings`, `characters`, `lorebook`,
`statusTables`, `composer`, `rpModules`, `plotSchedule`, and `visualCatalog`.
Every v2 pack is merge-only with `deleteMissing=false`; omission never grants
deletion authority. Runtime changes always require separate preview and apply
calls after explicit user confirmation.
"""


def evaluate_authoring_diagnostics(
    document: StoryDesignDocument,
    *,
    profile: str = "draft",
) -> list[dict[str, Any]]:
    """Evaluate deterministic authoring errors and advisory warnings."""

    selected_profile = normalize_authoring_profile(profile)
    catalog = authoring_rules_catalog()
    rules = {
        str(item["ruleId"]): item
        for item in catalog["diagnosticRules"]
    }
    diagnostics: list[dict[str, Any]] = []

    def emit(rule_id: str, path: str) -> None:
        rule = rules[rule_id]
        if selected_profile not in rule["profiles"]:
            return
        diagnostics.append({
            "ruleId": rule_id,
            "severity": rule["severity"],
            "path": path,
            "message": rule["message"],
            "suggestion": rule["suggestion"],
            "runtimeEffect": rule["runtimeEffect"],
        })

    if not document.story.title.strip():
        emit(
            (
                "package.story-title-required"
                if selected_profile == "package"
                else "quality.story-title-empty"
            ),
            "/story/title",
        )
    if not document.target.workspace_id:
        emit(
            (
                "package.workspace-required"
                if selected_profile == "package"
                else "quality.target-unset"
            ),
            "/target/workspaceId",
        )
    if document.target.allow_create_workspace:
        if not document.target.workspace_name.strip():
            emit("package.workspace-name-required", "/target/workspaceName")
        if not document.target.workspace_root:
            emit("package.workspace-root-required", "/target/workspaceRoot")
    if not document.resources.openings:
        emit("quality.opening-missing", "/resources/openings")
    if selected_profile == "package" and not document.story.story_prompt.strip():
        emit("quality.story-prompt-empty", "/story/storyPrompt")
    if len(document.story.summary.strip()) > 240:
        emit("quality.story-summary-too-long", "/story/summary")
    for index, question in enumerate(document.open_questions):
        if question.status == "open":
            emit(
                "workflow.open-question-unresolved",
                f"/openQuestions/{index}",
            )

    portrayal_pattern = re.compile(
        r"(性格|口头禅|说话(?:方式|语气|习惯)|行为倾向|"
        r"心理(?:活动|状态)|内心(?:想法|活动)|"
        r"\bpersonality\b|\bspeech pattern\b|\bbehavior tendency\b)",
        re.IGNORECASE,
    )
    for character_index, character in enumerate(
        document.resources.characters
    ):
        base = f"/resources/characters/{character_index}"
        if portrayal_pattern.search(character.description):
            emit(
                "character.description-portrayal-leak",
                f"{base}/description",
            )
        for detail_index, detail in enumerate(character.details):
            tag_set = set(detail.tags)
            has_objective = bool(
                tag_set.intersection(OBJECTIVE_CHARACTER_DETAIL_TAGS)
            )
            has_portrayal = bool(
                tag_set.intersection(PORTRAYAL_CHARACTER_DETAIL_TAGS)
            )
            path = f"{base}/details/{detail_index}/tags"
            if has_objective and has_portrayal:
                emit("character.detail-mixed-kinds", path)
            if detail.content.strip() and not (has_objective or has_portrayal):
                emit("character.detail-kind-missing", path)

    scheduling_pattern = re.compile(
        r"(每.{0,10}(回合|轮|turn|分钟|小时|天)|延迟|延期更新|"
        r"定时|周期|defer(?:red)?|interval|read[\s_-]?only|"
        r"只读|手动更新|manual)",
        re.IGNORECASE,
    )
    for table_index, table in enumerate(document.resources.status_tables):
        for row_index, row in enumerate(table.rows):
            base = (
                f"/resources/statusTables/{table_index}/rows/{row_index}"
            )
            if row.update_rule and scheduling_pattern.search(row.update_rule):
                emit("status.update-rule-scheduling", f"{base}/updateRule")
            if table.status_kind == "scene" and row.key == "时间":
                year_match = re.search(r"(\d+)\s*年", row.value)
                if year_match and int(year_match.group(1)) < 1000:
                    emit("status.scene-placeholder-year", f"{base}/value")

    player_control_pattern = re.compile(
        r"(玩家|用户|player|user).{0,8}"
        r"(已经|必须|决定|选择|答应|拒绝|接受|同意|"
        r"has|must|decides|chooses|agrees|refuses|accepts)",
        re.IGNORECASE,
    )
    for event_index, event in enumerate(
        document.resources.plot_schedule.events
    ):
        base = f"/resources/plotSchedule/events/{event_index}"
        if event.dispatch_mode == "soft" and not event.suitability_hint.strip():
            emit("plot.soft-event-hint-empty", f"{base}/suitabilityHint")
        if event.dispatch_mode == "forced" and event.suitability_hint.strip():
            emit("plot.forced-event-unused-hint", f"{base}/suitabilityHint")
        if not event.description.strip():
            emit("plot.event-description-empty", f"{base}/description")
        directive = re.sub(
            r"(不得|不要|不可|避免)替玩家",
            "",
            event.directive,
        )
        if player_control_pattern.search(directive):
            emit("plot.directive-controls-player", f"{base}/directive")

    for lore_index, entry in enumerate(document.resources.lorebook):
        if not entry.content.strip():
            emit(
                "lorebook.content-empty",
                f"/resources/lorebook/{lore_index}/content",
            )
    for style_index, style in enumerate(
        document.resources.narrative_styles
    ):
        if not style.prompt.strip():
            emit(
                "composer.style-prompt-empty",
                f"/resources/narrativeStyles/{style_index}/prompt",
            )

    known_refs = _known_story_stable_ids(document)
    for visual_index, visual in enumerate(document.resources.visual_catalog):
        base = f"/resources/visualCatalog/{visual_index}"
        if not visual.visual_anchors:
            emit("visual.anchors-empty", f"{base}/visualAnchors")
        for ref_index, reference in enumerate(visual.subject_refs):
            if reference not in known_refs:
                emit(
                    "visual.subject-ref-unresolved",
                    f"{base}/subjectRefs/{ref_index}",
                )
    return sorted(
        diagnostics,
        key=lambda item: (
            0 if item["severity"] == "error" else 1,
            item["path"],
            item["ruleId"],
        ),
    )


def advisory_diagnostics_for_paths(
    diagnostics: Sequence[Mapping[str, Any]],
    affected_paths: Sequence[str],
) -> list[dict[str, Any]]:
    normalized = [
        path.removesuffix("/-")
        for path in affected_paths
        if path
    ]
    if not normalized:
        return []
    return [
        dict(item)
        for item in diagnostics
        if item.get("severity") == "warning"
        and any(
            _paths_overlap(str(item.get("path", "")), path)
            for path in normalized
        )
    ]


def _build_field_rules(
    root_schemas: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rules: list[dict[str, Any]] = []
    for root_model, schema in root_schemas.items():
        _append_schema_field_rules(root_model, schema, seen, rules)
        for model, definition in schema.get("$defs", {}).items():
            if model not in _MODEL_INFO:
                raise ValueError(
                    f"authoring rule model metadata is missing for {model}"
                )
            _append_schema_field_rules(model, definition, seen, rules)
    return sorted(rules, key=lambda item: (item["domain"], item["ruleId"]))


def _append_schema_field_rules(
    model: str,
    schema: Mapping[str, Any],
    seen: set[tuple[str, str]],
    output: list[dict[str, Any]],
) -> None:
    info = _MODEL_INFO.get(model)
    if info is None:
        raise ValueError(f"authoring rule model metadata is missing for {model}")
    for field, property_schema in schema.get("properties", {}).items():
        identity = (model, field)
        if identity in seen:
            continue
        seen.add(identity)
        description = _FIELD_OVERRIDES.get(
            identity,
            _FIELD_DESCRIPTIONS.get(field),
        )
        if not description:
            raise ValueError(
                f"authoring field description is missing for {model}.{field}"
            )
        if identity in _EXAMPLE_OVERRIDES:
            example = copy.deepcopy(_EXAMPLE_OVERRIDES[identity])
        elif field in _EXAMPLES:
            example = copy.deepcopy(_EXAMPLES[field])
        elif "default" in property_schema:
            example = copy.deepcopy(property_schema["default"])
        else:
            raise ValueError(
                f"authoring field example is missing for {model}.{field}"
            )
        avoid = _FIELD_AVOID.get(
            identity,
            "不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。",
        )
        base_path = info["path"]
        path = f"{base_path}/{field}" if base_path else f"/{field}"
        output.append({
            "ruleId": f"field.{info['token']}.{_kebab(field)}",
            "domain": info["domain"],
            "model": model,
            "field": field,
            "pathPattern": path,
            "title": f"{info['title']} · {field}",
            "description": description,
            "avoid": avoid,
            "examples": [copy.deepcopy(example)],
            "runtimeEffect": _RUNTIME_EFFECT_OVERRIDES.get(
                identity,
                _RUNTIME_EFFECTS[info["domain"]],
            ),
        })


def _enrich_schema_object(
    schema: dict[str, Any],
    model: str,
    field_rules: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    info = _MODEL_INFO.get(model)
    if info:
        schema["description"] = info["description"]
    for field, property_schema in schema.get("properties", {}).items():
        rule = field_rules.get((model, field))
        if rule is None:
            raise ValueError(
                f"generated Schema field has no authoring rule: {model}.{field}"
            )
        property_schema["description"] = rule["description"]
        property_schema["examples"] = copy.deepcopy(rule["examples"])
        property_schema["x-authoringRuleId"] = rule["ruleId"]
        property_schema["x-runtimeEffect"] = rule["runtimeEffect"]


def _known_story_stable_ids(document: StoryDesignDocument) -> set[str]:
    resources = document.resources
    ids = {document.story.stable_id}
    for values in (
        resources.openings,
        resources.characters,
        resources.lorebook,
        resources.status_tables,
        resources.narrative_styles,
        resources.quick_replies,
        resources.plot_schedule.pools,
        resources.plot_schedule.events,
        resources.plot_schedule.outlines,
        resources.visual_catalog,
    ):
        ids.update(item.stable_id for item in values)
    for character in resources.characters:
        ids.update(detail.stable_id for detail in character.details)
    for outline in resources.plot_schedule.outlines:
        ids.update(node.stable_id for node in outline.nodes)
    return ids


def _paths_overlap(left: str, right: str) -> bool:
    left = left.rstrip("/") or "/"
    right = right.rstrip("/") or "/"
    return (
        left == right
        or left.startswith(right + "/")
        or right.startswith(left + "/")
    )


def _kebab(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", value).replace("_", "-").lower()


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


__all__ = [
    "AUTHORING_RULES_RELATIVE_PATH",
    "AUTHORING_RULES_SCHEMA_VERSION",
    "AUTHORING_RULES_VERSION",
    "AuthoringProfile",
    "advisory_diagnostics_for_paths",
    "authoring_rules_catalog",
    "enrich_schema",
    "evaluate_authoring_diagnostics",
    "filter_authoring_rules",
    "normalize_authoring_profile",
    "render_contract_reference",
    "render_reference_files",
    "render_skill_document",
]
