# RPG Agent RP Modules 实施计划

## 概述

RP Modules 是一套面向 RPG Agent 的玩法机制模块体系。它不是通用 Skill，也不是任意提示词插件，而是围绕“持续、可信、可测试的角色扮演体验”构建的内置机制层。

当前 `context` 和 `prompts` 还处于架构搭建阶段，角色扮演规则、叙事风格、玩家能动性、机制裁定等内容尚未完全充实。因此本计划的第一原则是：先明确 RP 主契约，再把骰子、检定、战斗、库存、任务、关系等玩法做成可组合、可落盘、可测试的模块。模块可以提供 prompt 片段，但不能取代主 Agent 的 RP 身份。

## 核心判断

RPG Agent 不适合优先引入通用 Skill 生态。

通用 Skill 通常强调“按任务加载一套能力说明”，适合代码、写作、办公等通用助手场景。但在 RPG 中，这种设计容易带来几个问题：

- 把沉浸式回复拉成“分析报告”或“创作建议”。
- 让 `story_architect`、`character_voice` 这类提示词覆盖角色卡、世界书和状态表。
- 让模型显式暴露“我正在使用某个 Skill”，破坏 RP 沉浸。
- 让玩法机制停留在提示词层，缺少状态落盘、工具审计和测试闭环。

因此本项目应把能力扩展定义为 **RP Modules**：每个模块是一套 RPG 玩法或叙事机制，通常包含规则、工具、状态 schema、上下文渲染和测试场景。

## RP 主契约

RP 主契约是所有模块必须服从的上层规则。它应逐步沉淀到 `PromptManager`、固定上下文层、用户后缀、模块 wrapper 和测试中。

建议先明确以下契约：

- Agent 的默认身份是 RPG GM / 场景主持者 / NPC 扮演者，而不是通用助手。
- 普通聊天默认保持 IC 或沉浸式叙事，不展示幕后分析、模块名、规则实现细节。
- 角色卡、世界书、状态表、已发生历史和玩家输入的优先级高于模块提示词。
- 不替玩家角色做重大决定，不代替玩家说话，不自动解决主要冲突。
- 可以描写环境、NPC 行动、后果和可感知线索，但玩家行动必须由玩家决定。
- 机制结果必须转译成自然叙事，而不是只返回工具 JSON 或规则说明。
- 只有用户明确要求规划、复盘、OOC 分析时，才允许输出元叙事内容。

这部分不应做成可选模块，而应作为 RPG Agent 的基础能力常驻。

## Scene Runtime 与当前场景

`status/全局状态/当前场景.csv` 不是普通状态表。它虽然由 `StatusManager` 持久化，但语义上属于 **Scene Runtime**：当前时空、地点、在场人物和短期场景属性的权威来源。

当前实现已经有两个关键设计，后续 RP Modules 不能破坏：

- `SceneTracker` 从 `当前场景.csv` 恢复状态，但不走通用 `status_tables` 渲染，而是渲染为 `[scene]...[/scene]`。
- `[scene]` 会拼入当前 user message，并随用户输入一起写入 history。这样一方面让主 Agent 对当前时空保持高注意力，另一方面让 MemorySubAgent 和后续摘要能按历史顺序归纳场景轨迹。

因此，`当前场景` 不建议做成可插拔 `rp_module`。它应作为 RP Runtime Core 常驻，优先级高于所有玩法模块。RP Modules 可以读取、依赖或通过正式工具请求更新 Scene Runtime，但不能替代它、复制它，也不能另起一套“当前场景”状态源。

推荐边界：

- `SceneTracker` / `当前场景.csv`：维护当前时空、地点、在场人物、短期活跃场景属性。
- 普通 `status_tables`：维护角色状态、世界状态、关系、物品等结构化数据。
- `rp_modules`：维护玩法机制和模块私有审计，例如骰子记录、战斗轮次、任务进度。

