# RP Modules MVP 实施计划：模块架构与 Dice 骰子模块

## 目标

在当前架构下实现第一版 RP Modules：它是围绕 RP 业务语义的玩法机制层，不是通用 Skill 体系。MVP 以 `dice` 骰子模块验证完整链路：

- 模块可按配置启停。
- 模块可提供稳定固定层契约、可选动态运行态和工具。
- 模块工具通过现有 `ToolRegistry` 注册和执行。
- 模块命令通过现有 `CommandDispatcher` 暴露给 Play WebUI、CLI、Telegram。
- dice 工具支持掷骰、DC 检定和可测试随机源；MVP 先不做落盘审计。
- 不破坏现有全局短 `session_id`、Play API/Agent Service 边界、结构化上下文、Scene Runtime 和状态表架构。

## 当前架构基线

本计划以当前代码为基线，不再按旧 CSV/旧上下文假设设计。

- Web 主体验是 Play WebUI；Play API 是接入层，只通过 `AgentClient` 调用 Agent Service，不持有 `AgentManager`。
- Agent Service 是唯一持有 `AgentManager` / `RPGGameAgent` / `rp_memory` / llama lazy worker 的进程。
- 会话内链路使用全局短 `session_id`；Play API 通过 catalog session 反查 workspace/story，但传给 Agent Service 的仍只有 `session_id`。
- `RPGContextBuilder.build()` 已支持 `rp_module_sections`，`RPGContext` 已有 `RPModulesLayer` 和 `RPModuleRuntimeSection`。
- `ContextRenderer` 已在 `STATUS_TABLES` 之后、`USER_MESSAGE` 之前渲染 `LayerType.RP_MODULES`。
- `FixedLayerComposer` 已有核心 RP 契约，并支持追加稳定固定层片段。
- `ToolRegistry` 是全局工具注册表，已经拒绝重复工具名。
- `CommandDispatcher` 已支持内置命令和子 Agent 命令；斜杠命令会在 LLM 前被拦截，不进入 history。
- `StatusManager` 是 Agent 面向 session 状态表的薄适配层，底层是 `rpg_data` SQLite `document_json` 真源，不再是 CSV 内容源。
- `StatusManager.list_context_tables()` 已只返回普通状态表，排除 `status_kind="scene"`。
- `当前场景` 是 `status_kind="scene"` 的特殊状态表，由 Scene Runtime 作为 user prefix 注入，不是普通 RP Module。
- session 运行目录必须通过 `CatalogService.get_session_runtime_dir(session_id)` 获取，路径形如 `{workspace_root}/stories/{story_id}/{session_id}`。

## 非目标

- 不做通用 `skills/` 目录、任意 `SKILL.md` 注入或工作区自定义 Python 脚本执行。
- 不做 Dashboard API/WebUI，不恢复旧 router 主入口。
- 不把 Scene Runtime / 当前场景做成 RP Module。
- 不让模块直接写 CSV、直接改 SQLite 原始 JSON 或绕过 `StatusManager` / `rpg_data` service。
- MVP 不实现完整 DND/COC 规则、战斗系统、物品系统、模块市场或模块编辑器。
- MVP 不为 dice 做复杂 WebUI 独立页面；先通过聊天工具调用、斜杠命令和命令列表完成可用闭环。

## 架构原则

### 模块不是主 Prompt

RP 主契约属于核心固定层，不属于可选模块。模块只能补充机制规则和工具策略，不能覆盖：

- 系统提示。
- 角色卡。
- 世界书。
- 状态表。
- 当前场景。
- 已发生历史。
- 玩家输入。

普通回复必须保持沉浸式 RP。除非用户明确要求 OOC 分析，模块不得要求模型展示内部流程、模块名或实现细节。

### 静态契约和动态运行态分离

- 静态契约：模块用途、工具使用策略、叙事原则、禁止项。启用配置不变时稳定，放进 fixed layer 或 fixed layer 的稳定追加片段。
- 动态运行态：战斗回合、临时检定上下文、近期机制状态摘要等会变化的信息。只有确有内容时才进入 `RPModulesLayer`。

Dice MVP 只有静态契约和工具 schema，默认不每轮注入动态运行态。

### user prefix 只留给 Scene Runtime

RP Modules 不进入 user prefix，不写入 history。当前 user message 顺序仍应保持：

```text
user [scene] + 用户输入 + user suffix
```

