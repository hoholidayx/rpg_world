# RPG World WebUI 产品需求文档

## 1. 背景与结论

RPG World 的长期目标是构建一个 **AI RPG World / 沉浸式 RP 平台**。现有 Telegram 渠道适合轻量交互和 App 推送，但不适合承载复杂的角色卡、世界书、状态表、场景 HUD、剧情日志、玩法模块和多面板沉浸式体验。

因此 WebUI 后续应成为主体验，并拆分成两个独立 Web 项目：

1. **Dashboard WebUI（后台管理端）**：面向创作者、GM 和系统维护者。
2. **Play WebUI（前台游玩端）**：面向玩家，承载沉浸式 RP 聊天与游玩体验。

Telegram 保留为轻量入口、推送通知、快速回复和兜底交互。CLI 保留为开发调试和最小交互入口。

## 2. 产品目标

### 2.1 总目标

- 让 RPG World 从“多渠道聊天机器人”升级为“可长期运行、可管理、可沉浸游玩的 AI RPG 世界”。
- WebUI 负责体验上限，Telegram 负责触达效率。
- Dashboard 与 Play 前端独立演进，但共享 FastAPI / `rpg_core` 后端能力。
- 所有渠道共享 workspace/session 语义，避免同一故事在不同入口分裂。

### 2.2 非目标

- 不在 Telegram 中实现复杂 dashboard、地图、战斗面板、状态表编辑器等重 UI。
- 不在前端复制角色卡、世界书、状态表、记忆、摘要和 RP 机制的核心业务规则。
- 第一阶段不做多人实时协作、公共房间或商业化账号系统。
- 第一阶段不做完整规则书复刻；玩法模块先围绕轻量、可审计、可测试机制建设。

## 3. 项目拆分

### 3.1 Dashboard WebUI

**定位**：数据管理、创作维护、配置诊断后台。

**建议目录**：继续使用当前 `rpg_world/webui`，或后续重命名为 `rpg_world/dashboard_webui`。

**核心用户**：

- 世界/剧本创作者。
- GM / 管理员。
- 调试 Agent 行为的开发者。

**核心场景**：

- 创建和切换 workspace。
- 管理 session / 存档。
- 编辑角色卡、世界书、状态表。
- 查看和修正当前场景。
- 查看对话历史、摘要、记忆和上下文诊断。
- 管理 LLM / 模块 / 渠道相关配置。

### 3.2 Play WebUI

**定位**：玩家前台、沉浸式 RP 主客户端。

**建议目录**：新增 `rpg_world/play_webui`，作为独立 Vite 项目。

**核心用户**：

- 玩家。
- 只想“进入故事”的用户。
- 移动端或平板上的轻量游玩用户。

**核心场景**：

- 选择一个世界和存档并继续游玩。
- 在沉浸式聊天界面中与 GM / NPC 互动。
- 查看当前场景、时间、地点、天气、在场角色和短期状态。
- 使用快捷行动、OOC 输入、命令面板、骰子/检定/战斗等 RP 模块。
- 浏览剧情日志、分支、摘要和关键事件。
- 从 Telegram 推送跳转回当前场景。

## 4. 信息架构

### 4.1 Dashboard WebUI 页面

| 页面 | 说明 | 优先级 |
|---|---|---|
| Overview | 当前 workspace 概览、数据健康、最近 session | P0 |
| Workspaces | 工作区创建、重命名、删除、切换 | P0 |
| Sessions | 存档列表、创建、克隆、删除、历史查看 | P0 |
| Characters | 角色卡 CRUD、预览、校验 | P0 |
| Lorebook | 世界书 CRUD、关键词、启用状态 | P0 |
| Status Tables | 状态类型/CSV 表 CRUD、当前场景入口 | P0 |
| Memory & Summary | 记忆索引、摘要文件、召回诊断 | P1 |
| Context Inspector | 当前 prompt/context 预览、token 估算 | P1 |
| Settings | API、LLM、渠道、模块配置查看与校验 | P1 |
| Channel Bindings | Telegram chat 与 workspace/session 绑定管理 | P1 |

