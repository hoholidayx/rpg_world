# RPG World WebUI 产品需求文档

## 0. Solo 开发大纲：需求、核心方案与优先级

本章作为独立开发时的执行清单，只保留“先做什么、为什么做、做到什么程度”。详细论证、架构说明和验收标准见后续章节。

### 0.1 一句话方向

先把 WebUI 做成 **可稳定游玩的互动叙事客户端**，而不是一开始追求完整游戏化：优先解决会话继续、流式叙事、场景/角色状态可见、输入可控、错误可恢复；分支、视觉小说表现和玩法模块后置。

### 0.2 核心方案路线

1. **保留现有 Dashboard**：当前 `rpg_world/webui` 继续承担后台管理、CRUD 和调试，不在这里追求沉浸式体验。
2. **新增 Play WebUI**：单独创建 `rpg_world/play_webui`，默认采用 `Next.js + React + TypeScript + AI SDK + shadcn/ui + Tailwind + Zustand + TanStack Query`。
3. **先复用现有 API**：MVP 先接 `/chat/stream`、`/chat/history`、`/chat/commands`、session/status/character/lorebook 现有接口，不等待后端一次性重构。
4. **再补关键后端接口**：优先补 scene 聚合读写、session title/rename、Play turn API、stop/retry；history CRUD、fork、snapshot 放到第二阶段。
5. **事件流渐进升级**：先兼容当前 `AgentStreamEvent`，前端 reducer 分离 text/thinking/tool/done/error；后续再升级为 RPG typed event stream。
6. **视觉增强后置**：P0/P1 只做响应式 UI 和轻量状态面板；PixiJS 放到沉浸式增强阶段，Phaser 暂不进入当前开发计划。

### 0.3 按优先级实施清单

#### P0：先做可玩的 Play MVP

- 创建 `play_webui` 项目和基础路由：Home / Continue、`/session/[id]`。
- 实现 workspace/session 选择、最近存档、继续游玩。
- 接入 `/chat/stream`，实现稳定 SSE 流式输出。
- 做主界面三块：剧情流、场景 HUD、底部输入区。
- 输入区支持自由输入、IC/OOC/GM 指令或 slash command 的最小切换。
- 场景 HUD 先读取 `当前场景.csv` 对应 API；若 API 不足，先在 Dashboard/API 中补 scene 读取接口。
- 处理基础错误：stream error 不清空已输出内容，允许复制本轮文本。
- 移动端可用：单栏剧情流 + 底部输入 + 抽屉式状态面板。

#### P1：补齐“可控”和“可维护”

- Dashboard 稳定化：确认 workspace/session/character/lorebook/status CRUD 可用。
- 增加 scene 聚合读写接口与 Dashboard Scene Editor。
- 增加 session title/rename，改善存档管理。
- Play 输入增强：语气、节奏、叙事视角、快捷行动。
- 前端增加 StreamStatus 和 DebugEventPanel，区分 thinking/tool/error/done。
- 后端增加 stop/retry/continue 的明确 API 或明确降级提示。
- 增加本地草稿、复制、收藏片段、基础剧情日志。

#### P2：做分支、回滚、typed events

- 设计 `RPGStreamEvent` schema，并新增 Play turn API。
- 将通用 agent stream 映射为 narration、dialogue、tool、scene.patch、system.status 等事件。
- 实现 Turn 列表、删除后续、重试指定 Turn。
- 实现 fork session：先基于 session clone，再记录 fork 来源元数据。
- 设计 snapshot：明确 history、scene、status/module state 的一致性边界。
- Play 增加 Branch UI 和 Journal。

#### P3：沉浸式增强，但不做重游戏

- 增加 ChoiceCards、角色表情/情绪标签、关系值、背包/任务简表。
- 接入首批轻量 RP Modules：骰子、检定、物品、任务。
- 可选引入 PixiJS：背景、立绘、表情、粒子、过场；业务状态仍由 React + 后端管理。
- 评估 TTS/语音输入，但不阻塞主流程。
- 暂不做 Phaser、多人实时协作、完整地图/战斗系统。

### 0.4 每阶段完成定义

- **P0 完成**：不用 Telegram 和 Dashboard，玩家也能在 Play WebUI 中选择存档、发送输入、看到流式剧情、查看当前场景，并在移动端完成普通 RP。
- **P1 完成**：独立开发维护成本下降，Dashboard 能支撑数据修正，Play 输入和错误恢复足够顺手。
- **P2 完成**：LLM 跑偏后可以重试、回滚、分支，事件流不再依赖整段 markdown 解析。
- **P3 完成**：界面有轻视觉小说感和轻机制反馈，但核心仍是互动叙事，不被游戏引擎复杂度绑死。

## 1. 背景、定位与结论

RPG World 的长期目标是构建一个 **AI RPG World / 沉浸式 RP 平台**。现有 Telegram 渠道适合轻量交互、App 推送和兜底回复，但不适合承载复杂的角色卡、世界书、状态表、场景 HUD、剧情日志、分支回滚、玩法模块和多面板沉浸式体验。