动态 RP Module layer 是 system message，位置在普通状态表之后、当前 user message 之前。它不能比 `[scene]` 拥有更高优先级。

### 模块状态和状态表分离

- 模块私有状态：缓存、战斗轮次、后续审计等，只服务模块内部机制，存放在 session runtime 目录下。
- 普通状态表：需要被上下文、WebUI 或多个系统消费的结构化事实，走 `StatusManager` / `rpg_data`。
- Scene Runtime：时间、地点、在场人物和短期场景属性，走 `SceneTracker` 和 scene tools。

Dice MVP 不写普通状态表，也先不写模块私有审计；只返回本次工具调用结果。

## MVP 目录设计

新增核心目录建议：

```text
rpg_core/rp_modules/
  __init__.py
  base.py
  models.py
  registry.py
  runtime_store.py
  status_bridge.py

  dice/
    __init__.py
    module.py
    parser.py
    tools.py
    models.py
```

职责：

- `base.py`：定义 `RPModule` 基类和模块运行上下文。
- `models.py`：定义 manifest/config/runtime 的 dataclass；审计模型等到 dice v2 或需要落盘记录时再补。
- `registry.py`：根据 settings 创建启用模块，收集 fixed sections、runtime sections、tools 和 commands。
- `runtime_store.py`：使用 `CatalogService.get_session_runtime_dir(session_id)` 管理模块私有文件。
- `status_bridge.py`：为后续模块提供受控状态表快照和 patch 接口；dice MVP 可只实现只读骨架或延后到 combat/inventory 前。
- `dice/parser.py`：解析骰子表达式。
- `dice/tools.py`：实现 `rp_dice_roll` 和 `rp_dice_check_dc` 的 `BaseTool` 适配。
- `dice/module.py`：组合 dice 的工具、固定层契约和命令。

## RPModule 基类

MVP 接口保持小而稳定，预留后续模块交互 hook：

```python
class RPModule:
    name: str

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        ...

    def get_runtime_sections(self, request: ModuleContextRequest) -> list[RPModuleRuntimeSection]:
        ...

    def get_tools(self) -> list[BaseTool]:
        ...

    def get_commands(self) -> list[ModuleCommand]:
        ...

    def on_module_activated(self, event: ModuleActivationEvent) -> None:
        ...

    def on_module_deactivated(self, event: ModuleActivationEvent) -> None:
        ...

    def on_other_module_activated(self, event: ModuleActivationEvent) -> None:
        ...

    def on_other_module_deactivated(self, event: ModuleActivationEvent) -> None:
        ...

    def on_module_tool_result(self, event: ModuleToolResultEvent) -> None:
        ...
```

MVP 中 dice 的 hook 可以全部 no-op，但 registry 应按稳定顺序调用，避免后续 combat/inventory/relationship 接入时临时改接口。

## Registry 设计

`RPModuleRegistry` 是 session-scoped：每个 `RPGGameAgent` 对应一个全局短 `session_id`，registry 可以持有当前 session 的 runtime store 和模块实例。

Registry 维护：

- `module_name -> RPModule`
- `public_tool_name -> (module_name, internal_tool_name)`
- `command_name -> ModuleCommand`
- `module_name -> list[public_tool_name]`

初始化输入：

- `session_id`
- `world_name`
- `StatusManager | None`
- `SceneTracker | None`
- `settings.rp_module_settings`
- 可注入 RNG factory，方便测试 dice。

核心方法：

- `enabled_modules() -> list[RPModule]`
- `get_fixed_sections() -> list[FixedLayerSection]`
- `get_runtime_sections(request) -> list[RPModuleRuntimeSection]`
- `get_tools() -> list[BaseTool]`
- `get_commands() -> list[ModuleCommand]`
- `module_status(name) -> ModuleStatus`

工具命名规则：

- 注册到 `ToolRegistry` 的名称必须全局唯一，并使用 `rp_<module>_<action>`。
- Dice MVP 公开工具名固定为 `rp_dice_roll`、`rp_dice_check_dc`。
- 不使用 `dice.roll` 这种带点工具名，避免 provider schema 兼容问题。
- 如果模块声明重复 public tool name，Agent 初始化应失败并给出清晰错误。

## 配置设计

RP Modules 是业务配置，放在 `rpg_core/settings.yaml`，不放进 `llm_service/llm.yaml`。