### 4.2 Play WebUI 页面

| 页面 | 说明 | 优先级 |
|---|---|---|
| Home / Continue | 选择最近世界与存档，继续游玩 | P0 |
| Play Room | 主 RP 体验页：聊天、场景 HUD、角色面板 | P0 |
| Journal | 剧情日志、摘要、关键事件、分支回顾 | P1 |
| Character Sheet | 玩家角色/NPC 只读或轻编辑视图 | P1 |
| Scene Details | 当前场景详情、线索、可交互对象 | P1 |
| Mechanics Panel | 骰子、检定、战斗、物品、任务等模块入口 | P2 |
| Mobile Quick Play | 窄屏优化布局 | P0 |

## 5. Play WebUI 核心体验要求

### 5.1 主布局

桌面端建议三栏结构：

```text
┌──────────────┬──────────────────────────────┬──────────────────┐
│ 世界/存档栏   │         RP 主聊天区           │ 场景/角色/机制栏  │
│ session list │  narrative + user actions     │ HUD + panels      │
└──────────────┴──────────────────────────────┴──────────────────┘
```

移动端建议单栏 + 底部 Tab：

```text
Play | Scene | Characters | Journal | Actions
```

### 5.2 聊天交互

- 支持 SSE / WebSocket 流式输出。
- 支持停止生成、重试、复制、收藏关键回复。
- 支持输入模式切换：
  - IC 行动/发言。
  - OOC 说明。
  - GM 指令。
  - Slash command。
- 支持快捷行动按钮，例如“观察四周”“询问 NPC”“继续前进”。
- 支持工具调用可视化，但默认不破坏沉浸感；详细工具记录放入可展开调试区域。

### 5.3 场景 HUD

必须常驻展示：

- 当前时间。
- 当前地点。
- 天气/季节。
- 在场人物。
- 当前场景短期属性。
- 最近一次状态变化。

场景 HUD 的权威数据来自 `SceneTracker` / `当前场景.csv` 对应后端能力，前端只展示和通过受控 API 修改，不直接写文件。

### 5.4 角色与 NPC 面板

- 展示玩家角色核心状态。
- 展示在场 NPC 简略信息。
- 支持从角色卡和状态表聚合展示。
- 默认只读，编辑入口跳转 Dashboard 或打开受控轻编辑表单。

### 5.5 剧情日志

- 按 session 展示完整历史。
- 支持按章节、时间、地点、角色过滤。
- 支持摘要视图与完整对话视图切换。
- 支持关键事件标记。

## 6. Dashboard 核心体验要求

### 6.1 数据管理

Dashboard 负责所有结构化数据的权威编辑入口：

- workspace。
- session。
- character。
- lorebook。
- status tables。
- scene runtime。
- memory / summary。

### 6.2 诊断能力

Dashboard 应提供 Play WebUI 不暴露或默认隐藏的诊断信息：

- 当前上下文结构。
- token 预算。
- 召回记忆列表。
- 世界书命中结果。
- 状态表注入情况。
- 工具调用记录。
- LLM stats。

### 6.3 配置与渠道绑定

Dashboard 管理 Telegram 与 WebUI 的协作关系：

- 查看 Telegram bot 配置摘要。
- 绑定 Telegram chat_id 到 workspace/session。
- 解除绑定。
- 发送测试推送。
- 查看最近渠道消息。

## 7. 后端需求

### 7.1 已有可复用能力

当前 FastAPI 已具备以下基础能力：

- chat send / stream / history / commands。
- workspace list/create/rename/delete。
- session list/create/delete/clone。
- character / lorebook / status CRUD。

### 7.2 待补 API