因此 WebUI 后续应成为主体验，并拆分成两个独立 Web 项目：

1. **Dashboard WebUI（后台管理端）**：面向创作者、GM 和系统维护者，继续偏数据维护、配置、诊断和调试。
2. **Play WebUI（前台游玩端）**：面向玩家，承载沉浸式 RP 聊天、轻游戏化交互和移动端游玩。

Play WebUI 不应被设计成普通 chatbot，而应被视为：

> 互动叙事运行时 + 角色扮演控制台 + 视觉小说/轻游戏界面 + 多轮剧情日志 + 用户输入面板。

当前阶段的最终目标不是完整网页游戏，也不要求复杂地图、物理碰撞或 3D 角色，而是围绕 **剧情连续、角色可信、状态可见、输入可控、流式低等待、可回滚/可重写/可分支** 做交互增强。

## 2. 产品目标与非目标

### 2.1 总目标

- 让 RPG World 从“多渠道聊天机器人”升级为“可长期运行、可管理、可沉浸游玩的 AI RPG 世界”。
- WebUI 负责体验上限，Telegram 负责触达效率。
- Dashboard 与 Play 前端独立演进，但共享 FastAPI / `rpg_core` 后端能力。
- 所有渠道共享 workspace/session 语义，避免同一故事在不同入口分裂。
- 前端不只接收 markdown 文本，而是逐步升级为消费 typed event stream，并将旁白、对白、系统状态、工具调用、场景变化、角色状态、选项和机制事件分开展示。

### 2.2 非目标

- 不在 Telegram 中实现复杂 dashboard、地图、战斗面板、状态表编辑器等重 UI。
- 不在前端复制角色卡、世界书、状态表、记忆、摘要和 RP 机制的核心业务规则。
- 第一阶段不做多人实时协作、公共房间或商业化账号系统。
- 第一阶段不做完整规则书复刻；玩法模块先围绕轻量、可审计、可测试机制建设。
- 第一阶段不做复杂 3D、完整游戏引擎化地图、实时动作战斗或计划跟踪 UI。已有 agent 计划跟踪另行规划，Play WebUI 先围绕会话内互动体验。

## 3. 技术选型结论

### 3.1 推荐默认方案

对 **Play WebUI**，默认选型建议为：

```text
Next.js App Router + React + TypeScript
+ Vercel AI SDK
+ shadcn/ui + Radix UI + Tailwind CSS
+ Zustand
+ TanStack Query
+ SSE streaming
```

当视觉小说表现需求更强时，再叠加 **PixiJS**；当产品已经接近“网页游戏”而不是“互动叙事”时，再评估 **Phaser**。

选择理由：

- Play WebUI 的前端不是简单聊天框，而是可流式更新的互动叙事运行时。Next.js App Router 适合把账号、存档、角色配置、会话列表、设置、后端密钥保护等放在服务端，把输入框、实时流、角色状态、动画、快捷操作等放在客户端。
- Vercel AI SDK 适合 LLM 应用的流式文本、结构化对象、工具调用、Agent 与 UI hooks，可以把“掷骰结果”“角色状态变化”“物品获得”“副本事件”等渲染成专门 UI 卡片。
- shadcn/ui + Radix + Tailwind 适合快速搭建可定制的 RPG 控制台、Dialog、Drawer、Tabs、角色卡、状态标签、响应式布局和移动端 Bottom Sheet。
- Zustand 适合保存高频、临时、UI 驱动的运行态；TanStack Query 适合管理远程 server state、缓存、重试、失效和去重。

### 3.2 Dashboard 与 Play 的技术边界

当前 Dashboard WebUI 使用 Vue 3 + Vite + Ant Design Vue + Pinia，适合后台管理表单、表格和 CRUD。建议：

- **Dashboard WebUI**：继续沿用 Vue + Vite + Ant Design Vue + Pinia，短期聚焦稳定化和 API 契约补齐。
- **Play WebUI**：新增独立项目时采用 Next.js + React + TypeScript 技术栈，优先服务沉浸式体验和流式 UI。
- 两个前端共享 OpenAPI / typed API client、数据类型、鉴权约定、workspace/session 选择约定、RP 文本渲染规范和错误码约定。

### 3.3 视觉与游戏化路线

| 路线 | 技术 | 适用阶段 | 说明 |
|---|---|---|---|
| A. 最快 MVP / 最稳生产 | Next.js + React + AI SDK + shadcn/ui + SSE | M2 起步 | 文字 RPG、情感陪伴、即兴 RP、剧情生成、角色互动。 |
| B. 视觉小说增强 | 路线 A + PixiJS | M5 可选 | 背景、立绘、表情、BGM、粒子、镜头过渡；React 管业务，PixiJS 管 canvas 画面。 |
| C. 网页游戏化版本 | Next/Vite Shell + Phaser + React HUD + WebSocket | 后续另立项 | 地图、战斗、tilemap、roguelike、多人副本；不作为当前目标。 |
| D. Vue 团队路线 | Nuxt/Vue + AI SDK + Tailwind/Headless + Pinia | 备选 | 若团队强依赖 Vue 可考虑，但 AI UI / generative UI 生态便利度低于 React/Next。 |