建议配置：

```yaml
base:
  rp_modules:
    enabled: true
    reveal_mechanics_default: concise

    modules:
      dice:
        enabled: true
        allow_auto_checks: true
        default_dc: 12
        max_dice_count: 100
        max_die_sides: 1000

      combat:
        enabled: false
```

实现要求：

- 在 `rpg_core/settings.py` 增加 typed dataclass，例如 `RPModuleSettings`、`DiceModuleSettings`。
- 通过 `settings.rp_module_settings` 访问配置。
- 业务代码不得手写 YAML key 路径。
- `llm.yaml` 只管 LLM provider、模型、上下文窗口、超时等 LLM 配置。

## Dice 模块 MVP

### 表达式范围

第一版只支持可测试、容易解释的标准表达式：

- `d20`
- `1d20`
- `2d6+3`
- `4d6-2`
- `1d100`

建议语法：

```text
expression := [count] "d" sides [("+" | "-") modifier]
count      := 1..max_dice_count, 省略时为 1
sides      := 2..max_die_sides
modifier   := 0..100000
```

暂不支持：

- advantage/disadvantage。
- explode dice。
- keep highest / drop lowest。
- 多段表达式如 `2d6+1d4+3`。
- 通过工具参数传 seed。

这些后续可由 `checks` 或 dice v2 扩展。

### 工具

工具签名：

```python
rp_dice_roll(expression: str, reason: str = "", actor: str = "") -> str
rp_dice_check_dc(expression: str, dc: int, modifier: int = 0, reason: str = "", actor: str = "") -> str
```

返回给 LLM 的文本必须简短、可叙事化，例如：

```text
骰子结果: expression=1d20+2, rolls=[7], modifier=2, total=9, reason=潜行越过甲板, actor=艾拉
```

DC 检定返回：

```text
检定结果: expression=1d20, rolls=[13], modifier=2, total=15, dc=12, outcome=success
```

工具职责：

- 解析表达式。
- 执行随机。
- 计算 total。
- 判断 DC 成功/失败。
- 返回给 LLM 结构清晰的短文本。

LLM 职责：

- 判断何时需要调用工具。
- 把结果转译成沉浸式 RP 叙事。
- 不伪造用户明确要求的掷骰结果。
- 不用骰子替玩家选择行动，只裁定行动后果。

### 随机源与测试

- 对 LLM 暴露的工具 schema 不包含 seed。
- Dice 模块内部支持注入 `random.Random` 或等价 RNG factory。
- 单元测试使用固定 RNG，断言 rolls 和 total。

### 首版不做落盘审计

Dice MVP 先不实现 JSONL 审计，也不为 dice 写 session runtime 文件。原因：

- 首版目标是验证 RP Module、工具注册、上下文固定层和命令链路。
- 骰子结果会自然出现在本轮回复或命令输出里，已足够支撑手动验收。
- 审计会引入 turn id、命令来源、stream/non-stream 一致性和日志展示等额外边界，放到 dice v2 更稳。

后续如果需要可追溯骰子记录，再增加可选审计：

```text
{session_runtime_dir}/rp_modules/dice/rolls.jsonl
```

届时 `session_runtime_dir` 必须通过 `CatalogService.get_session_runtime_dir(session_id)` 获取，不拼 workspace/story 路径。

每条记录可包含：

- `timestamp`
- `session_id`
- `turn_id`
- `source`: `tool` / `command`
- `tool_name`
- `expression`
- `rolls`
- `modifier`
- `total`
- `dc`
- `outcome`
- `actor`
- `reason`
- `rng_id`

审计即使后续实现，也默认不把完整记录注入上下文；专门的骰子面板或 `/rp_module dice` 可再决定是否展示最近若干条。

### Dice 固定层契约

Dice 启用时追加一个稳定 fixed section，内容保持短：

```text
[rp_module_dice]
# 骰子与随机裁定
- 用户明确要求掷骰、检定或随机裁定时，必须调用 rp_dice_roll 或 rp_dice_check_dc，不得口头编造点数。
- 当行动结果明显不确定且会改变剧情走向时，可以建议或主动进行检定。
- 检定前只说明可感知风险或难度，不剧透隐藏信息。
- 检定后把结果转译成自然 RP 叙事；失败应引入代价、复杂化、延迟、暴露或资源消耗，而不是阻断剧情。
- 骰子只裁定行动后果，不替玩家角色选择行动或台词。
[/rp_module_dice]
```