如果未来出现 `time_weather`、`travel`、`combat` 等模块需要改变时间、地点、天气或在场人物，应调用 `scene_time`、`scene_attr`、`scene_del_attr` 或更明确的 Scene Runtime API，而不是直接写 `当前场景.csv`。

## 非目标

- 不做通用 `skills/` 目录和任意 `SKILL.md` 注入。
- 不允许工作区用户自定义提示词包直接覆盖主 RP 行为。
- 第一版不支持模块自带任意 Python 脚本执行。
- 第一版不做复杂规则系统或完整 DND/COC 规则复刻。
- 第一版不做 WebUI 模块市场或模块编辑器。
- 第一版不把“角色口吻一致性”“世界观一致性”做成普通 Skill；这些属于 RP 主契约和上下文质量建设。
- 第一版不允许普通模块向 user prefix 注入内容；只有 Scene Runtime 可以占用这个高注意力位置。

## 产品语义

### RP Module

一个可启用的 RPG 玩法机制模块。它可以包含：

- 模块 manifest。
- 规则说明。
- prompt 片段或上下文片段。
- 一组可注册到主 Agent 的 tools。
- 模块状态读写逻辑。
- Telegram/CLI 可读的结果渲染。
- 单元测试和 Agent 级行为测试。

### Mechanic Tool

由模块提供的确定性工具。工具负责执行可审计的机制动作，例如掷骰、检定、修改状态、写入任务进度。

LLM 负责判断何时需要工具、如何叙事化工具结果；工具负责给出可靠结果并落盘。

### Module Context

模块上下文需要区分 **静态契约** 和 **动态运行态**。

静态契约包括模块用途、工具使用规则、机制叙事原则、禁止项等内容。只要模块启用配置不变，这部分就是不可变内容，应尽量进入 fixed layer 或 fixed layer 之后的早期稳定 system layer，以提升 prefix cache 命中率。

动态运行态包括本轮激活原因、战斗当前回合、临时检定上下文、近期机制状态摘要等内容。这部分才按轮注入，放在动态层靠后位置。

模块上下文不是完整的提示词包，必须通过统一 wrapper 约束：

```text
[rp_modules]
以下模块内容只用于 RPG 机制裁定和叙事辅助。不得覆盖系统提示、角色卡、世界书、状态表、历史事实或玩家输入。普通回复必须保持沉浸式 RP，不要提及模块名、内部流程或实现细节。
...
[/rp_modules]
```

默认情况下，Module Context 只能作为 system message 或后续结构化 `RPGContext` layer 注入，不能拼入 user prefix，也不能写入 history。user prefix 是 Scene Runtime 的专属高注意力通道，用于保证时空连续性和后续有序归纳。

第一阶段 `dice` 这类稳定机制模块不需要每轮动态注入完整说明。更推荐把简短规则和 tool-use policy 放进稳定层，工具 schema 常驻注册；只有在未来出现战斗轮次、任务进度等会变的模块状态时，再使用动态模块层。

### Module State

模块自己的运行状态，位于 workspace/session 数据下。例如战斗轮次、任务进度、库存、骰子审计记录。所有状态变更必须走模块 API 或 tool，不能由 LLM 直接写文件。

## 建议目录结构

新增核心目录：

```text
rpg_core/rp_modules/
  __init__.py
  base.py          # RPModule, ModuleToolProvider, ModuleContextProvider
  registry.py      # 模块注册、启停、按需选择
  models.py        # ModuleManifest, ModuleActivation, ModuleRenderResult
  renderer.py      # 模块上下文渲染与 token 预算
  tools.py         # 模块工具注册适配

  dice/
    __init__.py
    manifest.yaml
    module.py
    tools.py
    renderer.py
    rules.md

  checks/
    ...
  combat/
    ...
```

如果后续需要工作区自定义规则，优先做成配置覆盖，例如 `data/<workspace>/rp_modules/dice.yaml`，而不是任意提示词文件覆盖。

### base.py 接口预留