| API 能力 | 用途 | 优先级 |
|---|---|---|
| 当前场景读取/更新聚合接口 | Play HUD / Dashboard Scene Editor | P0 |
| session rename | 存档管理体验 | P0 |
| history CRUD / branch support | 回滚、编辑、分支重跑 | P1 |
| context preview | Dashboard 诊断 | P1 |
| memory recall preview | Dashboard 诊断 | P1 |
| channel binding CRUD | Telegram 与 WebUI 共享 session | P1 |
| notification event API | Telegram/PWA 推送 | P2 |
| RP module state API | 骰子、战斗、任务等机制面板 | P2 |

## 8. Telegram 联动需求

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

## 9. 技术建议

### 9.1 前端技术栈

当前 Dashboard WebUI 使用 Vue 3 + Vite + Ant Design Vue + Pinia。后续可以：

- Dashboard 继续沿用 Vue + Ant Design Vue，适合表单、表格、CRUD 和后台管理。
- Play WebUI 可以独立选择更适合沉浸式体验的技术栈；若希望复用团队经验，可继续 Vue；若希望组件生态和动效更丰富，也可单独评估 React。

无论技术栈如何，两个前端项目应共享：

- OpenAPI / typed API client。
- 数据类型定义。
- 鉴权和 workspace/session 选择约定。
- Markdown / RP 文本渲染规范。

### 9.2 构建与部署

建议最终支持三种部署方式：

1. **开发模式**：API、Dashboard、Play 三个 dev server 独立启动。
2. **单机模式**：FastAPI 静态托管 Dashboard 和 Play 构建产物。
3. **分离模式**：Dashboard / Play 独立部署，统一访问同一个 API 服务。

### 9.3 目录建议

```text
rpg_world/
  webui/                 # Dashboard WebUI 当前目录
  play_webui/            # Play WebUI 独立项目，后续新增
  api/
  rpg_core/
  channels/
```

如后续需要更明确命名，可迁移为：

```text
rpg_world/
  dashboard_webui/
  play_webui/
```

## 10. 里程碑

### M0：文档与路线对齐

- 更新 README / CLAUDE / Telegram 计划 / AGENTS 路线说明。
- 明确 Dashboard 与 Play 拆分。
- 产出本 PRD。

### M1：Dashboard 稳定化

- 梳理当前 `rpg_world/webui` 为 Dashboard WebUI。
- 补齐 workspace/session/character/lorebook/status 基础 CRUD。
- 增加场景编辑入口。
- 增加基础 chat 调试页，但不追求沉浸式体验。

### M2：Play WebUI MVP

- 新增独立 `play_webui` 项目。
- 实现 Home / Continue 与 Play Room。
- 接入 `/chat/stream`、`/chat/history`、`/chat/commands`。
- 实现场景 HUD 与移动端基础布局。
- 支持 session 切换和最近存档。

### M3：渠道绑定与推送

- 实现 Telegram chat 与 workspace/session 绑定。
- Telegram 支持推送与 deep link。
- Play WebUI 显示跨渠道消息来源。

### M4：沉浸式增强

- 剧情日志和关键事件。
- 角色/NPC 面板。
- 上下文/记忆摘要可视化。
- 骰子、检定、任务等首批 RP Module UI。

## 11. 验收标准

### Dashboard WebUI MVP

- 能创建/切换 workspace。
- 能管理 session。
- 能 CRUD 角色卡、世界书和状态表。
- 能查看/编辑当前场景。
- 能查看 chat history 并发送测试消息。

### Play WebUI MVP

- 用户打开后可以选择世界与存档继续 RP。
- 主聊天支持稳定流式输出。
- 当前场景 HUD 与对话同步展示。
- 移动端可用。
- 不需要进入 Dashboard 也能完成普通游玩。

### Telegram Companion MVP

- Telegram chat 能绑定到 Play WebUI 的 workspace/session。
- Telegram 快速回复进入同一 session history。
- Telegram 能发送跳转 Play WebUI 的链接。
- Telegram 不承担复杂数据管理 UI。