## 4. 后端现状与约束：结合 `rpg_core` 的设计边界

### 4.1 后端分层边界

WebUI 必须遵守当前工程分层：

- `api/` 是 FastAPI 接入层，负责 HTTP 路由、请求/响应 schema、SSE 包装和鉴权/工作区解析。
- `channels/` 是 Telegram / CLI 等渠道接入层。
- `rpg_core/` 是无框架核心层，负责 Agent、Session、Context、Memory、Summary、Scene、Status、Character、Lorebook、LLM Provider、Tools 等业务能力。
- 前端不能直接读写 `data/` 文件，也不能绕过 API 直接修改角色卡、状态表、history、summary 或记忆索引。

### 4.2 已有核心能力映射

| 能力 | 当前后端位置 | WebUI 使用方式 | 备注 |
|---|---|---|---|
| LLM/Agent 主循环 | `rpg_core/agent/*` | 通过 `/chat/send`、`/chat/stream`、`/chat/command` | Agent 由 `AgentManager` 按 workspace/session 复用。 |
| SSE 流式输出 | `api/routers/chat.py` + `AgentStreamEvent` | Play Room 初期直接消费 `kind/content/tool_*` | 当前事件为通用 agent stream，后续需适配成 RPG typed events。 |
| session 生命周期 | `rpg_core/session/manager.py` + `api/routers/sessions.py` | session 列表、创建、删除、克隆 | 已有 turn_id、seq_in_turn、history.jsonl、session.json 元数据。 |
| history 持久化 | `SessionManager.append/replace_history` | 通过 API 查看和后续 CRUD | 已有 turn 分组基础，可支撑回滚/分支改造。 |
| 当前场景 | `rpg_core/scene/tracker.py` + `status/全局状态/当前场景.csv` | Play HUD / Dashboard Scene Editor | 场景状态是 user prefix 高优先级上下文，不是普通状态表。 |
| 状态表 | `rpg_core/status/*` + `api/routers/status.py` | Dashboard CRUD / Play 只读或受控轻编辑 | Play 不直接编辑 CSV 文件。 |
| 角色卡 | `rpg_core/character/*` + API | Character Panel / Character Sheet | 展示为只读或轻编辑，权威编辑在 Dashboard。 |
| 世界书 | `rpg_core/lorebook/*` + API | Dashboard 管理，Play 只显示命中摘要或设定入口 | 命中诊断默认隐藏。 |
| Context 结构与渲染 | `rpg_core/context/*` | Dashboard Context Inspector | Play 默认不显示完整 prompt。 |
| Memory / Summary | `rpg_core/memory/*`、`rpg_core/summary/*` | Journal、MemoryView、Dashboard 诊断 | Play 只显示前端可见摘要，不等于完整长期记忆。 |
| RP Modules 占位 | `rpg_core/jinja/modules/rp_modules.jinja`、tool registry | Mechanics Panel | 骰子、战斗、物品等必须走受控工具和状态写入。 |

### 4.3 当前事件流与目标事件流

当前 `/chat/stream` 返回的 SSE 数据形态来自 `AgentStreamEvent.to_dict()`，核心字段包括：

```ts
type CurrentAgentStreamEvent = {
  kind: "text" | "thinking" | "tool_call" | "tool_result" | "round_start" | "round_end" | "done" | "error";
  content?: string;
  tool_name?: string;
  tool_arguments?: string;
  tool_result_preview?: string;
  round_index?: number;
  usage?: unknown;
  model?: string;
  finish_reason?: string;
  duration_ms?: number;
};
```

Play WebUI 的目标不是一直解析一整段 markdown，而是最终消费更贴近 RPG UI 的 typed event stream：

```ts
type RPGStreamEvent =
  | { type: "narration.delta"; text: string }
  | { type: "dialogue.delta"; speakerId: string; text: string; emotion?: string }
  | { type: "scene.patch"; background?: string; bgm?: string; mood?: string; attrs?: Record<string, string> }
  | { type: "character.patch"; id: string; expression?: string; affection?: number; tags?: string[] }
  | { type: "choice.list"; choices: Choice[] }
  | { type: "dice.roll"; label: string; result: number; dc?: number }
  | { type: "tool.event"; name: string; status: "start" | "done" | "error"; preview?: string }
  | { type: "system.status"; status: "thinking" | "retrieving_memory" | "tool_running" | "saving" | "done" | "error" };
```

实施上建议分两步：

1. **兼容层**：Play WebUI 先把 `CurrentAgentStreamEvent` reduce 成 Timeline / StreamStatus / DebugEventPanel，确保现有后端可用。
2. **后端 typed event adapter**：新增 `/api/sessions/:id/turn` 或 `/chat/rpg-stream`，在 API 层或 `rpg_core` 层将通用 Agent 事件、工具调用结果、场景状态变化、角色状态变化映射为 `RPGStreamEvent`。保留旧 `/chat/stream` 给 Dashboard 调试和兼容。