`base.py` 需要从第一版开始预留模块间交互钩子，即使 dice 阶段暂时不用。后续 combat、inventory、relationship 同时启用时，会出现模块协作和状态影响：

- combat 修改 HP 或状态。
- inventory 消耗药水、弹药、金币。
- relationship 提供检定修正或 NPC 反应修正。
- quest_log 根据 combat 或 relationship 结果推进任务阶段。

建议 `RPModule` 基类预留：

```python
class RPModule:
    name: str

    def get_tools(self) -> list[BaseTool]:
        ...

    def get_static_contract(self) -> str:
        ...

    def get_dynamic_context(self, request: ModuleContextRequest) -> ModuleRenderResult | None:
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

第一阶段这些 hook 可以默认 no-op，但 registry 要负责按稳定顺序调用，避免后续临时重构。

## Manifest 设计

示例：

```yaml
name: dice
title: 骰子与随机裁定
version: 1
enabled: true
category: mechanic

activation:
  default: auto
  triggers:
    keywords: [掷骰, 骰子, 检定, d20, d100, 成功率]
    intents: [random_outcome, ability_check, contested_check]

rp_contract:
  mode: ic_first
  reveal_mechanics: concise
  forbid:
    - replace_player_choice
    - override_lore_or_status
    - reveal_internal_module_flow

tools:
  - name: roll
    public_name: rp_dice_roll
  - name: check_dc
    public_name: rp_dice_check_dc

context:
  inject_rules: when_active
  max_tokens: 500
```

关键字段说明：

- `category`：`mechanic`、`state`、`narrative_guard`、`workflow`。
- `activation.default`：`always`、`auto`、`manual`。
- `rp_contract.mode`：`ic_first`、`ooc_only`、`mixed`。
- `reveal_mechanics`：`none`、`concise`、`verbose`，默认 `concise`。
- `forbid`：模块级禁止项，renderer 会写进 wrapper。
- `tools[].name`：模块内部工具名，在模块内唯一即可。
- `tools[].public_name`：注册到 `ToolRegistry` 的全局工具名，必须全局唯一。

## Registry 与工具命名空间

`ToolRegistry` 当前是全局工具注册表，因此 RP Modules 必须从第一版开始预留命名空间，避免后续 `dice`、`combat`、`inventory` 等模块出现同名工具。

建议约定：

- 模块内部可以使用短名，例如 `roll`、`start`、`apply_status`。
- 注册到 `ToolRegistry` 的公开名称必须加命名空间前缀，例如 `rp_dice_roll`、`rp_dice_check_dc`、`rp_combat_start`、`rp_combat_advance_turn`。
- manifest 中显式记录 `public_name`，registry 加载时校验全局唯一。
- 如果两个模块声明了相同 `public_name`，启动或 reload 时应失败并给出清晰错误，而不是后注册覆盖先注册。
- 对 LLM 的工具 description 可以使用自然语言说明模块归属，但工具名本身不要使用 `dice.roll` 这类带点格式，避免 provider 或 schema 兼容性问题。

`RPModuleRegistry` 需要维护：

- `module_name -> RPModule`
- `public_tool_name -> (module_name, internal_tool_name)`
- `module_name -> list[public_tool_name]`

这样第二阶段做按模块过滤 tool schema 时，可以稳定地从 active module 反查公开工具名。

## 模块间交互与冲突处理

RP Modules 不能假设彼此完全独立。后续常见交互包括：

- combat 结算伤害后需要更新 HP/status。
- inventory 消耗物品后可能影响 combat 或 checks。
- relationship 可能为 checks 提供修正值，或影响 NPC 行动。
- quest_log 可能监听 combat/checks 结果推进阶段。

第一阶段不实现完整事务系统，但需要预留清晰边界：

- 模块不能直接读写其他模块的私有状态目录。
- 跨模块影响必须通过 registry 提供的事件、查询接口或明确的共享状态 API。
- 如果多个模块要写同一份权威状态，应由一个 owner 负责。例如 HP 若属于角色状态表，则通过 StatusManager/状态工具更新；inventory 不应直接改 combat 私有文件。
- registry 按稳定顺序分发事件：先当前被激活模块，再按 `module_name` 通知其他模块。
- hook 中不得执行 LLM 调用；hook 只做本地状态同步、缓存失效、修正值准备或审计记录。
- 如果两个模块对同一字段给出冲突修改，第一版应拒绝自动合并，返回需要主 Agent 明确裁定的错误或 warning。

建议事件模型：

```python
@dataclass(frozen=True)
class ModuleActivationEvent:
    module_name: str
    active_modules: tuple[str, ...]
    reason: str
    turn_id: int | None