Dice MVP 默认 `get_runtime_sections()` 返回空列表，不产生每轮动态 RP Modules system message。

## Dice 完成后的交互形态

Dice 的主要体验不是让玩家手动输入 `/roll`，而是在普通沉浸式 RP 中，由 Agent 在关键的不确定节点调用工具。`/roll` 和 `/check_dc` 是兜底、调试和玩家明确想手掷时的入口；正常玩法仍是自然语言对话。

适合掷骰的时机：

- 玩家明确要求随机裁定，例如“帮我判定我能不能稳住声音”。
- 行动结果明显不确定，且成功/失败会改变剧情走向。
- 玩家把决定权交给命运，例如“我想赌一次，看他会不会相信我”。
- 即兴情感 RP 中，骰子用于裁定外显表现、时机、误会、代价和 NPC 反应，不用于替玩家决定内心真实感受或强迫玩家角色行动。

不适合掷骰的时机：

- 玩家只是表达情绪、台词或角色意图。
- 结果不重要，直接叙事更流畅。
- 掷骰会替玩家决定“我爱不爱”“我原不原谅”“我要不要说出口”等角色主权选择。
- 结果涉及当前场景事实更新时，仍应通过 Scene Runtime 或状态表工具处理，而不是由 dice 私自改状态。

### 情感即兴 RP 示例

普通表达，不需要掷骰：

```text
玩家：我握着杯子，低声说“其实那天我不是不想来”，然后避开他的视线。
Agent：不调用 dice。直接延续沉浸式叙事，因为玩家在表达角色情绪和台词，没有请求随机裁定，也没有需要机制决定的外部结果。
```

玩家把结果交给不确定性，可以掷骰：

```text
玩家：我想装作没事，从他的追问里抽身离开，但我其实快绷不住了。
Agent 内部：调用 rp_dice_check_dc(expression="1d20+2", dc=13, reason="压住情绪保持镇定", actor="玩家角色")
工具结果：total=9, outcome=failure
Agent 回复：你把杯子放回桌面时动作慢了半拍，指尖碰出一声轻响。你已经尽力让语气平稳，可最后一个字还是轻轻发颤。他没有立刻追问，只是看着你，像终于确认了你一直藏着什么。
```

成功时也不是“通关”，而是改变情感张力：

```text
工具结果：total=17, outcome=success
Agent 回复：你把那阵哽咽压回去，甚至还能若无其事地笑一下。门口的风掀动他的衣角，他像是察觉了什么，却没有抓住证据，只低声说：“你总是这样，把话留一半。”
```

NPC 反应可以被骰子影响，但不替玩家做选择：

```text
玩家：我把那张旧照片递给他，赌他还会心软。
Agent 内部：调用 rp_dice_check_dc(expression="1d20", dc=12, reason="旧照片是否动摇对方态度", actor="对方")
Agent 回复：照片被他接过去的一瞬间，他脸上的冷硬松开了一道细缝。那不是原谅，更像是某个旧伤被碰到后短暂失守。他没有让你靠近，只把照片压在掌心，说：“你为什么现在才拿出来？”
```

这个交互的核心是：骰子给即兴 RP 增加不可预知的分叉和情绪代价，但最终呈现仍是一段自然叙事。玩家不需要频繁手动掷骰，除非玩家明确想把这一刻交给骰子。

## Agent 接入计划

### 初始化

在 `RPGGameAgent._ensure_initialized()` 中：

1. 创建 `RPModuleRegistry(session_id=..., status_mgr=..., scene_tracker=..., settings=...)`。
2. 从 registry 取 fixed sections。
3. 使用 `FixedLayerComposer(self._world_name).with_module_sections(registry.get_fixed_sections()).sections` 构造 `_fixed_sections`。
4. 初始化 provider、sub agents 等现有流程保持不变。

注意：`_refresh_rpg_context()` 负责刷新 character/lorebook/status/scene/memory managers；registry 如果持有这些对象，也需要在 reload 或 session 切换后重建或重新 bind。

### 工具注册

在 `_setup_tool_registry()` 中：

1. 注册现有文件工具。
2. 注册 scene tools。
3. 注册 `rp_module_registry.get_tools()`。
4. 注册 `_extra_tools`。