## 5. 核心领域对象

Play WebUI 与后端协作时，核心对象建议分为：

```ts
type Session = {
  id: string;
  workspace: string;
  title?: string;
  createdAt?: string;
  updatedAt?: string;
};

type Turn = {
  turnId: number;
  userMessage: string;
  assistantMessage?: string;
  source?: "play_webui" | "dashboard" | "telegram" | "cli";
  events?: RPGStreamEvent[];
  snapshotId?: string;
};

type Scene = {
  attrs: Record<string, string>;
  time?: string;
  location?: string;
  presentCharacters?: string[];
  mood?: string;
};

type CharacterRuntimeState = {
  id: string;
  name: string;
  role: "player" | "npc" | "companion" | "gm";
  expression: "neutral" | "happy" | "angry" | "shy" | "sad" | "tense";
  emotionVector?: {
    affection: number;
    trust: number;
    tension: number;
    curiosity: number;
  };
  currentGoal?: string;
  visibleStatusTags: string[];
};

type MemoryView = {
  summary?: string;
  visibleFacts: string[];
  lastUpdatedTurnId?: number;
};

type Snapshot = {
  id: string;
  sessionId: string;
  turnId: number;
  createdAt: string;
  label?: string;
};
```

注意分层：

- 用户可见：表情、语气、关系倾向、状态标签、场景摘要、可见记忆摘要。
- GM/调试可见：工具调用、上下文结构、记忆命中、状态表注入、token 预算。
- 模型内部：完整系统约束、长期记忆、隐藏动机、世界规则细节。

## 6. 项目拆分与信息架构

### 6.1 Dashboard WebUI

**定位**：数据管理、创作维护、配置诊断后台。

**建议目录**：继续使用当前 `rpg_world/webui`，或后续重命名为 `rpg_world/dashboard_webui`。

**核心用户**：世界/剧本创作者、GM / 管理员、调试 Agent 行为的开发者。

| 页面 | 说明 | 优先级 |
|---|---|---|
| Overview | 当前 workspace 概览、数据健康、最近 session | P0 |
| Workspaces | 工作区创建、重命名、删除、切换 | P0 |
| Sessions | 存档列表、创建、克隆、删除、历史查看、后续重命名 | P0 |
| Characters | 角色卡 CRUD、预览、校验 | P0 |
| Lorebook | 世界书 CRUD、关键词、启用状态 | P0 |
| Status Tables | 状态类型/CSV 表 CRUD、当前场景入口 | P0 |
| Scene Editor | 读取/更新 `当前场景.csv` 的受控编辑器 | P0 |
| Memory & Summary | 记忆索引、摘要文件、召回诊断 | P1 |
| Context Inspector | 当前 prompt/context 预览、token 估算 | P1 |
| Settings | API、LLM、渠道、模块配置查看与校验 | P1 |
| Channel Bindings | Telegram chat 与 workspace/session 绑定管理 | P1 |
| Event Debugger | 原始 SSE / typed event 查看器 | P1 |

### 6.2 Play WebUI

**定位**：玩家前台、沉浸式 RP 主客户端。

**建议目录**：新增 `rpg_world/play_webui`，作为独立 Next.js 项目。若部署约束要求静态导出，需要在方案评审时确认 Next.js SSR/API route 的使用边界。

| 页面 | 说明 | 优先级 |
|---|---|---|
| `/` | 落地页 / 进入游戏 / 最近继续 | P0 |
| `/app` | 最近会话、角色、世界模板、收藏、设置入口 | P0 |
| `/session/[id]` | 主 RPG 运行时：剧情流、场景画面、输入、角色状态 | P0 |
| `/session/[id]/branch` | 分支、回滚、快照、删除后续 | P1 |
| `/character/[id]` | 角色设定、人设、声音、边界，默认轻编辑或只读 | P1 |
| `/world/[id]` | 世界观、副本规则、风格设定 | P1 |
| `/settings` | 模型偏好、内容边界、隐私、导出 | P1 |
| Journal | 剧情日志、摘要、关键事件、分支回顾 | P1 |
| Mechanics Panel | 骰子、检定、战斗、物品、任务等模块入口 | P2 |

### 6.3 Play Room 推荐布局

桌面端：

```text
┌────────────────────────────────────────────────────┐
│ 顶部：世界/副本/角色/模式/模型状态                 │
├──────────────┬──────────────────────┬──────────────┤
│ 左：角色状态  │      画面/剧情主区域   │  记忆/物品/规则 │
│ NPC/关系/情绪 │  背景/立绘/旁白       │  背包/目标/规则 │
│ 玩家状态      │  对话气泡/事件/选项    │  调试可折叠     │
├──────────────┴──────────────────────┴──────────────┤
│ 输入：自由行动 + 语气 + 快捷动作 + 继续/重写/分支     │
└────────────────────────────────────────────────────┘
```

移动端：

```text
顶部：当前世界 + 当前状态
中部：剧情流 / 场景画面
底部：输入框 + 快捷动作
抽屉/Bottom Sheet：角色、背包、记忆、设置、Journal
```