@dataclass(frozen=True)
class ModuleToolResultEvent:
    module_name: str
    tool_name: str
    result: object
    turn_id: int | None
```

`on_other_module_activated` / `on_other_module_deactivated` 的典型用途：

- relationship 在 checks 激活时准备 NPC 关系修正说明。
- inventory 在 combat 激活时暴露可用消耗品摘要。
- quest_log 在 combat 结束或 checks 失败时监听是否推进任务状态。

这套 hook 先作为 no-op 接口存在，dice 第一阶段只需要验证 registry 会按顺序触发 activation/deactivation 事件。

## 与状态表的交互

RP Modules 应支持读写普通状态表，但必须通过受控桥接层，不能直接读写 CSV 文件。

建议增加 `StatusBridge` 或等价服务，由 registry 注入给模块：

```python
class StatusBridge:
    def read_table(self, type_name: str, table_name: str) -> StatusTableSnapshot:
        ...

    def propose_patch(
        self,
        module_name: str,
        table_ref: StatusTableRef,
        operations: list[StatusPatchOperation],
        reason: str,
    ) -> StatusPatch:
        ...

    def apply_patch(self, patch: StatusPatch) -> StatusPatchResult:
        ...
```

状态表交互规则：

- 模块可以读取普通状态表快照，用于生成动态上下文或计算修正值。
- 模块不能直接调用通用文件工具或手写 CSV。
- 模块写状态必须提交 `StatusPatch`，由 `StatusBridge` 统一校验和应用。
- `当前场景.csv` 不走普通 `StatusBridge` 写入，仍然走 SceneTracker / scene tools。
- 每个 `StatusPatch` 必须包含 module name、reason、目标表、操作列表和预期版本。
- 如果状态表在模块读取后被其他流程修改，`apply_patch` 应检测版本不一致并拒绝，要求重新读取后再提交。
- 多个模块写同一表时，按 registry 事件顺序提交；同一字段冲突时拒绝自动合并。
- LLM 如果需要改变状态，应调用模块工具或现有状态工具，由工具产生受控 patch，而不是在回复里声称已经修改。

建议 patch 操作第一版只支持有限集合：

```python
@dataclass(frozen=True)
class StatusPatchOperation:
    op: Literal["set_cell", "append_row", "delete_row"]
    row_key: str | None
    column: str | None
    value: str | None
```

常见模块映射：

- combat：通过 StatusBridge 修改角色 HP、临时状态、伤害记录。
- inventory：修改物品数量、装备状态、金币。
- relationship：读取关系表，为 checks 提供修正；必要时提交关系变化 patch。
- quest_log：修改任务阶段、线索状态、失败条件。

状态表与模块私有状态的边界：

- 能被多个系统消费、需要展示给用户或进入通用 status layer 的数据，放普通状态表。
- 只服务模块内部机制、审计或缓存的数据，放 `rp_modules/<module>/` 私有状态。
- 如果模块私有状态开始被多个模块依赖，应评估提升为普通状态表或共享状态 API。

## 第一阶段目标：Dice Module

第一阶段不要先做通用模块框架的全部能力，而是用 `dice` 模块验证完整链路。

目标：

- 支持标准骰子表达式，例如 `d20`、`2d6+3`、`1d100`。
- 支持可选原因、角色、难度 DC、修正值。
- 工具结果可审计，必要时写入 session 下的骰子记录。
- 主 Agent 能把骰子结果转成 RP 叙事。
- send 与 send_stream 行为一致。
- Telegram 不需要额外操作即可使用。

建议工具：

```python
rp_dice_roll(expression: str, reason: str = "", actor: str = "") -> RollResult
rp_dice_check_dc(expression: str, dc: int, modifier: int = 0, reason: str = "", actor: str = "") -> CheckResult
```

返回结构建议：

```python
@dataclass(frozen=True)
class RollResult:
    expression: str
    rolls: list[int]
    modifier: int
    total: int
    reason: str
    actor: str
    seed_id: str
