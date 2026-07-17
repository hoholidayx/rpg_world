# Agent Turn 与状态更新编排

本文是当前 Agent 普通正文 turn 的完整编排说明，覆盖命令与角色门禁、不可变快照、Context 门禁、Narrative Outcome、快速状态路由、主 Agent、事务提交、commit 后副作用和 deferred 慢状态归纳。

README 只保留架构概览；涉及阶段顺序、状态写入边界或失败语义时，以本文和对应代码为准。

## 目录

- [设计目标与核心不变量](#设计目标与核心不变量)
- [组件职责](#组件职责)
- [完整主流程](#完整主流程)
- [Turn 对象与模式策略](#turn-对象与模式策略)
- [Context 门禁与事务创建](#context-门禁与事务创建)
- [StatusSubAgent 固定编排](#statussubagent-固定编排)
- [状态字段更新频率](#状态字段更新频率)
- [scene 的特殊语义](#scene-的特殊语义)
- [主 Agent Context 与工具](#主-agent-context-与工具)
- [提交、回复与后置任务](#提交回复与后置任务)
- [deferred 慢状态归纳](#deferred-慢状态归纳)
- [失败与回退矩阵](#失败与回退矩阵)
- [LLM 调用数量](#llm-调用数量)
- [历史编辑与回滚边界](#历史编辑与回滚边界)
- [模型选择与当前非目标](#模型选择与当前非目标)
- [关键实现入口](#关键实现入口)

## 设计目标与核心不变量

当前编排以代码中的固定阶段约束 LLM，而不是让一个大提示词同时决定剧情裁定、目标路由、多个状态表更新和最终叙事。

核心不变量如下：

1. 同一 session 的工作由 `AgentMailbox` 串行处理。
2. 调用方输入、不可变选择和事务期资源分别由 `TurnRequest`、`TurnExecutionPlan`、`TurnRuntime` 表达。
3. Narrative Outcome 与状态更新是两个独立阶段；需要裁定时，本轮快速状态路由立即停止。
4. 状态路由只决定目标，不直接写值；scene 和每张普通表分别进入独立更新调用。
5. 每次状态更新调用只获得一个目标及其字段 allowlist，代码在工具执行边界再次校验；每个目标各自使用 checkpoint，失败只恢复当前目标并继续快速链路。
6. user/assistant message、Narrative Outcome、scene 和普通状态表的 turn 内写入都先进入 `TurnScratch`。
7. 只有主 LLM 完整成功后才执行短 commit；取消、provider 错误、流缺少 DONE 或 commit 失败都不得留下半个 turn。
8. `realtime` / `event_driven` 属于快速状态，`deferred` 属于回复后的慢归纳，`manual` 禁止 LLM 写入。
9. deferred 在回复交付后运行，但同一 session 的下一 mailbox 项必须等待它完成。
10. `send()` 与 `send_stream()` 共用相同业务 pipeline，只在回复协议和事件时序上不同。

## 组件职责

| 组件 | 职责 |
|---|---|
| `AgentMailbox` | session 内 FIFO、stream task、`requestId` 取消、回复后触发 deferred |
| `AgentTurnService` | 命令/角色 bypass，适配 `AgentReply` 和 SSE |
| `TurnPreprocessor` | 在快照、门禁和事务之前处理斜杠命令与玩家角色 guard |
| `TurnPlanResolver` | 固化 mode/style、玩家角色、Story Prompt、主模型与 RP Module 快照 |
| `TurnRuntimeFactory` | Context 门禁、provider 解析、transaction/scratch、RP runtime 和 Status preflight |
| `StatusPreflightHook` | 为 `StatusSubAgent` 绑定本 turn 的 scratch 工具和逐目标 checkpoint 回调 |
| `TurnPreparation` | 暂存 user message、memory recall、构建主 Context、工具 registry 与 schema |
| `TurnOrchestrator` | 同步/流式共享的 runner、commit、discard 和 post-commit 模板 |
| `AgentTurnTransaction` | message、Narrative Outcome、scene/status COW scratch 与短 commit |
| `PostCommitHooks` | story memory extraction 与 summary compression，逐项隔离失败 |
| `DeferredStatusCoordinator` | 调用同一个 `StatusSubAgent` 归纳到期的 deferred 字段 |

`RPGGameAgent` 只负责组装这些组件并委托公开 API，不承载上述阶段实现。

## 完整主流程

```text
调用方
  │
  ▼
AgentMailbox：按 session 串行取出 QueueItem
  │
  ▼
AgentTurnService / TurnPreprocessor
  ├─ 斜杠命令已处理 ───────────────► 直接返回，不建快照、不进门禁、不建事务
  ├─ 玩家角色 invalid ─────────────► 返回固定角色绑定提示，不写历史、不调用 LLM
  └─ 普通正文
       │
       ▼
TurnPlanResolver
  ├─ TurnExecutionSnapshot
  │    mode / mode prompt / style / player character / rendered Story Prompt / policy
  ├─ MainLLMSelection
  └─ RPModuleSelectionSnapshot
       │
       ▼
TurnRuntimeFactory
  ├─ 主 Context 窗口门禁（不计本次 input）
  ├─ 解析本轮主 provider
  ├─ AgentTurnTransaction.begin() → TurnScratch
  ├─ 创建并绑定 RPModuleTurnRuntime
  └─ StatusPreflightHook（仅 policy 允许时）
       │
       ├─ Outcome 判定
       │    ├─ STAGED   ─► 停止 Route/快速预写
       │    ├─ FALLBACK ─► 停止 Route/快速预写，交由主 Agent 补判
       │    └─ NOT_REQUIRED
       │          │
       │          ▼
       │       Route：选择 scene / normal table / realtime key / event key
       │          │
       │          ▼
       │       Update：scene 一次 + 每张普通表各一次；目标失败仅恢复该目标并继续
       │
       ▼
TurnPreparation
  ├─ 将“scene prefix + 原始 input”暂存为本 turn user message
  ├─ MemoryRecallHook（失败只 warning）
  ├─ 用 scratch 后的 scene/status/outcome 构建主 Context
  └─ 构建 turn-local 工具 registry 与主 Agent schema
       │
       ▼
Main runner
  ├─ 可进行多轮 tool call
  └─ 产生最终 assistant content
       │
       ▼
AgentTurnTransaction.commit()
  ├─ user/assistant messages
  ├─ Narrative Outcome
  └─ scene / normal status documents
       │
       ▼
回复适配 + PostCommitHooks
       │
       ▼
AgentMailbox：回复交付后执行 deferred reconciliation
       │
       ▼
处理同 session 下一 QueueItem
```

角色状态在 `TurnPreprocessor` 先检查一次，`TurnPlanResolver` 创建快照时还会以 `require_player_character=True` 再确认一次，避免 guard 与快照解析之间发生绑定变化。

## Turn 对象与模式策略

### 三段生命周期

| 对象 | 可变性 | 内容 | 生命周期 |
|---|---|---|---|
| `TurnRequest` | frozen | 原始正文、mode、style override、可选 `request_id` | 调用方到 pipeline 结束 |
| `TurnExecutionSnapshot` / `TurnExecutionPlan` | frozen | 玩家角色、Story Prompt、mode/style policy、主模型、RP Module 选择 | Context 门禁前解析，本轮不再变化 |
| `TurnRuntime` | mutable | provider、transaction、scratch、统计、preflight 结果、RP runtime | 仅当前事务期 |

Story、Session 或模型配置在生成中的修改只影响下一 turn，不改写当前 `TurnExecutionPlan`。

### mode policy

| mode | Status preflight | scene/status 工具 | RP Modules | 叙事风格 prompt |
|---|---:|---:|---:|---:|
| `ic` | 开启 | 开启 | 开启 | 开启 |
| `gm` | 开启 | 开启 | 开启 | 开启 |
| `ooc` | 关闭 | 关闭 | 关闭 | 关闭 |

`ooc` 仍是普通正文 turn，会进入主 Context 门禁、事务、主 runner 和 commit；它只是通过 `TurnExecutionPolicy` 关闭 RP/状态相关能力。显式传入的 style ID 仍会被校验，但 style prompt 不注入 OOC Context。

该 policy 不移除 scene 和普通状态表的只读 Context 投影，因此 OOC 主 Agent 仍可理解当前世界状态，但不能通过 scene/status 工具写回；基础工具中的 `WriteFileTool` 也会隐藏，其它只读基础工具可继续存在。

斜杠命令不属于上述普通正文 mode pipeline，始终在门禁和事务之前分流。

## Context 门禁与事务创建

`TurnRuntimeFactory` 首先用不可变的主模型和 RP Module 快照估算“下一轮实际主 Agent Context”。门禁只计算当前已存在的 Context，不计本次待发送 input。

- 达到 `agent.context_window_reject_threshold_ratio` 时，普通正文直接失败。
- 此时 transaction 尚未创建，不调用主/子 Agent，也不写 user history。
- 斜杠命令已经在更早阶段分流，因此始终可用于 `/compact` 等恢复操作。

门禁通过后才调用 `AgentTurnTransaction.begin()`：

- `SessionManager.begin_turn()` 分配正数 `turn_id`。
- `MessageScratch` 保存本轮待提交消息和顺序。
- `StatusDocumentScratch` 保存普通表与 scene document 的 copy-on-write 版本。
- scratch `SceneTracker` 绑定到 scratch status manager，不直接改持久化 scene。
- `RPModuleTurnRuntime` 绑定 scratch，使 Narrative Outcome 的选择和结果都成为 turn-local 状态。

Status preflight 在 user message 正式 stage 之前运行。它读取 `base_history`、当前 scratch state 和原始 `user_input`，因此不会把尚未提交的当前输入误当成已确认历史。

## StatusSubAgent 固定编排

固定顺序是：

```text
Outcome → 仅当 NOT_REQUIRED 时 Route → scene/逐普通表 Update
```

Outcome、Route 和每个 Update 都是独立 LLM 调用，不会在同一个 sub-agent turn 中混合完成。

### 输入与历史窗口

Outcome 和 Route 可以看到：

- SubAgent 的世界书、角色卡等系统上下文；
- 本 turn 固化的玩家角色身份；
- 当前 scene；
- 所有可进入 LLM Context 的 normal session 状态表；
- 最近最多 5 个已存在 turn 的独立历史窗口；
- 当前原始 user input。

StatusSubAgent 不使用主 Agent 的 `summary_processed` 历史过滤。它直接从本 turn `base_history` 取最近 turn，跳过 system message，并将单条内容限制在前 500 个字符。这个窗口会随 turn 滚动；当前实现优先保证近期判断语义，没有额外的历史归纳预处理层。

角色绑定但无法解析 `characterName` 的普通表会在 data/context 边界记录 warning 并排除，因此也不会进入 Route catalog。

### 阶段 A：Outcome 判定

只有当前 RP Module 快照提供 Narrative Outcome，且模块允许自动裁定或检测到明确随机意图时，Outcome 阶段才获得唯一工具：

```text
rp_story_outcome(reason, actor?)
```

该阶段不得获得 scene/status 工具，结果使用类型化状态表达：

| 结果 | 含义 | 后续行为 |
|---|---|---|
| `STAGED` | 已成功暂存一条 Narrative Outcome | 立即停止 Route 和快速状态预写 |
| `NOT_REQUIRED` | 模型未调用 outcome 工具，或本轮没有 outcome schema | 允许进入 Route |
| `FALLBACK` | 返回了非法工具、工具执行失败或判定无法可靠完成 | 停止快速链路，主 Agent 保留补判能力 |

同一 turn 最多暂存一条结果。若模型返回多个纯 outcome 调用，只执行第一个，其余作为重复调用诊断；底层工具本身也会幂等复用 scratch 中的第一条结果。若一次响应混入任何非 outcome 工具，则不执行混合批次并进入 `FALLBACK`。

Outcome 一旦 `STAGED`，本轮主 Context 不再注入 Narrative Outcome fixed section；结果只通过 `RP_MODULES` runtime section 进入主 Agent，包含公开的 `outcomeCode`、label、`narrativeGuidance`、reason 和可选 actor。该 section 使用简短无序条目要求直接执行最终结果，并从统一的 turn-local 状态工具集合中精确列出本轮实际存在的方法；未注册的方法不会出现在提示词中，没有任何可写字段时则明确说明本轮没有状态写入工具。`rp_story_outcome` 同时从主 Agent schema 和可执行 registry 移除，主 Agent 不能改判、重抽或重复执行；底层工具幂等只保留给预裁定边界内部使用。若 Outcome 未预裁定或进入 `FALLBACK`，主 Agent 则继续获得明确写出 `rp_story_outcome` 的原 fixed contract 与补判工具。

### 阶段 B：状态目标 Route

Route 只在 Outcome 为 `NOT_REQUIRED` 且至少存在一个状态工具时运行。它只有一个不产生写入的结构化工具：

```text
select_status_targets({
  scene: boolean,
  tables: [{
    table_id: integer,
    realtime_keys: string[],
    event_keys: string[],
    reason: string
  }]
})
```

`scene` 不是必选目标。当前有 scene 只表示它可供判断；只有本轮确定事实确实影响 scene 时，Route 才应返回 `scene=true`。完全没有目标时可以不调用路由工具。

普通表的定位方式如下：

1. 代码从 `StatusManager.list_context_tables()` 取得当前 session 可见的 normal 表。
2. Route catalog 为每张表提供运行时 `table_id`、name、description，以及每个字段的 key、value、frequency 和 `event_rule`。
3. LLM 只能返回 catalog 中的运行时 `table_id` 和现有字段 key。
4. 代码忽略未知/重复表 ID、未知 key 和频率不匹配的 key。
5. `event_keys` 还必须对应 `event_driven` 字段且具有非空 `updateRule`。

这里的 ID 是 `rpg_session_status_tables` 的运行时表 ID，不是 workspace template ID 或 story mount ID。模板来源和通用挂载范围不向 LLM 暴露。

### 阶段 C：隔离更新

Route 结果被代码拆成多个 `_RoutedStatusUpdateBatch`：

```text
scene=true                 → 1 次 scene update
normal table A 被选中      → 1 次 table A update
normal table B 被选中      → 1 次 table B update
```

每次调用的可见范围不同：

| 目标 | 可见 Context | 可用工具 | 代码边界 |
|---|---|---|---|
| scene | 当前 scene + 近期历史 + input | 本轮动态注册的 scene 工具 | 禁止普通表工具；默认只能改已有 value |
| 单张 normal 表 | 该表被选中的 rows + 近期历史 + input | `status_table_set_values` | 固定 table ID + key allowlist |

隔离 Update 使用同一份稳定 system contract，不再根据整轮工具全集动态枚举能力。contract 明确“只能使用本请求实际提供的工具”，而每次实际下发的 schema 仍只包含当前 scene 或单张 normal 表，因此提示词与执行能力一致。user message 固定按以下顺序组织：

```text
Recent Conversation
→ User Action
→ Selected State Target
```

同一 Route 产生多个目标时，近期历史和当前动作构成共同前缀，目标内容只在末尾分叉；scene 与单表仍保持独立 Context、schema、allowlist 和 checkpoint，不合并调用。

普通表更新工具以及默认策略下的 scene 工具都只能修改已有 key 的 value，不能新增、删除或重命名 key。执行前后有多层校验：

1. 当前阶段只能调用为该 batch 注册的工具名。
2. StatusSubAgent active scope 校验 `table_id` 和本次 Route 产生的 key allowlist。
3. `StatusWritePolicy` 再读取真实 document，校验表可访问、key 存在且频率只属于 `realtime` / `event_driven`。
4. scratch manager 再拒绝 scene 等非 normal 表。
5. 值未变化时返回 no-op，不产生 staged document。

每个快速 Update 目标在 provider 调用前各自创建内存 checkpoint。目标内任一 provider 异常、非法工具、工具执行失败或范围校验失败，都会恢复该目标开始前的 scratch；该目标内已恢复的记录只保留诊断意义，此前成功目标不受影响，代码继续执行后续 scene/普通表目标和主 Agent。`StatusSubAgentResult.failed` 仅表示至少一个快速目标失败，`updated` 表示最终仍有修改保留在 scratch，二者可以同时为 `true`。

目标级 best-effort 不提供可靠重试：主 Agent 仍获得同一个 scratch 上的 scene/status 工具，可以机会性补写失败目标；如果没有补写，也只提交成功目标。checkpoint 创建或恢复失败意味着无法确认 scratch 一致性，异常必须上抛并 discard 整个 turn。取消信号同样向外传播，不作为可恢复目标失败吞掉。不新增持久化 journal、失败待办或重试队列。

### 缓存前缀与观测

Provider 缓存匹配的是实际序列化并 tokenized 后的请求共同前缀，不是代码里的阶段名或 `RPGContext` 层。Outcome、Route、scene Update 和 table Update 使用不同的 system/tool schema，应视为不同缓存族；同一 turn 第一次调用这些阶段时没有命中是正常现象，业务正确性不得依赖缓存。

| 调用链路 | Provider message 顺序 | 缓存族边界 |
|---|---|---|
| Main Agent | Fixed / Persistent / Summary → Hot History 原始 messages → Story / Status / Recall / RP Modules → Current User | 同一主模型与工具集合；rolling history 和动态层决定后续公共前缀 |
| StatusSubAgent | 一条阶段 system contract → 一条动态 user（history/action/target） | Outcome、Route、scene Update、各单表 Update、Deferred 分开 |
| MemorySubAgent | 一条 pipeline system contract → 一条动态 user | Recall、Story、Summary、Batch Summary、Overall Summary 分开 |

StatusSubAgent 与 MemorySubAgent 本身没有使用主 Context 的 system 合并逻辑；它们保持稳定 system 在前、动态 user 在后的两消息结构。主 Context 是否合并不会直接改变 SubAgent 请求，低命中更常由不同阶段 schema、动态 user 内容、服务端缓存策略或共享缓存容量造成。

DeepSeek 的 context cache 由服务端自动、best-effort 管理。以 `A` 为公共前缀，先请求 `A+B`、再请求 `A+C` 时，第二次仍可能没有命中；服务端识别并持久化公共前缀后，后续 `A+D` 才可能报告命中。因此不做额外预热、不为了缓存合并 Outcome/Route/Update，也不向单目标调用暴露工具全集。规则以 [DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache/) 为准。

开启 `verbose_logging` 后，每次 StatusSubAgent 与 MemorySubAgent provider 调用按独立 `source` 记录：

- `contextHash` / `systemHash` / `toolsHash`、对应字符数、逐消息 `index/role/hash/chars`、message/role 计数和工具名，用于比较本地最终请求；日志不输出 system/user/tool schema 正文；
- provider 返回的 cache hit、miss 和 hit rate。实际命中以 usage 为准，hash 相同只说明本地可见前缀结构相同，不保证服务端一定命中。

主 Agent、StatusSubAgent 与 MemorySubAgent 共用 canonical JSON + SHA-256（截断 16 位）的指纹口径。`contextHash` 覆盖按顺序排列的最终 messages，`systemHash` 只覆盖其中的 system message，`toolsHash` 覆盖最终 schema 列表；逐消息 hash 用来定位第一个变化的 wire message。它们是完整内容的相等性指纹，不是 provider cache key：只要尾部变化，完整 hash 就会变化，但 provider 仍可能复用变化点之前的 token 前缀。反过来，hash 相同也不保证服务端缓存一定存在。

这些诊断只进入日志，不新增 API、持久化字段或 WebUI 状态。

### 主 Agent 的补判与状态修正

Status preflight 的结果决定主 Agent 能看到什么：

- `STAGED`：主 Context 注入最终裁定，并从 schema 与可执行 registry 移除 outcome 工具；主 Agent 只能遵循结果。
- `NONE`：没有预裁定；若 Narrative Outcome 模块允许，主 Agent 仍可调用 `rp_story_outcome` 补判。
- `FALLBACK`：预判不可靠，主 Agent 保留同一 outcome 工具完成补判。

scene/status 工具仍绑定到同一个 turn scratch。主 Agent 可以补做预路由遗漏或快速目标失败后的确定状态同步，但普通表工具仍拒绝 `deferred` / `manual` 和非现有 key，默认 scene 工具同样拒绝非现有 key；该补写是机会性的，不承诺本轮或下一轮一定修复。

模型协议要求：只有发生真实、持久、确定的追踪值变化时才写状态；有变化时先在不含 RP 正文的工具调用轮完成同步，最终正文不得新增尚未同步的可追踪确定事实。确认没有变化时允许零状态工具，也不得询问玩家是否需要标记状态。

## 状态字段更新频率

状态字段只允许以下四种频率：

| 频率 | 语义 | 快速 Route | 主 Agent 状态工具 | deferred |
|---|---|---:|---:|---:|
| `realtime` | 本 turn 已确定且应立即反映的状态 | 可选 | 可写 | 不参与 |
| `event_driven` | 仅在本 turn 明确命中自然语言 `updateRule` 时更新 | 命中规则后可选 | 回退时可写，仍受工具频率校验 | 不参与 |
| `deferred` | 多个 committed turn 后才适合归纳的慢状态 | 禁止 | 禁止 | 到期后可写 |
| `manual` | 只由管理端人工维护 | 禁止 | 禁止 | 禁止 |

补充规则：

- 旧 document 缺少 `updateFrequency` 时按 `realtime` 读取。
- `event_driven` 必须有非空 `updateRule`；它不是事件总线，而是 Route 每 turn 对规则是否命中的语义判断。
- 只有 normal 表可以使用 `deferred`。
- `deferredIntervalTurns` 只对 deferred 字段有效；未配置时使用 `agent.status_sub_agent.deferred.default_interval_turns`。
- 频率是字段级策略，不是整张表统一的刷新周期。

这形成“快表/慢表”能力，但不强制整张表只能快或慢。同一 normal 表可以同时包含 realtime、event-driven、deferred 和 manual 字段，例如生命值实时更新、任务节点事件更新、人物关系延迟归纳、备注人工维护。

## scene 的特殊语义

scene 在数据层和 Agent 编排层承担不同职责：

| 层级 | scene 行为 |
|---|---|
| 数据层 | 仍是 `status_kind="scene"` 的 SQLite document，必须挂载到 story；多张时使用排序第一张 active scene |
| 字段策略 | 所有字段固定为 `realtime`，保存边界拒绝 `event_driven` / `deferred` / `manual` |
| 主 Context | 不进入普通 `STATUS_TABLES`，而作为高优先级 `[scene]` user prefix 与当前输入合并 |
| Outcome / Route | 可读取 scene；Route 用独立 `scene: boolean` 决定本轮是否涉及它 |
| Update | 命中后单独调用，只暴露 scene Context 和 scene 专用工具 |
| LLM key 权限 | `agent.scene.allow_runtime_key_changes=false` 时只能修改已有 value；开启后才允许增删非锁定 key |
| 普通表工具 | 永远不使用 `status_table_set_values` |
| 慢归纳 | 永远不进入 deferred |

因此需要区分两件事：

- 只要 active scene 存在，它通常会出现在主 Agent 的当前 user prefix 中。
- 但在状态 Route 中，scene **不会必定返回或必定更新**；只有路由判断本轮涉及 scene 且至少有一个 scene 工具时才返回 `scene=true`。

scene 工具注册和执行权限如下：

| 配置/文档状态 | 实际能力 |
|---|---|
| 默认关闭，至少一个已有 key | 注册 `scene_attr`，其 key schema 只枚举已有字段 |
| 默认关闭，已有 `时间` key | 额外注册 `scene_time`；该工具不能隐式创建 `时间` |
| 默认关闭，空 scene | 不注册任何 scene 工具，Route 强制 `scene=false` |
| `allow_runtime_key_changes=true` | 注册 `scene_time` / `scene_attr` / `scene_del_attr`，保留 `MAX_ATTRS=8` 与非锁定 key 删除规则 |

默认关闭时，`runtimeKeyLocked` 不限制已有 value 更新；它只继续参与显式开启结构编辑后的删除保护。该配置只影响 LLM 工具暴露和执行，Play API / Data 层的手工 CRUD 不变。

普通表才通过 `tables[]` 选择具体运行时表 ID 和字段 key；scene 走专用布尔目标和专用工具，不参与普通表 catalog。

## 主 Agent Context 与工具

`TurnPreparation` 在 Status preflight 结束后执行：

1. 从 scratch `SceneTracker` 读取 scene Context。
2. 把 `scene Context + 原始 user input` 组合成待持久化 user message，并 stage 到 `MessageScratch`。
3. 执行 MemoryRecallHook；失败只记录 warning。
4. 使用 scratch 后的 scene/status、已暂存 Outcome 和当前 user message 构建主 Context。
5. 使用相同 scratch 资源构建可执行工具 registry 和模型可见 schema。
6. `verbose_logging` 开启时，在首次主 LLM 调用前输出一次最终 messages/schemas 指纹；同步与流式共用该 preparation，后续工具 round 不重复。

主 Context 的结构化层顺序是：

```text
Fixed Layer
→ Persistent Memory / Summary
→ Hot History
→ Story Memory / STATUS_TABLES / Recalled Memory / RP_MODULES
→ 当前 User Message（含 scene prefix）
```

实际 provider wire messages 与上述结构化顺序一致：Fixed、Persistent Memory、Summary 分别作为 system message，Hot History 的 user/assistant/tool/system role 全部原位保留，之后 Story Memory、`STATUS_TABLES`、Recalled Memory、`RP_MODULES` 分别作为 system message，最后发送当前 User Message。Story Memory 作为低频累积信息放在 Summary 后、状态表前；当前状态表位于每轮召回之前。这样动态层变化不会截断更早的固定指令与 Hot History 前缀；历史窗口滑动时共同前缀仍可能缩短。Recall 块同时声明冲突时以当前 scene、普通状态表、玩家角色绑定和更新事实为准，不能仅凭历史召回回滚状态。

“只能有一条且必须首位 system”不是跨 provider 的行业准则，而是具体 API 或 chat template 的兼容能力。本项目不再为某个模型全局合并 system。局域网原生 llama.cpp/Qwen 部署可以使用 `--jinja` 和 `--chat-template` / `--chat-template-file` 配置服务端模板；模板上线前必须用包含“Hot History 后再次出现 system”的请求验证角色顺序和生成结果。若某个部署不支持，应在该 provider/chat-template 边界修复，不得改变 canonical Context。

拆分消息不会使 cache 以“单条消息 hash”为单位工作。完整 `systemHash` 覆盖所有 system messages，任一尾部变化仍会改变它；provider 实际判断的是 chat template 序列化/tokenized 后从请求开头起的相同 token。只要前段 token 不变，完整 hash 不同也可能报告部分 cache hit，逐消息 hash 仅用于定位应用层变化点。

主 Agent 历史与 StatusSubAgent 历史不同：主 Context 只投影 `summary_processed=false` 的消息；Play/Agent history API 和 StatusSubAgent 独立链路仍可读取完整未删除历史。

普通 `STATUS_TABLES` 展示运行时表 ID、表名、description、完整 KV 和字段更新策略。角色绑定表按 `characterName` 分组，但绑定只帮助模型理解归属，不改变普通工具的 ID/key 校验方式。

如果 StatusSubAgent 已暂存 Outcome，`RP_MODULES` 会在主 Agent 第一次调用前给出该结果和状态同步边界。主 runner 可以进行多轮工具调用；最终 assistant `content` 是回复、SSE、历史和数据库的唯一正文真源。

## 提交、回复与后置任务

### commit 内容

主 runner 完整成功后，`TurnRuntime.commit()` 先 stage assistant message，再提交：

- 当前 user message；
- 最终 assistant message；
- 本 turn Narrative Outcome；
- scratch 中变化过的 scene/normal status documents。

持久化 session 使用 `rpg_data` database atomic 完成这些写入。数据库事务只覆盖短 commit 点，不跨任何 LLM 调用。状态表发现持久化 document 偏离 scratch baseline 时记录 warning，并按当前 last-write-wins 策略覆盖。

`history_enabled=False` 仅用于测试/内存场景：失败时恢复内存 history，但不承诺补偿已经写入外部 status manager 的数据。

### 同步与流式时序

| 路径 | commit 后顺序 |
|---|---|
| `send()` | commit → `PostCommitHooks` → 返回 `AgentReply` / mailbox `set_result` → deferred |
| `send_stream()` | commit → 发最终 SSE DONE 和 end → `PostCommitHooks` → turn task 返回 → deferred |

流式中 runner 产生的 DONE 会先被暂存；只有 commit 成功后，最终 DONE 才携带 usage、stats 和 `committed_turn_id` 发给调用方。runner 发出 ERROR、stream 结束但没有 DONE、commit 失败或主动取消时都不发送成功 DONE。

同步结果可以携带类型化的 `status_sub_agent_records` 诊断。流式路径会在主 runner 前把实际执行的 preflight tool call/result 转成 SSE 事件；重复 outcome、跳过项和已回滚项属于诊断记录，不重复发成工具事件。

`PostCommitHooks` 当前依次执行 story memory extraction 和 summary compression。两项分别捕获异常，只记录 warning，不回滚已提交 turn。

## deferred 慢状态归纳

deferred 复用同一个 `StatusSubAgent`，但不是快速 Route 的延续。它只根据已提交历史工作，并使用专用结构化工具 `set_deferred_values`。

### 到期计算

对每个 normal 表的每个 deferred 字段：

1. 读取 `(runtime table ID, field key)` 对应的 `last_processed_turn_id`。
2. 只选择 marker 之后的 committed turn groups。
3. 使用字段 `deferredIntervalTurns`，未配置则使用全局默认周期。
4. 累积达到周期后，取最早一批符合周期的 turn，并计算本批 boundary turn ID。
5. 同一 table、同一 boundary 的到期字段合并成一次 LLM batch。

当前到期计算不按 `ic` / `gm` / `ooc` mode 过滤；只要消息已经成功 commit，其 turn group 就会参与累计。斜杠命令和角色 guard 不写历史，因此不计入。

每个 batch 只向模型提供：

- 本批允许的字段 key、当前 value 和周期；
- 从 marker 到本批 boundary 的 committed messages；
- `set_deferred_values` schema。

模型可以不调用工具，表示值无需改变。无论是否改变值，只要 batch 成功，document 与所有本批字段的进度会在同一数据库事务中提交；batch 失败则既不写值，也不推进进度。不同 batch 相互隔离，一个失败不阻止其它 batch。

### 用户体验与串行一致性

deferred 在同步 reply 或流式 DONE 已交付后才由 mailbox 触发，因此不延迟本轮正文展示。它不是脱离 session 的后台任务：mailbox 会等待归纳完成，再处理同一 session 的下一命令或 turn，确保下一轮读取到一致的慢状态。

## 失败与回退矩阵

| 失败位置 | 当前行为 | 事务结果 |
|---|---|---|
| 命令或玩家角色 guard | 直接 bypass；角色 invalid 返回固定绑定提示 | 不创建事务 |
| Context 窗口门禁 | 拒绝正文，提示先压缩 | 不创建事务 |
| Outcome 返回非法/执行失败 | 标记 `FALLBACK`，停止 Route，主 Agent 补判 | 保留 scratch，主 turn 继续 |
| Route 失败 | 停止快速 Update，主 Agent 继续处理 | 保留 scratch，主 turn 继续 |
| 单个快速 Update provider/工具/范围失败 | 仅恢复当前目标，继续后续目标和主 Agent | 保留其他成功目标的 scratch，主 turn 继续 |
| 快速目标 checkpoint 创建/恢复失败 | 异常终止 | discard scratch |
| Memory recall 失败 | warning-and-continue | 主 turn 继续 |
| 主 provider / runner 失败 | 异常终止 | discard scratch |
| stream ERROR 或缺少 DONE | 发送错误/end | discard scratch |
| commit 失败 | 恢复内存 history并报错；持久化 atomic 回滚 | commit 不成立，discard scratch |
| story memory / summary 失败 | warning，互不影响 | 已提交 turn 保留 |
| deferred 单批失败 | warning，不推进该批进度 | 已提交 turn 保留 |

Status preflight 的单目标可恢复失败不会自动终止后续快速目标或主 turn；只有未处理异常、取消或 checkpoint 无法创建/恢复时才升级为事务失败。即使快速阶段已有部分成功目标，后续主 provider、stream 或 commit 失败仍会 discard 整个 turn scratch。

## LLM 调用数量

下表只计算最低调用数；主 Agent 因工具调用产生的后续 round 需另计。

| 情况 | 最低调用组成 |
|---|---|
| 命令 / 角色 guard / Context 门禁拒绝 | 0 |
| `ooc` 普通正文 | 主 Agent 1 次 |
| StatusSubAgent 禁用或本轮无任何相关工具 | 主 Agent 1 次 |
| Outcome 成功预裁定 | Outcome 1 次 + 主 Agent 1 次 |
| Outcome 无需裁定或失败，且没有状态工具 | Outcome 1 次 + 主 Agent 1 次 |
| Outcome 不需要、Route 无目标 | Outcome 1 次 + Route 1 次 + 主 Agent 1 次 |
| Outcome 不需要、命中 N 个状态目标 | Outcome 1 次 + Route 1 次 + N 次隔离 Update + 主 Agent 1 次 |
| 没有 Outcome 工具但有状态能力 | Route 1 次 + N 次隔离 Update + 主 Agent 1 次 |
| deferred 到期 | 回复后每个 `(table, boundary)` batch 额外 1 次 |

这里的一个状态目标是 scene 或一张 normal 表；同一表选中多个 key 仍只产生一次 Update 调用。
包含 Outcome 的行假设本轮实际提供了 outcome schema；模块未提供时直接从 Route 开始计算。

## 历史编辑与回滚边界

- `retry/edit` 若针对最后一个持久化 turn，会先 truncate 该 turn，再以相同 turn ID 重新生成；非最后一轮则追加新 turn。
- truncate 会删除对应消息和 Narrative Outcome，重新生成时重新裁定。
- 已提交的 scene/status 值不会随消息 truncate、edit、retry 或 clear 自动回滚。
- deferred progress 会收缩到剩余历史的最大 turn ID；clear 时收缩到 0。
- 收缩 progress 只影响未来归纳范围，不反向恢复已经写入的 deferred 值。
- 主动停止 stream 只 discard 当前未提交 scratch，不补偿回滚此前已完成的 turn。

状态分支回滚需要独立的状态版本/日志能力；当前实现没有持久化 `status_turn_journal`。

## 模型选择与当前非目标

- 主 Agent 模型按 `config default < story override < session override` 解析，并固化进本 turn plan。
- StatusSubAgent 的 Outcome、Route、隔离 Update 和 deferred 当前复用 `agent.status_sub_agent` 的 provider 配置与逻辑。
- 当前没有按阶段、成本或 provider 健康度动态降级的编排；如需使用低成本或本地模型，应通过现有 biz provider 配置切换整个 StatusSubAgent 链路。
- 当前没有额外轻量预处理 LLM、归纳式 StatusSubAgent 历史窗口，也没有把 Outcome 延迟到多个 turn 后批量判断。
- rolling history 可能降低严格前缀 cache 命中率；隔离 Update 通过稳定 system contract 和 `Recent Conversation → User Action → Selected State Target` 扩大同一 Route 内的公共前缀，不增加动态 provider 路由复杂度。

## 关键实现入口

| 能力 | 文件 |
|---|---|
| facade / composition root | `rpg_core/agent/agent.py` |
| mailbox 与 deferred 时序 | `rpg_core/agent/mailbox/service.py` |
| turn 请求、快照与 policy | `rpg_core/agent/turn/models.py` |
| plan 解析 | `rpg_core/agent/turn/planning.py` |
| Context 门禁与 runtime 创建 | `rpg_core/agent/turn/factory.py` |
| 固定 hooks | `rpg_core/agent/turn/hooks/fixed.py` |
| 主 Context / 工具准备 | `rpg_core/agent/turn/preparation.py` |
| 同步/流式共享编排 | `rpg_core/agent/turn/orchestrator.py` |
| 协议适配与 bypass | `rpg_core/agent/turn/service.py`、`preprocessor.py` |
| transaction / scratch / commit | `rpg_core/agent/turn/transaction/` |
| StatusSubAgent 阶段实现 | `rpg_core/agent/sub_agents/status/agent.py` |
| StatusSubAgent 类型化结果 | `rpg_core/agent/sub_agents/status/models.py` |
| 主工具装配与 schema 过滤 | `rpg_core/agent/runtime/tools.py` |
| 普通状态表工具与写策略 | `rpg_core/status/tools.py` |
| deferred 协调器 | `rpg_core/agent/runtime/deferred_status.py` |
| Narrative Outcome runtime | `rpg_core/rp_modules/narrative_outcome/` |