## 7. Play WebUI 核心体验需求

### 7.1 流式叙事体验

RPG/情感/即兴产品最怕“白屏等待”。前端必须支持：

1. token-by-token 或 event-by-event 的剧情输出；
2. 用户可以停止生成、继续、重试、换风格；
3. 旁白、对白、系统事件、选项、角色状态分离展示；
4. 失败时保留已生成片段，不整轮消失；
5. 支持“正在思考 / 正在检索记忆 / 正在运行工具 / 正在更新场景 / 正在保存”等细粒度状态；
6. tool call 默认沉浸式折叠，只在调试面板完整展示。

传输层建议：

- P0 使用 SSE，适合 server → client 的 LLM token/event 流。
- P2 或多人/语音/强打断需求出现后，再引入 WebSocket。WebSocket 不作为 MVP 前置条件。

### 7.2 游戏化状态面板

核心组件包括：

- **StoryTimeline**：旁白、对白、系统事件、骰子、战斗、物品、世界切换。
- **CharacterPanel / CharacterCard**：头像、表情、情绪、关系值、状态标签、当前动机的用户可见部分。
- **ScenePanel**：地点、时间、天气、氛围、背景图、BGM、当前 NPC。
- **ActionComposer**：自由输入、快捷动作、语气选择、潜台词/内心戏开关。
- **ChoiceCards**：模型生成的多个行动选项，允许用户改写后发送。
- **BranchToolbar**：撤回上一轮、从某一轮分叉、保存当前线。
- **BoundaryPanel**：人设、世界观、禁区、偏好、内容边界。
- **DebugEventPanel**：开发/GM 可见的原始事件、工具记录、stats。

### 7.3 强可控的用户输入

输入框不应只是普通 textarea，应包含：

| 控制项 | 示例 |
|---|---|
| 自由行动 | “我想做什么” |
| 语气 | 冷静 / 诱导 / 撒娇 / 威胁 / 幽默 / 试探 |
| 叙事视角 | 第一人称 / 第二人称 / 第三人称 |
| 节奏 | 快速推进 / 细腻描写 / 多给选项 / 少旁白 |
| 可见指令 | 继续 / 重写 / 缩短 / 更克制 / 更黑暗 |
| 隐藏偏好 | 不显示给角色，只影响模型 |
| 输入模式 | IC / OOC / GM 指令 / Slash command |

前端将这些输入组合为 structured action，再由后端转换为受控 prompt / command / metadata。不要要求普通用户直接编辑系统 prompt。

### 7.4 可回滚、可重写、可分支

每一轮 Turn 应支持：

- 继续。
- 重试。
- 改写本轮。
- 从这里分支。
- 删除后续。
- 收藏片段。
- 导出剧情。
- 查看本轮状态变化。

后端基础：`SessionManager` 已具备 turn_id / seq_in_turn / history replace / clone 能力，但还缺少面向 WebUI 的 history CRUD、按 Turn 删除后续、快照、分支元数据和回滚后状态一致性接口。该能力应作为 P1 后端重点建设。

### 7.5 角色、情绪、关系显性化

情感/RP 类 Agent 的沉浸感来自“角色是否像活着”。前端至少展示：

- 玩家角色核心状态。
- 在场 NPC 简略信息。
- 表情、情绪标签、关系倾向。
- 角色卡和状态表聚合后的可见状态。
- 当前目标或动机的用户可见摘要。

默认只读，编辑入口跳转 Dashboard 或打开受控轻编辑表单。不要把全部心理状态、隐藏目标、长期记忆命中无差别展示给玩家。

## 8. 状态管理与前端数据流

### 8.1 状态分层

| 状态类型 | 推荐位置 | 示例 |
|---|---|---|
| 客户端临时状态 | Zustand | `currentSceneId`、`selectedCharacterId`、`streamBuffer`、`pendingChoices`、`isGenerating`、`inputDraft`、`activePanel`、`visualMode` |
| 服务端状态 | TanStack Query | `sessions`、`sessionDetail`、`characterProfiles`、`saveSlots`、`userSettings`、`worldTemplates`、`purchaseStatus` |
| 本地草稿/离线缓存 | IndexedDB | 未发送草稿、长剧情缓存、图片/音频缓存、离线阅读记录、待同步操作队列 |
| 权威业务状态 | FastAPI + `rpg_core` | history、scene、status tables、character、lorebook、memory、summary |

不要把所有状态都放 Zustand，也不要在前端手写服务端状态同步逻辑。

### 8.2 推荐数据流

```text
User Action
  ↓
InputComposer 生成 structured action
  ↓
POST /api/session/:id/turn 或兼容期 POST /chat/stream
  ↓
Server 开始 Agent run / LLM / tool calling
  ↓
SSE 返回 CurrentAgentStreamEvent 或 RPGStreamEvent
  ↓
Client event reducer
  ↓
更新：
  - StoryTimeline
  - ScenePanel
  - CharacterPanel
  - ChoiceCards
  - PixiStage（可选）
  - StreamStatus
  ↓
turn.done 后刷新 history / scene / snapshot / session meta
```