```

随机源需要可注入，保证测试可复现：

- 对 LLM 暴露的工具 schema 不包含 `seed` 参数，避免模型操纵点数。
- 模块内部 `DiceRoller` 支持传入 `random.Random` 或等价 RNG。
- 单元测试使用固定 seed 的 RNG，断言具体点数和 total。
- 审计记录保存 `seed_id` 或 `rng_id`，用于关联一次投掷，但不要求能从审计日志反推出随机种子。

## Dice Module RP 行为

骰子模块的重点不是“会随机”，而是“随机结果如何服务 RP”。

默认行为：

- 用户明确要求掷骰时，必须调用工具，不能口头编造结果。
- 当剧情出现明显不确定且结果会影响走向时，可以建议或主动进行检定。
- 检定前应说明可感知风险或难度，但不要剧透隐藏信息。
- 检定后必须叙事化结果，说明玩家角色感知到什么、世界如何响应。
- 失败不是终止剧情，而是引入代价、复杂化、延迟、暴露或资源消耗。
- 不用骰子替玩家选择行动，只裁定行动结果。

示例叙事：

```text
骰子落下：d20 = 7，加上你的敏捷修正 2，总计 9，没能越过难度 12。

你踩上湿滑的船沿时，靴底短暂打滑。你没有摔进海里，但扶住栏杆的声音惊动了甲板另一侧的守夜人。
```

## 后续模块候选

### checks

能力检定模块。可以在 dice 基础上增加属性名、熟练项、优势/劣势、对抗检定。

### combat

轻量战斗模块。第一版只做回合、先攻、HP/状态变更，不做完整规则书。

工具示例：

- `start_combat(participants)`
- `roll_initiative(...)`
- `apply_damage(target, amount, damage_type)`
- `apply_status(target, status, duration)`
- `advance_turn()`

### inventory

库存模块。负责物品获得、消耗、装备、金钱变化。

### quest_log

任务日志模块。负责线索、目标、阶段、失败条件和奖励记录。

### relationship

NPC 关系模块。负责好感、敌意、信任、阵营态度等状态变化。

### time_weather

时间与天气模块。与现有 SceneTracker 协作，避免重复状态源。

## Agent 接入设计

### 初始化

在 `_ensure_initialized()` 中初始化 `RPModuleRegistry`，并根据 settings 创建启用模块。

模块工具通过统一接口注册到 `ToolRegistry`：

```python
for module in module_registry.enabled_modules:
    self._tool_registry.register_all(module.get_tools())