这样模块工具使用现有 `run_chat_loop(provider, tool_registry, messages)` 流程，不需要改 provider schema 生成方式。

### 上下文构建

在 `_build_transformed_context()` 和 `_build_ctx_for_inspection()` 中向 builder 传入：

```python
rp_module_sections=self._rp_module_registry.get_runtime_sections(...)
```

Dice MVP 返回空列表。后续 combat/inventory 等模块有动态运行态时才返回 `RPModuleRuntimeSection`。

`send` 与 `send_stream` 必须共用同一套 context/runtime section 收集逻辑，避免流式和非流式行为不一致。

### 命令注册

推荐在 `_ensure_initialized()` 中，`CommandDispatcher.register_default_builtins()` 后注册模块命令：

- `/rp_modules`
- `/rp_module`
- `/roll`
- `/check_dc`

命令执行仍走 Agent 内部队列，不进入 LLM，不写入 history。

命令输出必须是短文本，兼容 Telegram 和 CLI。

## Play API / WebUI 接入

MVP 不需要新增 Play API router：

- Play WebUI 已可通过 `/sessions/{session_id}/commands` 获取命令列表。
- Play WebUI 发送 `/roll 1d20+2` 到 `/sessions/{session_id}/turn` 即可触发 Agent 命令。
- 用户自然语言要求掷骰时，Agent 可通过工具调用 dice。
- Play API 仍只用全局短 `session_id` 调 Agent Service。

后续如果要做专门的骰子面板，可再评估新增：

```text
GET /play-api/v1/sessions/{session_id}/rp-modules
GET /play-api/v1/sessions/{session_id}/rp-modules/dice/rolls
POST /play-api/v1/sessions/{session_id}/rp-modules/dice/roll
```

这些端点必须仍通过 Agent Service 或 `rpg_data` 明确边界实现，不能让 Play API 直接持有 `AgentManager`。

## 状态表交互计划

Dice MVP 不写普通状态表，但框架要把边界写清楚。

后续 `StatusBridge` 应基于 `StatusManager` 和 `rpg_data` dataclass，不基于 CSV：

```python
class StatusBridge:
    def read_table(self, table_id: int) -> StatusTableSnapshot:
        ...

    def read_table_by_name(self, name: str, status_kind: str = "normal") -> StatusTableSnapshot:
        ...

    def propose_patch(self, module_name: str, table_ref: StatusTableRef, operations: list[StatusPatchOperation], reason: str) -> StatusPatch:
        ...

    def apply_patch(self, patch: StatusPatch) -> StatusPatchResult:
        ...
```

规则：

- 普通模块只能读写 `status_kind="normal"` 状态表。
- `status_kind="scene"` 只能通过 `SceneTracker` 和 scene tools 修改。
- patch 必须包含 module name、reason、目标表、操作列表和预期 version。
- version 不一致时拒绝写入，要求重新读取。
- 同一字段冲突时拒绝自动合并。
- LLM 不得通过自然语言声称已经修改状态；必须调用工具。

## 命令设计

### `/rp_modules`

输出示例：

```text
已启用 RP Modules:
- dice: 骰子与随机裁定，tools=rp_dice_roll,rp_dice_check_dc
```

### `/rp_module dice`

输出：

- 是否启用。
- 工具列表。
- 配置摘要。
- 自动检定策略说明。
- 首版不展示最近 rolls，因为 MVP 不落盘审计。

### `/roll <expr> [reason...]`

示例：

```text
/roll 1d20+2 潜行越过甲板
```

返回简短结果；不进入 LLM，不自动叙事化。用户想要叙事化时可以普通输入或让主 Agent 用工具。

### `/check_dc <expr> dc=<n> [reason...]`

示例：

```text
/check_dc 1d20+2 dc=12 潜行越过甲板
```

返回成功/失败和 total。

## 测试计划

### 核心模块测试

- `test_dice_parser.py`
  - `d20`
  - `1d20`
  - `2d6+3`
  - `4d6-2`
  - 非法表达式。
  - count/sides/modifier 边界。
- `test_dice_tools.py`
  - 固定 RNG 下 rolls 和 total 可复现。
  - `rp_dice_roll` 返回可读文本。
  - `rp_dice_check_dc` 成功/失败正确。
  - 工具 schema 不包含 seed。
  - 首版不写 JSONL 审计文件。