事件 reducer 示例：

```ts
function reduceEvent(state: RuntimeState, event: RPGStreamEvent) {
  switch (event.type) {
    case "narration.delta":
      state.timeline.appendDelta("narration", event.text);
      break;
    case "dialogue.delta":
      state.timeline.appendDialogueDelta(event.speakerId, event.text);
      break;
    case "scene.patch":
      state.scene = { ...state.scene, ...event };
      break;
    case "character.patch":
      state.characters[event.id] = {
        ...state.characters[event.id],
        ...event,
      };
      break;
    case "choice.list":
      state.choices = event.choices;
      break;
  }
}
```

## 9. 后端 API 需求与演进计划

### 9.1 已有可复用 API

| API | 用途 | 状态 |
|---|---|---|
| `GET /chat/history` | 读取当前 agent history | 已有，偏 chat 调试 |
| `POST /chat/send` | 非流式发送消息 | 已有 |
| `POST /chat/stream` | SSE 流式发送消息 | 已有，MVP 可复用 |
| `POST /chat/command` | 执行 slash command | 已有 |
| `GET /chat/commands` | 获取命令列表 | 已有 |
| `GET/POST/DELETE /workspaces/.../sessions` | session 列表、创建、删除 | 已有 |
| `POST /workspaces/.../sessions/{id}/clone` | session 克隆 | 已有，可作为分支雏形 |
| `status` CRUD | 状态类型和 CSV 表 CRUD | 已有 |
| `character/lorebook/workspace` CRUD | Dashboard 数据管理 | 已有基础 |

### 9.2 待补 API

| API 能力 | 建议接口 | 用途 | 优先级 |
|---|---|---|---|
| 当前场景聚合读取 | `GET /api/sessions/{id}/scene` | Play HUD / Dashboard Scene Editor | P0 |
| 当前场景受控更新 | `PATCH /api/sessions/{id}/scene` | 更新时间、地点、在场人物、短期属性 | P0 |
| session rename/title | `PATCH /api/sessions/{id}` | 存档管理体验 | P0 |
| Play turn API | `POST /api/sessions/{id}/turn` | structured action + typed event stream | P0/P1 |
| stop generation | `POST /api/sessions/{id}/stop` | 停止生成 | P0/P1 |
| retry turn | `POST /api/sessions/{id}/retry` | 重试上一轮或指定 turn | P1 |
| history CRUD | `GET/PATCH/DELETE /api/sessions/{id}/turns` | 回滚、编辑、删除后续 | P1 |
| fork session | `POST /api/sessions/{id}/fork` | 从 turn 分支 | P1 |
| snapshot | `POST/GET /api/sessions/{id}/snapshots` | 回滚/存档点 | P1 |
| context preview | `GET /api/sessions/{id}/context-preview` | Dashboard 诊断 | P1 |
| memory recall preview | `POST /api/sessions/{id}/memory/preview` | Dashboard 诊断 | P1 |
| channel binding CRUD | `/api/channel-bindings` | Telegram 与 WebUI 共享 session | P1 |
| notification event API | `/api/notifications` | Telegram/PWA 推送 | P2 |
| RP module state API | `/api/sessions/{id}/modules/*` | 骰子、战斗、任务等机制面板 | P2 |

### 9.3 后端实现注意事项

- 场景 HUD 的权威数据来自 `SceneTracker` / `当前场景.csv` 对应能力，前端只展示并通过受控 API 修改，不直接写文件。
- `当前场景.csv` 是高优先级 scene 状态，应作为 user prefix 进入最终用户消息，不能被当成普通状态表随意注入或隐藏。
- history CRUD 必须保持 `turn_id`、`seq_in_turn`、`session.json` 的一致性；删除后续或回滚后需要明确是否同时回滚 scene/status/module state。
- 分支可先复用 session clone，再在 metadata 中记录 `forked_from_session_id`、`forked_from_turn_id`、`fork_label`。
- typed event adapter 不应把 HTTP 细节写入 `rpg_core`；可以先在 API 层转换，稳定后再下沉为核心事件模型。
- RP Modules 不是通用 skill 体系；骰子、战斗、物品等能力应围绕 RP 工具流程和受控状态读写设计。

## 10. Telegram 联动需求

Telegram 的产品定位是 companion channel：

- 推送：剧情生成完成、异步事件、任务完成、系统提醒。
- 快速回复：用户在 Telegram 回复一句，写入绑定 session。
- Deep link：Telegram 消息按钮跳转 Play WebUI 当前 workspace/session。
- 兜底：Play WebUI 不可用时仍可进行最小文本 RP。

关键要求：

- Telegram chat 必须能绑定到明确的 workspace/session。
- 绑定关系不应写入临时运行状态，应落盘到受控配置或数据文件。
- Telegram 输入与 Play WebUI 输入进入同一 session history。
- Play WebUI 应能标识消息来源，例如 `source=telegram`。
- Dashboard 提供绑定管理和测试推送，Play 只做跳转接续和来源标识。

## 11. 推荐目录结构

Play WebUI 默认架构：