```

### 每轮动态运行态

第一阶段不做 `max_active_per_turn`、动态模块排序或 token 裁剪。当前目标不是通用动态插件生态，而是稳定内置机制模块。

每轮只判断两件事：

- 是否有模块需要提供动态运行态，例如未来 combat 的当前回合、initiative 顺序、临时状态摘要。
- 如果没有动态运行态，则不生成额外 system message。

dice 第一阶段通常只有静态契约和工具 schema，不需要每轮动态注入。后续如果模块数量变多、动态运行态变多，再引入 `max_active_per_turn`、priority、token budget 和裁剪解释。

选择逻辑必须抽成公共方法，供 `send` 和 `send_stream` 共用。

建议方法：

- `_collect_dynamic_rp_module_context(user_input)`
- `_build_messages_with_rp_module_context(messages, dynamic_context)`

第一阶段工具 schema 可以全部注册；第二阶段再做按模块过滤。

### 上下文位置

上下文位置需要按变化频率拆分，不能把所有 RP Module 内容都放到动态尾部。

第一阶段 `rp_modules` 还不是动态插拔生态，启用模块通常随配置固定。对于这类不可变内容，应优先采用缓存友好的放置方式：

- **RP 主契约**：进入 fixed layer，属于主 Agent 身份。
- **静态模块契约 / 工具使用策略**：进入 fixed layer 或 fixed layer 之后的早期稳定 system layer。它类似 tool schema 的说明配套，随模块启停变化，平时不按轮变化。
- **动态模块运行态**：只有当模块存在会变化的状态或本轮提示时才注入，放在状态表之后、当前 user message 之前。

也就是说，第一阶段的 dice 模块可以只把“何时掷骰、必须调用工具、结果如何叙事化、不得替玩家选择”等短规则放进稳定层，工具 schema 常驻注册；不需要每轮都生成 `active rp modules` system message。

这里的“当前 user message”需要特别区分：当前实现会把 `[scene]...[/scene]` 与用户原始输入拼成同一条 user message，并写入 history。也就是说，最终顺序应是：

```text
system fixed layer:
  - RP 主契约
  - 世界书 / 角色卡
  - 静态 RP Module 契约与工具策略
system persistent memory
system summary
mixed hot history
system story memory
system recalled memory
... system status tables
system dynamic rp module state/hints（仅当需要）
user [scene] + user input + user suffix
```

动态模块层放在 user message 前，是为了让会变化的机制状态接近当前请求；但它仍是 system layer，不进入 user prefix，不写入 history，不得比 `[scene]` 拥有更高注意力。`[scene]` 仍然是最靠近用户输入的高优先级运行态。

普通模块不要通过 user prefix 注入内容。只有当某个未来模块被提升为 Scene Runtime 的组成部分，并且它的内容必须随 history 被有序归纳时，才可以评估进入 user prefix；这需要单独设计和测试，不能作为 rp_modules 默认能力。

第二阶段再将模块纳入 `RPGContext` 结构化层：

```text
[0] fixed layer: RP 主契约 + 世界书 + 角色卡 + 静态 RP Module 契约
[1] persistent memory
[2] summary
[3..N] hot history
[N+1] story memory
[N+2] recalled memory
[N+3] status tables
[N+4] dynamic rp module state/hints（可选）
[N+5] user message: [scene] + user input + user suffix
```

注意：`当前场景.csv` 已经由 builder 从通用 status tables 中排除，避免重复渲染。后续增加 `LayerType.RP_MODULES` 时，应只表示动态模块运行态；静态模块契约更适合并入 fixed layer 或新增稳定早期 layer。Scene Runtime 不属于普通 status layer，也不属于 rp_modules layer。

## 配置设计

RP Modules 属于业务玩法配置，应放在 `settings.yaml`，不放进 `llm.yaml`。

示例：

```yaml
base:
  rp_modules:
    enabled: true
    reveal_mechanics_default: concise

    modules:
      dice:
        enabled: true
        activation: auto
        audit_rolls: true
        allow_auto_checks: true
        default_dc: 12

      combat:
        enabled: false