- `test_rp_module_registry.py`
  - 配置启停生效。
  - 重复 public tool name 失败。
  - fixed sections 稳定排序。
  - dice runtime sections 默认为空。
  - no-op hook 不影响行为。

### 上下文测试

- 启用 dice 时 fixed layer 包含 `rp_module_dice`。
- Dice MVP 不会每轮生成 RP Modules dynamic layer。
- 手动传入 runtime sections 时，`LayerType.RP_MODULES` 位于 `STATUS_TABLES` 后、`USER_MESSAGE` 前。
- RP Modules 不进入 user prefix。
- `[scene]` 仍随 user message 进入 history。

### Agent 测试

- `_setup_tool_registry()` 注册 dice tools。
- mock provider 调用 `rp_dice_roll` 时返回工具结果。
- 用户明确要求掷骰时，工具 schema 可被 LLM 看到。
- `send` 和 `send_stream` 的模块 fixed sections / runtime sections 一致。
- `/roll`、`/check_dc` 被命令分发器拦截，不进入 LLM，不写 history。

### API / WebUI 契约测试

- `GET /play-api/v1/sessions/{session_id}/commands` 能返回 `/roll`、`/check_dc`、`/rp_modules`。
- `POST /play-api/v1/sessions/{session_id}/turn` 发送 `/roll 1d20` 能返回命令结果。
- Play API 仍只传全局短 `session_id` 给 Agent Service。

### Telegram / CLI 测试

- `/roll` 命令经 Telegram 正常分发。
- `/check_dc` 错误表达式返回短错误，不破坏会话。
- 普通消息触发 dice tool 时，stream/non-stream 入口不受影响。
- 测试使用 mock，不依赖真实 Telegram、LLM 或网络。

## 实施顺序

1. 增加 `RPModuleSettings` / `DiceModuleSettings` typed accessor，并更新 `rpg_core/settings.yaml`。
2. 实现 `rpg_core/rp_modules/base.py`、`models.py`、`runtime_store.py`、`registry.py`。
3. 实现 dice parser、dice dataclass、dice tools、dice module。
4. 在 registry 中加载 dice，校验 public tool name 唯一。
5. 在 `RPGGameAgent._ensure_initialized()` 中创建 registry，并把 dice fixed section 接入 `FixedLayerComposer`。
6. 在 `_setup_tool_registry()` 注册模块工具。
7. 在 `_build_transformed_context()` / `_build_ctx_for_inspection()` 传入 runtime sections；Dice MVP 为空。
8. 注册 `/rp_modules`、`/rp_module`、`/roll`、`/check_dc` 命令。
9. 补核心、上下文、Agent、Play API、Telegram/CLI 测试。
10. Dice MVP 稳定后，再评估专门 WebUI 骰子面板和后续 `checks` / `combat` / `inventory`。

## MVP 验收标准

- 没有通用 Skill 注入机制。
- dice 模块可通过 settings 启停。
- 启用 dice 后 fixed layer 包含短静态契约。
- 明确掷骰请求不会由 LLM 口头编造点数，而是可走 `rp_dice_roll` / `rp_dice_check_dc`。
- `/roll`、`/check_dc` 可用，输出兼容 Play WebUI、CLI、Telegram。
- dice MVP 不写 JSONL 审计；结果只通过工具返回文本或命令输出呈现。
- Dice MVP 不默认注入动态 RP Modules layer。
- RP Modules 不进入 user prefix，不写 history。
- `[scene]` 仍是当前 user message 前缀，Scene Runtime 不被模块替代。
- Dice 不读写普通状态表；后续状态写入必须通过 `StatusBridge`。
- Tool public name 全局唯一，重复命名会失败。
- 随机源可注入，测试能断言具体 rolls。
- Play API / Agent Service 边界不变：Play API 不持有 `AgentManager`，会话内请求只用短 `session_id`。
- `send` 与 `send_stream` 模块行为一致。
- 测试不依赖真实 LLM、Telegram 或网络。

## 后续模块候选

- `checks`：属性名、熟练项、优势/劣势、对抗检定。
- `combat`：轻量回合、先攻、HP/状态变更。
- `inventory`：物品获得、消耗、装备、金钱变化。
- `quest_log`：线索、目标、阶段、失败条件和奖励记录。
- `relationship`：好感、敌意、信任、阵营态度。
- `time_weather`：只通过 Scene Runtime 协作，不另建当前场景状态源。