```text
rpg_world/
  webui/                       # Dashboard WebUI 当前目录
  play_webui/                  # Play WebUI 独立 Next.js 项目
    app/
      session/[id]/page.tsx
      session/[id]/branch/page.tsx
      character/[id]/page.tsx
      world/[id]/page.tsx
      settings/page.tsx
    components/
      runtime/
        StoryTimeline.tsx
        InputComposer.tsx
        ChoiceCards.tsx
        ScenePanel.tsx
        CharacterPanel.tsx
        RuntimeToolbar.tsx
        StreamStatus.tsx
      visual/
        PixiStage.tsx
        CharacterSprite.ts
        BackgroundLayer.ts
      system/
        ErrorBoundary.tsx
        ReconnectBanner.tsx
        DebugEventPanel.tsx
    stores/
      runtimeStore.ts
      uiStore.ts
    queries/
      sessions.ts
      characters.ts
      worlds.ts
    lib/
      rpg-events.ts
      stream-client.ts
      snapshot.ts
      api-client.ts
  api/
  rpg_core/
  channels/
```

## 12. 分阶段实施计划

### M0：文档与路线对齐（当前）

**目标**：明确 Dashboard / Play 拆分、Play 默认技术栈、与 `rpg_core` 的边界、API 缺口和验收路径。

**任务**：

- 更新本 PRD，吸收 Play WebUI 选型和互动叙事需求。
- 明确 Dashboard 继续后台化，Play 独立前台化。
- 梳理现有 API / `rpg_core` 能力与缺口。
- 将“不做完整游戏化，先做交互增强”写入非目标。

**验收**：

- PRD 中包含技术选型、领域对象、后端映射、API 演进、里程碑、验收标准。
- 后续 M1/M2 可以直接拆 issue。

### M1：Dashboard 稳定化与 API 契约补齐

**目标**：让现有 `rpg_world/webui` 成为稳定 Dashboard，并补齐 Play MVP 依赖的基础 API。

**任务**：

- 梳理当前 Dashboard 导航与页面命名，明确其后台定位。
- 补齐 workspace/session/character/lorebook/status 基础 CRUD 的前后端契约测试。
- 增加 Scene Editor：读取/更新 `当前场景.csv` 的受控 API 与 UI。
- 增加 session rename/title 能力。
- 增加基础 chat 调试页和 SSE debug，不追求沉浸式体验。
- 输出 OpenAPI / typed API client 的生成或维护方案。

**验收**：

- Dashboard 能创建/切换 workspace。
- Dashboard 能管理 session，至少支持创建、删除、克隆、重命名或标题编辑。
- Dashboard 能 CRUD 角色卡、世界书和状态表。
- Dashboard 能查看/编辑当前场景。
- Dashboard 能查看 chat history 并发送测试消息。
- API 契约测试覆盖新增/调整接口。

### M2：Play WebUI MVP（文字互动叙事）

**目标**：新增 `play_webui`，实现可用的沉浸式文字 RP 主流程。

**任务**：

- 创建 Next.js + React + TypeScript 项目。
- 接入 shadcn/ui、Tailwind、Zustand、TanStack Query。
- 实现 Home / Continue 与 `/session/[id]` Play Room。
- 兼容接入 `/chat/stream`、`/chat/history`、`/chat/commands`。
- 实现 `CurrentAgentStreamEvent` 到 UI state 的 reducer。
- 实现 StoryTimeline、InputComposer、ScenePanel、CharacterPanel、StreamStatus、DebugEventPanel。
- 实现移动端基础布局。
- 支持停止生成的 UI 占位；若后端 stop API 未完成，则明确显示“不支持中断，仅可等待完成/刷新恢复”。
- 支持复制、收藏本轮输出的前端本地能力。

**验收**：

- 用户打开 Play WebUI 后可以选择 workspace/session 并继续 RP。
- 主聊天支持稳定流式输出，断线或 error event 不会清空已生成片段。
- 当前场景 HUD 与后端 `当前场景` 数据同步展示。
- 移动端可完成普通游玩。
- 不进入 Dashboard 也能完成普通 RP 输入、继续、查看场景和角色状态。

### M3：Typed Event Stream 与 Turn 级控制

**目标**：从“流式聊天”升级为“typed event 驱动的 RPG 运行时”。

**任务**：

- 设计并落地 `RPGStreamEvent` schema。
- 新增 Play turn API：structured action 输入 + typed event SSE 输出。
- 将通用 agent events 映射为 narration/status/tool events。
- 将 scene tool 或 scene reload 结果映射为 `scene.patch`。
- 建立 Turn 级 metadata：source、input mode、style controls、event list、snapshot id。
- 实现 stop/retry/continue 的后端支持。
- 在 Play WebUI 中替换兼容 reducer 为 typed event reducer。

**验收**：

- UI 不再依赖整段 markdown 后处理来识别系统事件。
- 旁白、工具状态、场景 patch、选项、角色 patch 可以分区域更新。
- 单轮失败时能保留已经收到的 event。
- stop/retry/continue 行为有明确 API 和 UI 状态。