```

配置访问必须增加 typed accessor，例如 `settings.rp_module_settings`，不要在业务模块手写 YAML key 路径。

## 命令设计

第一阶段建议提供只读和调试命令：

- `/rp_modules`：列出已启用模块。
- `/rp_module <name>`：查看模块状态和工具列表。
- `/roll <expr>`：手动掷骰，等价于走 dice 工具。
- `/check <expr> dc=<n>`：手动检定。

命令输出需兼容 Telegram，避免长表格和复杂 Markdown。

## 状态与审计

机制模块只要产生可影响剧情的结果，就应考虑审计。

Dice 第一阶段建议记录到：

```text
data/<workspace>/sessions/<session_id>/rp_modules/dice/rolls.jsonl
```

每条记录包含：

- timestamp
- turn_id
- expression
- rolls
- modifier
- total
- actor
- reason
- source: `tool` 或 `command`
- rng_id / seed_id

审计记录不一定全部注入上下文，但 `/rp_module dice` 可以展示最近若干条。

## 模块状态生命周期

模块状态位于 session 下，例如：

```text
data/<workspace>/sessions/<session_id>/rp_modules/<module_name>/
```

生命周期规则需要提前定义：

- 禁用模块时，已有状态默认保留，不自动删除。禁用只表示不注册工具、不注入上下文、不主动消费状态。
- 重新启用模块时，模块应读取原状态；如果版本不兼容，进入迁移或只读失败状态，并给出明确错误。
- 模块 manifest 的 `version` 用于状态 schema 版本判断。模块状态目录中应保存 `state_meta.json`，至少包含 `module_name`、`schema_version`、`created_at`、`updated_at`。
- 模块升级时，如果 `schema_version` 变化，模块必须提供迁移函数，或显式声明不兼容并拒绝加载旧状态。
- 删除 session 时，session 下的 `rp_modules/` 随 session 一起删除；克隆 session 时应随 session 一起复制，除非用户选择不复制运行态。
- `/rp_module <name>` 应能显示模块状态版本、是否启用、最近审计记录和迁移状态。
- 第一版不提供自动清理命令；后续可以增加 `/rp_module purge <name>`，但必须二次确认。

## 与现有模块的边界

### PromptManager

需要逐步增强 RP 主契约，但不要把所有模块规则塞进主 prompt。主 prompt 负责身份和优先级，模块负责机制细节。

### RPGContextBuilder

第一阶段少改 builder。等 dice 链路稳定后，再增加 `active_rp_modules` layer、`LayerType.RP_MODULES` 和 `/context` 展示。

### StatusManager / SceneTracker

`当前场景.csv` 是特殊高优先级状态，属于 Scene Runtime Core，不是普通 rp_module。模块如果要改变时间、地点、在场人物或当前场景属性，必须通过 SceneTracker 暴露的正式工具或 API，例如 `scene_time`、`scene_attr`、`scene_del_attr`。不要让 LLM 用通用文件工具直接改 CSV/JSON。

普通状态表仍由 `StatusManager` 管理，但 RP Modules 不应直接操作 `StatusManager` 的底层文件。需要通过 `StatusBridge` 读取快照和提交 patch。模块私有状态放在 session 下的 `rp_modules/<module_name>/`。三者不要混写。

### Memory / Summary

Scene Runtime 会随 user message 写入 history，因此当前场景轨迹可以被 MemorySubAgent 和摘要按顺序看见。普通 Module Context 不写入 history，避免把规则说明和内部流程污染长期记忆。

模块结果进入正式 assistant 回复后，自然会被历史和摘要看见。第一阶段不单独为模块结果建立 memory 索引。

## 测试计划

核心模块测试：

- dice 表达式解析：`d20`、`2d6+3`、非法表达式、边界数量。
- `rp_dice_roll` 使用固定 RNG seed 时点数和 total 可复现。
- `rp_dice_check_dc` 成功/失败判定正确。
- audit 写入 JSONL，字段完整。
- registry 会拒绝重复 `public_name`，避免模块工具命名冲突。
- registry 会按稳定顺序触发模块 activation/deactivation hook。
- 默认 no-op hook 不影响 dice 第一阶段行为。
- 模块不能通过 registry 直接访问其他模块私有状态目录。
- StatusBridge 能读取普通状态表快照，并通过版本检测拒绝过期 patch。
- 两个模块对同一状态字段提交冲突 patch 时拒绝自动合并。
- `当前场景.csv` 不允许通过普通 StatusBridge patch 修改。
- 禁用模块后状态保留但工具不注册、上下文不注入。
- session 删除/克隆时模块状态跟随 session 目录语义。

Agent 接入测试：

- 启用 dice 时，稳定上下文中包含 dice 的静态 RP 契约或工具策略。
- 用户明确要求掷骰时，不要求每轮注入完整 dice 说明；模型应通过常驻工具 schema 和稳定契约调用 dice 工具。
- 普通 RP 输入不应注入无关模块详情。
- 当前 user message 中仍包含 `[scene]`，并且 `[scene]` 位于用户原始输入之前。
- RP Modules 不进入 user prefix，不写入 history。
- 动态模块运行态仅在确有变化状态时注入，例如未来 combat 当前回合。
- send 和 send_stream 的模块选择一致。
- dice 工具 schema 被注册，mock provider 可以调用。
- 工具结果后，assistant 回复仍包含 RP 叙事约束。

命令测试：

- `/rp_modules` 能列出 dice。
- `/roll 1d20+2` 返回骰子结果。
- `/check 1d20 dc=12` 返回成功/失败。

Telegram 测试：

- `/roll` 命令经 Telegram 正常分发。
- 普通消息触发 dice 工具时，stream 编辑节流不受影响。
- 异常表达式能返回短错误，不破坏会话。

RP 回归测试：

- 静态模块契约包含“不得替玩家行动、不得覆盖角色卡/世界书/状态表”。
- 静态模块契约包含“不得覆盖 Scene Runtime / 当前场景”的约束。
- 用户没有要求 OOC 时，模块上下文不应要求模型输出分析报告。
- 检定失败场景要求继续推进剧情，而不是直接阻断回复。

## 实施顺序

1. 增强 RP 主契约文本：先补 PromptManager 或固定层模板中的核心规则。
2. 明确 Scene Runtime 文档与测试边界，保证 `[scene]` 继续作为 user message 前缀并写入 history。
3. 增加 `rp_modules` 配置块和 Settings accessor。
4. 实现 `rpg_core/rp_modules/base.py`、`models.py`、`registry.py`。
5. 实现 dice 表达式解析和工具。
6. 在 Agent 初始化中注册 dice tools。
7. 将 dice 的静态模块契约接入 fixed layer 或 fixed layer 后的稳定 system layer，避免每轮动态注入。
8. 在 send/send_stream 中接入动态模块运行态选择；动态层注入位置在 system status tables 后、user message 前，仅在需要时出现。
9. 增加 `/rp_modules`、`/rp_module`、`/roll`、`/check` 命令。
10. 补核心、Agent、命令和 Telegram 测试。
11. dice 稳定后，再评估 combat、inventory、quest_log。

## 第一阶段验收标准

- 没有通用 Skill 注入机制。
- dice 模块可配置启停。
- 明确掷骰请求会走工具，不由 LLM 编造。
- 工具结果可审计。
- 普通 RP 回复仍保持沉浸式，不暴露模块内部流程。
- `[scene]` 仍作为当前 user message 前缀进入主上下文和 history。
- 普通 rp_modules 不占用 user prefix，不污染长期历史。
- dice 的静态规则不按轮重复注入，避免破坏 prefix cache。
- 动态模块层为空时不产生额外 system message。
- 模块工具公开名全局唯一，重复命名会失败。
- dice 随机源可注入，测试能断言具体点数。
- 模块状态禁用保留、升级可迁移或明确失败、删除 session 时随 session 清理。
- `RPModule` 基类预留模块间交互 hook，registry 按稳定顺序分发事件。
- 第一版遇到跨模块状态写冲突时拒绝自动合并，并返回清晰 warning/error。
- RP Modules 通过 StatusBridge 与普通状态表交互，不直接写 CSV；Scene Runtime 仍只通过 SceneTracker 修改。
- send 与 send_stream 行为一致。
- Telegram 主入口可用。
- 测试不依赖真实 LLM、Telegram 或网络。