### M4：分支、回滚、剧情日志

**目标**：解决 LLM 即兴“跑偏”后的可控性，让用户像视觉小说一样 SL。

**任务**：

- 实现 Turn 列表 API、按 turn 删除后续、编辑/改写本轮。
- 实现 fork session：从指定 turn 复制历史和必要状态。
- 实现 snapshot：保存/恢复 history + scene/status/module state 的一致性方案。
- Play WebUI 增加 Branch UI、Journal、关键事件收藏和导出。
- Dashboard 增加 history CRUD / branch debug 入口。

**验收**：

- 用户可从任意可见 Turn 分支出新 session。
- 用户可回滚到指定 Turn 并删除后续。
- 回滚/分支后 scene HUD 不出现明显与剧情矛盾的旧状态；若状态无法自动回滚，UI 必须标记需手动校正。
- Journal 可按时间、角色或关键事件浏览。

### M5：沉浸式增强与首批 RP Modules

**目标**：在不进入完整游戏工程复杂度的前提下增强沉浸感。

**任务**：

- 增加 ChoiceCards、角色表情/情绪标签、关系值、背包/任务简表。
- 实现骰子/检定/轻战斗/物品等首批 RP Module UI。
- 可选引入 PixiJS 演出层：背景、立绘、表情、粒子、过场。
- 增加 TTS / 语音输入可行性评估，不作为核心依赖。
- 支持世界模板和 UGC 角色/副本编辑器的需求拆分。

**验收**：

- 首批 RP Module 的状态读写都经过后端受控 API 和工具流程。
- 视觉增强层可关闭，关闭后文字 RP 主流程仍完整可用。
- PixiJS 只负责画面表现，不接管业务状态和路由。

### M6：渠道绑定与推送

**目标**：让 Telegram 成为 Play WebUI 的 companion channel。

**任务**：

- 实现 channel binding CRUD。
- Telegram 支持绑定、解绑、查看当前绑定。
- Telegram 支持剧情完成/异步事件推送和 deep link。
- Play WebUI 显示跨渠道消息来源。
- Dashboard 提供绑定管理和测试推送。

**验收**：

- Telegram chat 能绑定到 Play WebUI 的 workspace/session。
- Telegram 快速回复进入同一 session history。
- Telegram 能发送跳转 Play WebUI 的链接。
- Telegram 不承担复杂数据管理 UI。

## 13. 总体验收标准

### 13.1 Play WebUI MVP

- 用户可以选择世界/工作区与存档继续 RP。
- 主聊天支持稳定 SSE 流式输出。
- 当前场景 HUD 与对话同步展示。
- 用户能切换 IC/OOC/GM 指令或 Slash command 输入模式。
- 用户能继续、重试、停止或看到明确的暂不支持提示。
- 移动端可用。
- 普通游玩不依赖 Dashboard。
- 错误恢复不丢失已生成片段。

### 13.2 Dashboard WebUI MVP

- 能创建/切换 workspace。
- 能管理 session。
- 能 CRUD 角色卡、世界书和状态表。
- 能查看/编辑当前场景。
- 能查看 chat history 并发送测试消息。
- 能查看基础上下文/事件/工具调用诊断。

### 13.3 后端/API

- 新增 API 有 `api/tests/` 契约测试。
- 修改 session/history/scene/context/memory 行为时有 `rpg_core/tests/` 覆盖。
- `/chat/stream` 兼容旧前端，新的 typed event API 不破坏 Dashboard 调试能力。
- 所有 WebUI 操作都通过 FastAPI 和 `rpg_core` 受控能力完成，不直接读写运行数据文件。

## 14. 当前不建议一开始做的事

- 不要一开始做复杂 3D 或完整地图游戏。
- 不要所有输出都走 markdown；markdown 可以保留给旁白，但系统事件、角色状态、选项、道具、骰子、记忆命中应结构化。
- 不要把系统 prompt 编辑器暴露给普通用户；应包装成世界风格、角色性格、互动边界、剧情节奏、亲密程度、危险程度、幽默程度等配置。
- 不要过早做计划跟踪 UI、Agent DAG、planner timeline。
- 不要让 PixiJS / Phaser 接管业务状态；业务权威仍在 FastAPI + `rpg_core`。

## 15. 最终建议

当前阶段最合理的路线是：

```text
Dashboard：Vue 3 + Vite + Ant Design Vue + Pinia，继续后台化和稳定化。
Play：Next.js + React + TypeScript
  + AI SDK
  + shadcn/ui + Tailwind + Radix
  + Zustand for runtime state
  + TanStack Query for server state
  + SSE for LLM/event streaming
  + PixiJS only when 需要视觉小说表现
  + Phaser only when 已经是网页游戏
```

这套方案的优势是：MVP 快、生态成熟、AI 流式 UI 好做、后续可扩展到视觉小说或轻游戏，不会一开始就被游戏引擎复杂度绑死，同时能与现有 `rpg_core` 的 Agent、Session、Scene、Status、Memory、Summary 和 Tool 架构保持清晰边界。
