# RPG World — 故事数据管理与 LLM Agent 交互子系统

RPG World 是 nanobot 项目的一个子系统，专注于故事驱动的 RPG 数据管理和 LLM Agent 交互。提供角色卡管理、世界书管理、状态表管理、场景上下文构建、记忆召回与 RP 模块运行态等功能。

## 目录

- [产品路线与定位](#产品路线与定位)
- [近期架构变更记录](#近期架构变更记录)
- [快速起步](#快速起步)
- [架构](#架构)
  - [进程隔离架构](#进程隔离架构)
  - [Play 会话与数据目录](#play-会话与数据目录)
  - [Agent 组合式门面与 turn 事务](#agent-组合式门面与-turn-事务)
  - [Agent Turn 完整编排（独立文档）](docs/agent-turn-orchestration.md)
  - [上下文与 RP 模块](#上下文与-rp-模块)
- [记忆系统](#记忆系统)
- [配置](#配置)
- [Session ID 规则](#session-id-规则)
- [测试](#测试)
- [当前实现优先级](#当前实现优先级)
- [相关文档](#相关文档)

## 产品路线与定位

RPG World 的长期产品目标是成为一个 **AI RPG World / 沉浸式 RP 平台**，而不是单一聊天机器人。后续体验重心调整为：

- **Play WebUI（前台游玩端）**：主客户端，承载沉浸式 RP 聊天、场景状态、玩家扮演角色、角色/NPC 面板、剧情日志、行动输入、骰子/战斗/物品等玩法机制。
- **Telegram**：轻量入口、App 推送、快速回复和兜底交互；不再作为复杂沉浸式 UI 的主要承载面。
- **CLI**：开发调试和最小交互入口。

设计原则：Play WebUI 负责 Web 主体验和管理入口，Telegram 负责触达效率；二者必须共享同一套 workspace/session 语义，避免同一个故事在不同渠道分裂。Play WebUI 通过 Play API 复用 `rpg_core`、`rp_memory` 和 `rpg_data` 后端能力，不在前端复制角色、世界书、状态或 RP 规则。

## 近期架构变更记录

- **2026-07-13：Agent Turn 与状态更新固定编排。** Narrative Outcome 与状态更新拆分为独立阶段；状态更新先 Route，再按 scene 和单张普通表隔离执行。快速状态目标采用 best-effort：单个目标失败只回退该目标，其他成功目标保留且主流程继续；整个 turn 仍只在主 runner 成功后统一提交。字段频率统一为 `realtime | event_driven | deferred | manual`，其中 deferred 在回复交付后、同 session 下一 mailbox 项前归纳。scene 继续以 `status_kind="scene"` 作为数据真源，但在主 Context 和更新工具上走专用路径。完整设计、时序和失败语义见 [Agent Turn 与状态更新编排](docs/agent-turn-orchestration.md)。

## 快速起步

```bash
# 安装依赖
uv sync

# 启动 Agent 服务（唯一持有 AgentManager/RPGGameAgent/rp_memory 运行时）
uv run python -m run_agent

# 按需在其它终端启动独立入口
uv run python -m run_play_api
uv run python -m run_telegram
uv run python -m run_cli

# CLI / Telegram / API 都通过 agent_client 访问 Agent 服务
uv run python -m channels.cli.repl

# 直接调试 API（自动重载）
uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir channels --reload-dir rpg_core --reload-dir rp_memory --reload-dir llm_service --host 127.0.0.1 --port 8000

# 启动 Play WebUI（另一个终端）
cd play_webui && npm run dev
```

根目录聚合 supervisor 入口已移除。配置已按进程/模块拆分到各自目录；进程是否启动只由用户运行哪个
`run_*` 入口决定，不再通过配置启停进程。

## 架构

### 进程隔离架构

RPG World 采用单 Agent 服务拓扑。只有 `run_agent.py` 进程持有
`AgentManager`、`RPGGameAgent`、`rp_memory` 和 llama lazy worker。Play API、
CLI、Telegram 只通过 `AgentClient` 调用 Agent 服务。

```
run_agent          -> agent_service.main:app
run_play_api       -> play_api.main:app      -> AgentClient
run_cli            -> channels.cli.repl      -> AgentClient
run_telegram       -> channels.telegram.runner -> AgentClient
```

根目录还提供同级快捷入口，便于调试和查找：

```
run_agent.py    -> agent_service.main
run_play_api.py -> play_api.main
run_telegram.py -> channels.telegram.runner
run_cli.py      -> channels.cli.repl
```

服务、渠道和客户端配置分别由对应模块的 YAML 管理，所有配置字段都封装为类型化属性：

```python
from channels.config import settings as cfg
from agent_service.settings import settings as agent_cfg
from play_api.settings import play_settings

agent_cfg.service.port
agent_cfg.agent_client.base_url
play_settings.service.port
cfg.telegram_bots
cfg.cli_workspace_id
cfg.cli_story_id
```

### 多渠道适配器

CLI / Telegram 等消息渠道继承同一抽象基类 `ChannelAdapter`；Play WebUI 不继承该基类，而是通过 Play API 调用 Agent service：

| 渠道 | 实现 | 技术栈 |
|---|---|---|
| CLI | `channels/cli/adapter.py` | Rich + prompt_toolkit |
| Telegram | `channels/telegram/adapter.py` | python-telegram-bot |
| Play WebUI | Next.js App Router + React + TypeScript，经 Play API/SSE 访问后端 | 沉浸式主客户端 |
| 未来消息渠道 | 只需继承 ChannelAdapter | 实现 start/stop/send_text 即可 |

当前路线调整为 Play WebUI 主体验、Telegram 辅助触达：Play WebUI 同时负责沉浸式 RP、数据管理和调试入口。Telegram 继续保持稳定可用，作为轻量入口、推送通知、快速回复与兜底渠道。

### Play 会话与数据目录

Play WebUI 使用 `rpg_data` 作为故事 catalog。数据模型是：

- 1 个 workspace 下可以有多个 story。
- 1 个 story 下可以有多个 session。
- Story 主数据中，`summary` 是短摘要，`first_message` 是会话开场首条消息模板，`story_prompt` 是 story 专属固定系统提示词。两类模板当前只支持 `{USER_PLAY_ROLE_NAME}` 白名单变量，数据库与 API 始终返回原始模板；未知变量在保存时返回校验错误，不执行 Jinja、表达式或递归替换。首消息在首次成功绑定且历史为空时渲染，Story Prompt 在每个 turn 的不可变 snapshot 中渲染一次。当前硬切换 schema 变更直接体现在 `0001_initial.sql`，demo 与分页测试数据分别放在 `0002_demo.sql`、`0003_pagination_demo.sql`；`0007_player_role_templates.sql` 只条件更新仍保持旧默认值的 Demo 数据。
- 角色卡和世界书条目属于 workspace，通过挂载表关联到 story；同一个角色卡或世界书条目可以挂载到多个 story。
- 状态表模板属于 workspace，通过 `rpg_story_status_tables` 挂载到 story；挂载记录可选绑定同一 story 的一个角色。一个角色可绑定多张状态表，但单张 story 状态表挂载最多绑定一个角色。
- Play 侧公开 `session_id` 是全局唯一短 ID，创建入口由 `rpg_data` 生成，当前生成格式为 `s_` + 10 位小写字母/数字；创建 session 时绑定 `workspace_id + story_id`，之后会话内接口只传 `session_id`。
- CLI / Telegram 启动时也先通过 Agent service 的 `ensure_session(workspace_id, story_id, session_id, title)` 解析会话；`session_id` 为空时创建系统生成 ID 的 session，非空时只校验并加载既有 session。
- `rpg_session_profiles` 保存会话标题、描述、`player_character_id` 和 `player_character_snapshot_json`；`rpg_sessions.id` 保持稳定，用作 URL 和 Agent session id。

玩家扮演角色绑定是 session 级能力：

- 状态只暴露 `bound | invalid`。缺失绑定、角色不存在、未挂载到当前 story、snapshot 损坏或 snapshot mount/story 不匹配，都统一视为 `invalid`。
- Play WebUI 新建或进入 session 后统一在 SessionRoom 内处理选角；invalid 时打开不可取消弹窗，绑定前禁用输入区。设置菜单可以切换当前扮演角色，切换只影响后续 user 消息展示和后续 prompt 语义，不重写历史。
- CLI / Telegram / Agent API 允许建立空 session；绑定前普通消息只返回固定编号角色列表，不调用 LLM、不写 user history。
- 绑定与切换统一走 Agent 命令 `/role_bind <序号>`。WebUI 的 `PATCH /play-api/v1/sessions/{session_id}/player-character` 会转发到 Agent service，由 Agent service 将角色 ID 映射为当前 story 已挂载角色序号并执行同一命令；不要在 Play API/DataManager 中直接写绑定。
- 首次成功绑定且 main history 为空、story `first_message` 非空时，`SessionRoleService` 会按刚绑定的角色渲染模板，再将同一条 assistant 开场消息写入 main 和 backup history；已有 history 或后续切换角色时不会重复追加或改写。
- 玩家身份在 Context 门禁前固化进 `TurnExecutionSnapshot`，由门禁、主 Agent、StatusSubAgent 与 Context Preview 共用。fixed layer 的 `[player_character]` 标签块是身份唯一真源；角色卡只在 Context 投影时标注为 `PLAYER_CHARACTER` 或 `NPC`，不依赖角色 metadata。当前绑定覆盖冲突的旧历史、摘要和记忆，但不会自动改写这些既有数据。

Play API 是 catalog session 到 Agent 服务的边界层：它通过 `session_id` 反查 workspace/story，并只把全局 `session_id` 传给 Agent 服务运行态；Agent service 的 `/chat/history`、`/chat/commands`、`/chat/send`、`/chat/stream`、`/chat/stop` 不再接收 workspace。当前会话内接口集中在 `/play-api/v1/sessions/{session_id}/...`，例如 `history`、`history-page`、`scene`、`commands`、`turn`、`stream`、`stop`、`player-character`。workspace、characters、lorebook、status-tables、ops 等管理接口也在 Play API 下；旧的 `chat.py`、`scene.py`、`commands.py` router 只保留占位，不再挂载为主接口。

状态表在 `rpg_data` 中采用 SQLite document 真源：

- 模板表和会话表都在 SQL 行内保存封装后的 `document_json`，对外通过 `StatusTableDocument` / `StatusTableRow` 等 dataclass 暴露，不把原始 JSON 字符串作为正文数据返回。
- SQLite 同时记录模板、story 挂载、session 副本、来源关系、排序、`metadata_json` 和 `status_kind`；`status_kind` 当前只允许 `scene` / `normal`。
- 每个 `StatusTableRow` 可声明 `updateFrequency`、`updateRule` 和 `deferredIntervalTurns`。频率只允许 `realtime | event_driven | deferred | manual`；旧 document 缺少频率时按 `realtime` 读取，`event_driven` 必须填写非空规则，只有 `deferred` 可以配置正整数归纳周期。
- 字段频率对应实时、规则命中、延迟归纳和人工维护四种写入策略；Route、字段 allowlist、scene 特例和 deferred 时序统一见 [Agent Turn 完整编排](docs/agent-turn-orchestration.md#状态字段更新频率)。
- 状态表模板属于 workspace，通过 `rpg_story_status_tables` 挂载到 story 后才可绑定角色；绑定字段是 nullable `story_character_mount_id`，只校验角色挂载属于同一 story，不限制同一角色绑定的状态表数量。
- `rpg_story_status_tables.mount_origin` 区分 `system_mount` 与 `story_template`。系统模板挂载只能解除挂载；故事内创建的状态模板可删除挂载及其底层模板，若模板仍被其它 story 使用则拒绝删除。
- 创建 session 时会把当时已挂载模板的 `document_json` 复制到 `rpg_session_status_tables`，`origin="template_copy"`，并把 story mount、角色绑定和 `characterName` 快照写入 session 表 metadata；角色名只用于在 LLM 上下文中分组角色状态表。
- 角色绑定要求挂载角色具有非空 name。旧 session 缺少 `characterName` 时，context 读取优先通过 `characterMountId -> rpg_story_characters -> rpg_characters` 反查；缺少直接角色挂载 ID 时可由状态表 `mountId -> rpg_story_status_tables.story_character_mount_id` 回退解析，成功后回填快照。无法解析的角色状态表会记录 warning 并从 LLM 上下文排除。
- 模板后续修改不影响已有 session 副本；运行时直接新建的会话表写入 `rpg_session_status_tables`，`origin="session_native"`。
- migration `0008_status_update_frequency.sql` 新增 `rpg_session_status_deferred_progress`，以运行时表 ID + 字段 key 保存最后处理 turn。deferred 的 document 值与进度在同一数据库事务中提交；归纳失败不推进进度，truncate/clear 只收缩进度边界，不回滚已经提交的状态值。
- `DataServiceGateway` 初始化时只 materialize workspace/story/session 运行目录并初始化缺失的 session 状态表副本；service 不扫描目录补业务索引，也不维护状态表 type 表、workspace-relative 状态表文件路径或 CSV 内容源。
- Bootstrap 默认不删除不在 SQL 索引里的 workspace/story/session 目录。只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才会执行启动清理；日志会输出每个删除项和汇总计数。
- `当前场景` 是 `status_kind="scene"` 的特殊状态表，仍受 story 挂载约束；多张 scene 表存在时消费排序第一张。scene document 的所有字段固定为 `realtime`，保存边界拒绝 `event_driven` / `deferred` / `manual`。
- `rpg_data` 通过 `rpg_workspaces.root_path` 定位 workspace 根目录，workspace/story/session 运行目录使用 workspace-relative 路径时统一由 `rpg_data.settings` 解析并阻止路径逃逸。

Play WebUI 的状态表页分为 `系统模板`、`故事状态模板` 和 `故事运行时` 三个视图。`系统模板` 管理工作区级模板及其 story 挂载；`故事状态模板` 管理当前 story 已挂载模板、故事内创建模板和可选角色绑定；`故事运行时` 只管理当前 session 的运行时副本。

### Telegram 渠道

Telegram 渠道当前支持：

- 长轮询启动与优雅关闭。
- `streaming=true` 时由 Application 托管后台生成任务，通过占位消息和增量编辑实现流式输出。
- 同一 Telegram chat 或同一 session 同时只接受一个生成，新输入会立即提示忙碌而不进入 AgentMailbox 排队；当前不提供主动停止按钮或 `/stop` 命令。
- Markdown 到 Telegram HTML 的渲染与 4096 字符分块发送。
- `/start`、后端斜杠命令透传，以及 Telegram 菜单命令规范化。
- Inline Keyboard callback 使用带 10 分钟 TTL、chat/session 归属校验和一次性 claim 的短 token。
- 每个 bot 绑定 `workspace_id + story_id`，启动时解析一个默认 session；未 pin 的 chat 使用 bot 默认 session，显式切换后会在当前 chat 内钉住 session。
- `/sessions` 会话菜单、按钮切换会话、`/session_create [title...]` 立即创建系统生成 ID 的 session；`/cancel` 保留给 Telegram 专属二段交互状态。
- `proxy`、流式编辑间隔、最小编辑字符数、请求超时等参数由 `channels/settings.yaml` 的 bot 配置控制。

### 核心引擎

| 模块 | 说明 |
|---|---|
| `agent/agent.py` | `RPGGameAgent` 组合根与公开门面，只组装组件并委托公开 API |
| `agent/mailbox.py` / `session_service.py` / `lifecycle.py` | FIFO 队列与取消、会话操作、session-scoped runtime 生命周期 |
| `agent/model_runtime.py` / `context_service.py` / `tool_service.py` | 主模型选择与 provider cache、Context/门禁/预览、工具与 schema 装配 |
| `agent/turn/` | 单轮请求、不可变执行计划、固定阶段 hooks、运行态与同步/流式共享编排 |
| `context/` | 结构化 RPG 上下文构建、LLM 边界渲染、上下文诊断 |
| `scene/` | 场景状态跟踪（时间/地点/属性） |
| `character/` | 角色卡只读适配，通过 `rpg_data` 按 session/story 读取挂载 |
| `lorebook/` | 世界书只读适配，通过 `rpg_data` 按 session/story 读取挂载 |
| `status/` | 状态表薄适配，通过 `rpg_data` 按 session 读取 SQLite document 真源 |
| `rp_modules/` | RP 玩法模块框架，当前包含 Narrative Outcome 剧情裁定与 Dice 低层随机模块 |
| `summary/` | 对话摘要压缩 |
| 顶层 `llm_service/` | LLMProvider 抽象、OpenAI/llama provider、LLMManager、llm.yaml 解析与本地 llama runtime |

顶层 `rp_memory/` 是独立记忆系统包，负责检索、索引、规划、召回和 rerank；顶层 `llm_service/` 是统一 LLM 服务包，负责 provider 路由、配置解析、OpenAI-compatible provider 与本地 llama.cpp runtime。

### Agent 组合式门面与 turn 事务

`RPGGameAgent` 是组合根和公开门面，不再拥有队列、Context、工具、模型选择或 turn 阶段实现。公开接口保持 `send()`、`send_stream()`、`cancel_current_turn()`、命令、Context inspection、history、角色绑定和 reload/switch；内部稳定接口为幂等 `initialize()`、只读 `session_id` / `session_manager` 与 `reindex_memory()`。

```text
RPGGameAgent（composition root + public facade）
├── AgentMailbox              FIFO、stream task、requestId 取消、错误事件
├── AgentSessionService       角色、history、truncate/delete/clear、reload/switch
├── AgentRuntimeLifecycle     初始化、AgentContextResources、SubAgents、compressor、watcher
├── MainModelRuntime          MainLLMSelection、provider cache、当前模型
├── AgentContextService       fixed layer、Context 构建/预览、窗口门禁
├── AgentToolService          base/turn-local tools、主 schema 过滤
└── AgentTurnService
    └── TurnOrchestrator      同步/流式共享业务模板
```

`AgentContextResources` 是一次性替换的不可变引用集合，包含 builder、角色、世界书、状态、scene 与 memory manager。reload/switch 不再逐字段改写 Agent，也不会保留 `_rpg_ctx` 字典；生命周期组件重建整组资源后，显式重绑 SubAgent context/tool provider、memory stores、compressor、RP registry 与 base tools。

`send()` 和 `send_stream()` 共用同一业务 pipeline，只在最终输出适配上区分 `AgentReply` 与 SSE：

```text
Mailbox → 命令/角色 guard → 不可变 TurnExecutionPlan
→ Context 门禁 → transaction/scratch/RP runtime
→ Status preflight（Outcome → Route → scene/逐表 Update）
→ stage user + memory recall + 主 Context/工具
→ 主 runner → commit → 输出适配 / PostCommitHooks
→ 回复后的 deferred 归纳 → 同 session 下一 mailbox 项
```

这些 hook 是固定的类型化阶段，不是事件总线，不提供动态优先级、运行时重排或第三方注册。

三个 turn 对象对应不同生命周期，不能合并成可变的大 request：

- `TurnRequest` 只表示调用方要求，包含正文、mode、style override 和可选 request ID。
- `TurnExecutionSnapshot` / `TurnExecutionPlan` 保存门禁前解析完成的本轮选择，生成期间不可变化。
- `TurnRuntime` 持有 transaction、scratch、统计、preflight 结果和 RP Module runtime，负责统一 commit/discard/close。

turn 子系统只依赖显式的 plan resolver、runtime factory、Context/Tool service 与固定 hooks；生产代码通过公开接口协作，不访问 Agent、builder 或 SubAgent 私有状态。

`AgentTurnTransaction` 是“内存 scratch + 短 commit 点”，不是跨 LLM 调用的长数据库事务。user/assistant message、Narrative Outcome、scene/status 都先暂存；快速状态阶段按 scene/单表目标独立 checkpoint，目标失败只恢复该目标并继续后续目标及主 runner。主 runner 完整成功后才统一提交仍保留的 scratch，流式 DONE 只在 commit 成功后发送；主 turn 取消或失败仍丢弃全部 scratch。story-memory、summary 和 deferred 属于 commit 后任务，不回滚已提交 turn。

完整阶段顺序、mode 差异、Outcome/Route/Update 隔离、scene 规则、字段 allowlist、同步/流式时序、失败隔离和 LLM 调用数量见 [Agent Turn 与状态更新编排](docs/agent-turn-orchestration.md)。该文档是编排细节的单一说明入口。

### 上下文与 RP 模块

`rpg_core/context/` 的主流程保持结构化数据，直到发送给 LLM 前才由 Jinja2 模板统一渲染：

- `RPGContextBuilder` 消费预组装的 `FixedLayerData`，并负责摘要、记忆、状态表和用户扩展块，产出结构化 `RPGContext`。
- 主 Agent 的 `send()`、`send_stream()` 和 `context-preview` 统一通过 `SessionManager.context_history()` 读取历史投影：仅排除 `summary_processed=true` 的单条消息，不校验 `summary_batch_id`、batch 文件、`overall.md` 或 turn 完整性；当前 turn 的 user message 仍来自事务 scratch。
- `FixedLayerAssembler` 通过 contributors 统一装配固定层 section，例如核心 RP 指令、文本输出格式、世界书、角色卡和已启用 RP Module 的静态契约。
- `ContextRenderer` 只在 LLM 请求边界把结构化层渲染为 message objects。
- `ContextInspector` 只服务 `/context`、日志和调试输出，不进入主业务数据模型。
- `context/usage.py` 封装最终渲染 messages 的共享 token 估算和 provider usage 归一化。`context-preview` 只返回下一轮主 Context 估算并驱动圆环/正文门禁；准确 usage 只来自正常 `/turn` 返回或 `/stream` 的 `turn_completed.payload.usage`，仅用于回复气泡和详情复盘，当前不落库。
- 主 Agent LLM 选择使用 `config default < story override < session override`：Story 详情编辑页立即保存故事默认，SessionRoom context 圆环左侧设置会话覆盖；生成中切换只影响下一 turn，不触发自动压缩。
- `rpg_core/rp_modules/` 是 RP 业务模块体系，不做通用 skill 体系。`narrative_outcome` 负责主 Agent 的剧情分支随机裁定；`dice` 只保留表达式解析和手动调试命令；`text_output_format` 仍由 fixed layer contributor 约束 assistant 正文使用 RP XML 标签。
- 内置模块登记在 `rpg_rp_module_catalog`。Story 挂载是 Session 的能力上限，新 Story 默认挂载当前全部内置模块；Session 可覆盖模块启用状态和稀疏配置，但不能重新启用 Story 已停用的模块。每次 preview/turn 都解析独立不可变快照，生成中的配置修改只影响下一 turn。
- `RP_MODULES` 是模块动态运行态层，位置在 `STATUS_TABLES` 后、`USER_MESSAGE` 前。Narrative Outcome 平时依靠 fixed contract 判断隐式变数；检测到明确随机意图时加入本轮强制裁定指令；若 StatusSubAgent 已预裁定，则该层改为注入已生效结果和裁定后状态检查边界。

当前发送顺序按缓存稳定性和 RP 注意力组织：

1. Fixed Layer：固定 RP 指令、Story Prompt、当前玩家角色标签块、文本输出格式、已启用 RP Module 静态契约、世界书、带 PLAYER/NPC 标注的角色卡。
2. Persistent Memory / Summary。
3. Hot History。
4. Story Memory / Recalled Memory / Status Tables / RP Modules。
5. User Message。

`当前场景` 在数据层仍是必须挂载到 story 的 `status_kind="scene"` SQL document，在主 Context 中则是高优先级 `[scene]` user prefix，不进入普通 `STATUS_TABLES`。Status Route 只在本轮涉及 scene 时选择它，并使用专用 scene 工具；scene 不走普通表工具或 deferred。完整差异见 [scene 的特殊语义](docs/agent-turn-orchestration.md#scene-的特殊语义)。

普通 `STATUS_TABLES` 层展示 session 运行时表 ID、表名、`description`（用途与更新规则）和完整 KV，不展示模板来源或通用挂载范围。绑定角色的表单独进入“角色状态表”段落并按角色名分组；当前只用角色绑定辅助模型理解所属角色，不扩展其它行为。

RP Modules 采用上下文分层策略：

- 稳定、低频变化的规则只放进 fixed layer，例如 Narrative Outcome 的“何时裁定、必须调用工具、不得替玩家做选择”。
- 文本输出格式是默认启用的 fixed layer 约束；RP 正文使用 `<rp-narration>` 和 `<rp-character name="...">` 标签区分旁白与角色发言。
- 高频或临时模块状态才进入 `RP_MODULES` 动态层；Narrative Outcome 为明确随机意图加入本轮强制指令，并把 StatusSubAgent 已暂存的裁定结果注入主 Agent 首次调用。
- 未预裁定时，主 LLM 的 RP schema 只暴露高层 `rp_story_outcome(reason, actor?)`；已预裁定时该 schema 隐藏。两种情况都不暴露表达式、DC、随机数、权重或低层 Dice 工具。
- `/rp_modules`、`/rp_module` 始终由 `CommandDispatcher` 在 LLM 前拦截；`/roll`、`/check_dc` 只在当前 Story/Session 的 Dice 模块有效启用时动态出现。所有命令都不进入对话历史。

#### Narrative Outcome：五级剧情分支随机机制

当前产品需要的是剧情方向上的受控随机，而不是完整 TRPG 数值系统。系统每轮结合用户完整语义、当前场景和状态判断是否存在“外部实质变数”：同一行动或场景反应存在两个以上合理结果、结果尚未被上下文唯一确定，并受未知信息、能力、阻力、风险、时机、环境或 NPC/世界反应影响，而且不同结果会实质改变剧情、信息、风险或代价。正常由 StatusSubAgent 的 Outcome 阶段先判断，漏判或失败时由主 Agent 补判；满足条件时，即使用户没有提骰子，也应在叙事结果前调用一次 `rp_story_outcome`。

五档定义与系统默认比例为：

| code | 展示名 | 默认比例 | 叙事约束 |
|---|---|---:|---|
| `critical_success` | 大成功 | 5% | 完整且超额达成 reason 的整体目标，并获得额外机会、信息或优势 |
| `success` | 成功 | 25% | 完整达成 reason 的整体目标，不附加重大代价 |
| `success_with_cost` | 成功但有代价 | 40% | 完整达成 reason 的整体目标并引入相称代价；代价不得抵消成功 |
| `setback` | 失败但推进 | 25% | 未达成 reason 的整体目标，但提供新信息、替代路径或下一步行动 |
| `critical_failure` | 重大失败 | 5% | 未达成 reason 的整体目标并引入严重后果，但不自动死亡、硬停局或永久剥夺玩家角色主权 |

Outcome 判定与状态更新由代码拆成独立阶段：预裁定成功后停止 Route 并将结果注入主 Agent；无需裁定时才执行状态目标路由与隔离更新。Outcome 的失败补判语义不受快速状态 best-effort 策略影响。完整正常链路和失败路径见 [StatusSubAgent 固定编排](docs/agent-turn-orchestration.md#statussubagent-固定编排)。

适合触发剧情裁定的情况：

- 玩家明确把结果交给运气，例如“我想碰碰运气，看能不能找到其它线索”。
- 用户没有提骰子，但行动明显受未知信息、能力、阻力、风险、时机或环境影响，例如趁守卫转身潜行、在火势蔓延前寻找出口。
- NPC 或世界的反应存在多个合理分支，当前人物动机和场景不足以唯一决定结果，而且不同分支会实质影响剧情。

不应触发剧情裁定的情况：

- 替玩家决定“我要不要做”“我是否原谅”“我真实喜欢谁”等角色主权选择或内心感受。
- 上下文已经确定结果、行动没有有效阻力，或只是没有实质代价的日常动作。
- 纯台词、情绪表达和不会改变剧情的信息重复确认。

自然语言是主要使用方式：

| 玩家输入 | 预期行为 |
|---|---|
| `我想碰碰运气，看能不能在附近找到其他线索` | 调用一次 `rp_story_outcome`，再按五级结果叙事 |
| `我趁守卫看向别处时溜进档案室` | 即使没有骰子关键词，只要当前场景仍有被发现的风险，就进行剧情裁定 |
| `我向 Alice 点头问好` | 没有实质变数，直接继续叙事 |
| `我很犹豫，但还是没有决定是否原谅他` | 不替玩家作出内心选择 |
| `这轮不要掷骰，直接继续叙事` | 尊重明确否定，不注入本轮强制裁定指令 |

每个自动剧情 turn 最多产生一条裁定；同一 turn 重复工具调用复用第一次结果。权重在 turn 开始时形成快照，生成中修改只影响下一 turn。裁定与 user/assistant message、快速状态表在同一个短数据库事务中提交；取消、provider 失败或 commit 失败都不留记录。

模块配置优先级是 `系统配置 < Story 稀疏覆盖 < Session 稀疏覆盖`；普通字段逐字段合并，Narrative Outcome 的五档 `weights` 是不可拆分整组，五项必须是 `0..100` 整数且总和严格等于 `100`。Story 编辑页管理模块挂载开关与配置，Session 设置菜单可覆盖或清除后继续继承 Story。通用接口为：

- `GET /play-api/v1/rp-modules/catalog`
- `GET /play-api/v1/workspaces/{workspace_id}/stories/{story_id}/rp-modules`
- `PATCH /play-api/v1/workspaces/{workspace_id}/stories/{story_id}/rp-modules/{module_name}`
- `GET /play-api/v1/sessions/{session_id}/rp-modules`
- `PATCH/DELETE /play-api/v1/sessions/{session_id}/rp-modules/{module_name}`

开发期迁移 `0005` 已整合重写为 `0005_rp_modules.sql`，不保留旧权重列兼容；本地数据库若曾执行旧版 `0005_narrative_outcome.sql`，需要重建后再启动。

`rpg_core/settings.yaml` 的 canonical 配置是：

```yaml
rp_modules:
  enabled: true
  modules:
    narrative_outcome:
      enabled: true
      auto_adjudication_enabled: true
      default_weights:
        critical_success: 5
        success: 25
        success_with_cost: 40
        setback: 25
        critical_failure: 5
    dice:
      enabled: true
      default_dc: 12
```

- `auto_adjudication_enabled=true`：允许按语义、当前场景和状态主动裁定隐式变数；关闭后只响应明确随机请求。
- `dice.allow_auto_checks` 已移除；出现该旧 key 会在启动时明确报错。自动剧情裁定只由 `narrative_outcome.auto_adjudication_enabled` 控制。

#### Dice：低层随机与手动调试

Dice 不再向主 LLM 暴露 `rp_dice_roll` 或 `rp_dice_check_dc`，也不再提供剧情判定提示。表达式解析、随机源和 DC 计算仍保留给手动调试及未来模块复用；`default_dc` 只服务 `/check_dc` 手动命令，`max_dice_count` / `max_die_sides` 只是输入安全限制。

手动命令主要用于调试、兜底或用户明确想自己指定骰子时，不是正常游玩的必需步骤：

```text
/roll 1d20                 # 只取得随机点数
/roll 2d6+1 随机天气       # 指定表达式与原因
/check_dc 1d20 dc=12 搜索  # 手动指定一次 DC 检定；省略 dc 时用 default_dc
/rp_module narrative_outcome # 查看剧情裁定模块
/rp_module dice              # 查看 Dice 调试模块
```

当前阶段明确不做：角色属性/技能面板、复杂难度表、装备或状态加值、优势/劣势、对抗检定、战斗骰，以及要求玩家频繁输入数值。Narrative Outcome 是当前剧情分支机制；底层 Dice 不应反向推动产品走向重数值玩法。

Assistant 回复的 `content` 是唯一真源：带标签全文会原样进入 SSE、历史和数据库，不再通过 `metadata.messageDisplay` 保存旁白/角色分段。Play WebUI 只在展示层做容错解析；解析失败、半截标签或非标准流内容必须原文展示，不丢消息。

SSE 业务错误码通过独立 `errorCode` 字段传递，`message` 保持底层错误文本；不要把业务错误码拼进正文，也不要把它和 HTTP `statusCode` 混用。

## 记忆系统

`rp_memory/` 是一个独立的检索子系统，不再把向量、keyword FTS、原始 markdown 扫描和 query 规划混在一个类里。当前结构按职责拆分为四个职责层：

```text
rp_memory/
├── planning/    QueryPlan 生成与 query rewrite
├── retrieval/   SqlVec / keyword / raw markdown recall
├── rerank/      基于 LLMProvider 的可选最终重排
└── storage/     SQLite repository、vector index、text index
```

### 运行链路

```text
用户 query
  -> MemoryManager
  -> QueryPlanner
     - 可通过 `llm_service/llm.yaml` 选择 OpenAI-compatible 或 llama provider
     - 配置缺失或加载失败时降级到 rule-based planner
  -> Retrieval
     - vector: 向量相似度召回
     - keyword: tokenizer 可插拔的 keyword FTS 召回
     - raw md: 直接扫描 markdown，按 raw_md_mode 决定是否作为主召回或 fallback
  -> scoring / fusion
  -> optional pointwise rerank
  -> RecallItem 列表
```

### 子包职责

#### `planning/`

负责把用户 query 变成结构化 `QueryPlan`。

- `RuleBasedQueryPlanner`：无模型兜底，负责归一化、term extraction、jieba 切词
- `LlamaQueryPlanner` / `OpenAIQueryPlanner`：可选的 LLM query planner，通过 `LLMManager` 获取 provider
- `FallbackQueryPlanner`：运行时异常兜底，保证 recall 不被 planner 中断

#### `retrieval/`

负责实际召回，不负责 query 解析。

- `SqlVecRetriever`：纯向量召回
- `KeywordRetriever`：基于 `TextIndex.keyword_search()` 的关键词召回，query 来源权重为 normalized 1.0、planner 0.85、compact 0.70
- `HybridRetriever`：组装 sqlvec + keyword + raw md 的融合召回，统一执行 exact / fuzzy、expanded、recency、granularity 和 hybrid scoring
- `RawMarkdownGrepSearch`：直接扫描 markdown 文件，保留 query planner 的 `raw_md_terms`、`expanded_queries` 和扩展查询分词；会解析 markdown front matter 中的简单标量字段用于 granularity
- `RawMarkdownRetriever`：只走 raw md 的 retriever 适配器

`memory.raw_md_mode` 控制 raw md 的参与方式：

- `disabled`：raw md 完全不参与召回。
- `always`：raw md 每次运行，作为主召回一路参与 merge、hybrid scoring 和 rerank。
- `fallback_only`：主召回只运行 sqlvec + keyword；当主候选不足或 sqlvec / keyword / store 阶段失败时才运行 raw md 补候选。`raw_md_min_results > 0` 时使用该显式阈值；否则阈值为当前召回池目标，有 reranker 时是 `rerank_candidate_k`，无 reranker 时是 `top_k`。

#### `rerank/`

负责可选的最终重排，不参与召回和 query 解析。

- `MemoryReranker`：统一重排接口
- `PointwiseMemoryReranker`：基于 `LLMProvider` 的 pointwise rerank 实现，可使用 OpenAI-compatible 或 llama provider

#### `storage/`

负责持久化和底层索引。

- `MemoryRepository`：SQLite chunk 存取
- `VectorIndex`：向量索引实现
- `TextIndex`：FTS5 / keyword 索引实现，写入和查询都使用 `memory.keyword_tokenizer` 选择的 tokenizer
- `VectorStore`：存储门面，封装 repository + vector index + text index

### 召回 `meta` 字段说明

最终返回的 `meta` 不是单一数据库字段，而是由原始 `candidate.metadata`、各路检索分数，
以及 rerank 调试信息合并而成。`HybridRetriever` 和 `MemoryManager.hybrid_search()` 会在
最终输出前补齐这些字段。

| 字段 | 来源 | 作用 |
|---|---|---|
| `type` | `summary/overall.md` 等摘要 front matter，写入时由 `BatchSummaryStore.save_overall()` 提供 | 标识摘要类型，常见值是 `overall` |
| `last_batch_id` | `summary/overall.md` front matter | 标识 overall 追踪到的最新批次，便于增量归纳 |
| `memory_id` | SQL chunk 的 `chunks.id`，或 raw md 的稳定哈希 ID | 召回项唯一标识，也是各路分数归并键 |
| `source` | 原始文件元信息或 raw md 目录名 | 标识来源类型，如 `summaries` |
| `file` | 原始文件路径 | 定位到具体源文件 |
| `chunk_idx` | 分块索引 | 同一文件内的第几个 chunk |
| `created_at` | SQL chunk 侧通常是写入时间；raw md 侧通常是源文件 mtime | 供 `recency_score` 计算 |
| `vector_score` | `SqlVecRetriever` / `VectorIndex` | 向量相似度分数 |
| `keyword_score` | `KeywordRetriever` / FTS | keyword / BM25 相关性分数 |
| `raw_md_score` | `RawMarkdownGrepSearch` | raw markdown 原文 query / term 覆盖分 |
| `exact_score` | `exact_and_fuzzy_scores()` | query 完全命中时为 1.0 |
| `fuzzy_score` | `exact_and_fuzzy_scores()` | query 的模糊匹配分数 |
| `expanded_score` | `RawMarkdownGrepSearch` / `HybridRetriever._finalize()` | query planner 扩展查询或扩展分词命中分 |
| `recency_score` | `HybridRetriever._finalize()` | 时间衰减分数，越新越高 |
| `granularity_score` | `HybridRetriever._finalize()` | 记忆粒度优先级分，来自 `batch` / `event` / `session` / `global` / `unknown` 等元信息 |
| `hybrid_score` | `apply_hybrid_scores()` | 向量、keyword、raw md、exact、expanded、recency、granularity 的融合分 |
| `rerank_score` | `PointwiseMemoryReranker` | 最终重排分数；有 rerank 时优先参与排序 |
| `debug` | 各检索/重排阶段逐步写入 | 调试信息，例如 `keyword_bm25`、`raw_md_source`、`llama_reason` |

常见 `debug` 键：

| debug 键 | 来源 | 说明 |
|---|---|---|
| `keyword_bm25` | `KeywordRetriever` | keyword FTS 的原始 BM25 分数 |
| `keyword_relevance` | `KeywordRetriever` | BM25 转换后的有界 keyword 相关性分 |
| `keyword_tokenizer` | `TextIndex` | 当前 keyword FTS 使用的 tokenizer：`jieba` / `bigram` / `both` |
| `keyword_query_hits` | `KeywordRetriever` | 多 query 命中明细，包含 query、来源权重、原始分和加权分 |
| `keyword_queries` | `KeywordRetriever` | 实际参与 keyword 搜索的 query 列表 |
| `raw_md_source` | `RawMarkdownGrepSearch` | raw markdown 的源文件路径 |
| `raw_md_terms` | `RawMarkdownGrepSearch` | raw markdown 实际使用的 term 列表 |
| `raw_md_expanded_queries` | `RawMarkdownGrepSearch` | raw markdown 使用的扩展查询 |
| `raw_md_expanded_terms` | `RawMarkdownGrepSearch` | 扩展查询再次分词得到的 raw md term |
| `raw_md_match_score` | `RawMarkdownGrepSearch` | raw md 阶段 exact、raw_md、expanded 三者的最大命中分 |
| `vector_score_norm` | `apply_hybrid_scores()` | 向量分数归一化后结果 |
| `keyword_score_norm` | `apply_hybrid_scores()` | keyword 分数归一化后结果 |
| `recency_score_norm` | `apply_hybrid_scores()` | 时间分数归一化后结果 |
| `exact_or_fuzzy_score` | `apply_hybrid_scores()` | exact / fuzzy 的合并分 |
| `expanded_score` | `apply_hybrid_scores()` | 参与 hybrid scoring 的扩展查询命中分 |
| `granularity_score` | `apply_hybrid_scores()` | 参与 hybrid scoring 的记忆粒度分 |
| `memory_granularity` | `HybridRetriever._finalize()` | 解析出的记忆粒度，如 `batch`、`event`、`global`、`unknown` |
| `llama_score_norm` | `PointwiseMemoryReranker` | llama provider rerank 打分归一化后结果 |
| `llama_reason` | `PointwiseMemoryReranker` | llama provider rerank 给出的简短原因 |
| `openai_score_norm` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 打分归一化后结果 |
| `openai_reason` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 给出的简短原因 |

注意：不同候选不一定都有全部字段，这是正常的。比如 raw md 候选通常会有
`raw_md_*`，而 SQL 向量候选更偏向 `vector_score` / `keyword_score` / `recency_score`。

### 配置

记忆系统配置分两类：

- `rpg_core/settings.yaml`：业务与检索参数，对应 `MemorySettings`，例如 `top_k`、`hybrid_*_weight`、`rerank_enabled`、`rerank_score_weight`、`chunk_size`、`chunk_overlap`、`jieba_dict`
- `llm_service/llm.yaml`：LLM 强相关配置，例如 `memory.embed`、`memory.query_planner`、`memory.rerank` 的 provider、model、model_path、上下文窗口、温度、超时

代码外部不直接读取 YAML 字符串 key。业务代码通过 `settings.memory_settings`、`LLMManager.get().get_provider(biz_key)` 或 `Settings` / `llm.config` 的封装方法访问配置。

常用 `rpg_core/settings.yaml` 的 `memory` 字段：

- `top_k`
- `hybrid_enabled`
- `hybrid_vector_weight`
- `keyword_tokenizer`
- `keyword_k`
- `raw_md_mode`
- `raw_md_min_results`
- `hybrid_keyword_weight`
- `hybrid_raw_md_weight`
- `hybrid_exact_weight`
- `hybrid_expanded_weight`
- `hybrid_recency_weight`
- `hybrid_granularity_weight`
- `rerank_enabled`
- `rerank_candidate_k`
- `rerank_score_weight`
- `chunk_size`
- `chunk_overlap`

关键语义：

- `keyword_tokenizer` 支持 `jieba`、`bigram`、`both`，默认 `jieba`；`bigram` 只是 tokenizer 选项，不再是检索架构命名。
- `keyword_k` 控制关键词召回候选数；不再读取旧的 `bigram_k`。
- `hybrid_keyword_weight` 控制 keyword 归一化分权重；不再读取旧的 `hybrid_bigram_weight`。
- `raw_md_mode=fallback_only` 且 `raw_md_min_results=0` 时，主候选不足阈值使用当前召回池目标：有 reranker 时为 `rerank_candidate_k`，无 reranker 时为 `top_k`。
- `rerank_candidate_k` 控制进入 reranker 的最大候选池，最终仍只返回 `top_k`。

代码中已有 sqlvec + keyword + raw md 三路独立 retriever，`HybridRetriever` 只负责组装与融合。
新增配置前应同步更新对应进程/模块的 settings 封装、README、`AGENTS.md` / `CLAUDE.md` 和测试。

### 设计原则

- `MemoryManager` 负责组装，不负责检索细节
- `QueryPlanner` 是增强能力，不是主链路硬依赖
- keyword 查询格式始终由 tokenizer 保证
- raw md 的 `always` 是主召回策略，`fallback_only` 是触发策略；一旦进入候选池，raw md 候选与其他候选同样参与 merge、hybrid scoring 和 rerank
- 检索层优先保持可解释的分数融合，避免把排序黑箱化

## 配置

### 配置文件拆分

根目录不再保留 `settings.yaml` / `llm.yaml`。配置按进程和业务边界拆分：

| 文件 | 职责 |
|---|---|
| `rpg_core/settings.yaml` | 核心业务配置：Agent 行为、主 Context 正文拒绝阈值、memory 检索参数、核心日志 |
| `agent_service/settings.yaml` | Agent 服务监听参数、非 Agent 进程访问 Agent 服务的客户端默认值、Agent 服务日志 |
| `channels/settings.yaml` | CLI / Telegram 渠道行为、Telegram bot、渠道日志 |
| `play_api/settings.yaml` | Play API 监听参数、Play API 日志 |
| `play_webui/play_webui.config.json` | Play WebUI 通用配置入口，例如 SessionRoom 历史分页窗口和 context 正文门禁阈值 |
| `llm_service/llm.yaml` | LLM provider、模型、上下文窗口、温度、超时等 LLM 强相关配置 |

正文门禁由 `play_webui` 的 `session.contextUsage.inputBlockThresholdRatio` 和 Core 的 `agent.context_window_reject_threshold_ratio` 独立控制，合法范围均为 `(0, 1]`、默认均为 `0.9`。前端非法值回退 `0.9`，Core 非法值会阻止启动；两侧都只计算不含当前待发送 input 的主 Agent Context。

上述 YAML 配置使用同一套 `base + profiles` 结构，通过 `RPG_WORLD_PROFILE` 选择 profile，默认读取各文件自己的 `default_profile`。`local` / `test` / `prod` 是固定 profile 名称；不需要在 `profiles.*.file` 里声明覆盖文件。当前 profile 会自动读取同级覆盖文件，例如：

```text
rpg_core/settings.local.yaml
channels/settings.local.yaml
agent_service/settings.local.yaml
play_api/settings.local.yaml
llm_service/llm.local.yaml
```

覆盖文件默认被 `.gitignore` 忽略，适合放本地 token、API key、端口或机器相关模型路径。示例文件可以用 `*.example.yaml` 形式提交，例如 `channels/settings.local.example.yaml`。

核心 memory 配置放在 `rpg_core/settings.yaml`：

```yaml
base:
  agent:
    max_tool_call_limit: 10
    include_tool_records: true
    verbose_logging: true
    status_sub_agent:
      enabled: true
      deferred:
        default_interval_turns: 5
  memory:
    top_k: 2
    keyword_tokenizer: jieba
    keyword_k: 50
    raw_md_mode: fallback_only
    rerank_candidate_k: 8
    rerank_score_weight: 0.70
  logging:
    log_level: DEBUG
profiles:
  local: {}
  test: {}
  prod: {}
```

渠道配置放在 `channels/settings.yaml`：

```yaml
base:
  channels:
    telegram:
      bots:
        main:
          enabled: false
          token_env: TELEGRAM_BOT_TOKEN_MAIN
          workspace_id: demo_workspace
          story_id: 1
          session_id: ""
          session_title: main
          auto_pin_created_session: false
    cli:
      workspace_id: demo_workspace
      story_id: 1
      session_id: ""
      session_title: CLI
      streaming: true
  logging:
    log_level: DEBUG
```

服务监听和客户端默认值按进程拆分。例如 `agent_service/settings.yaml`：

```yaml
base:
  service:
    host: 127.0.0.1
    port: 8010
    api_prefix: /agent/v1
    reload: false
  agent_client:
    base_url: http://127.0.0.1:8010/agent/v1
    request_timeout_ms: 60000
    stream_timeout_ms: 300000
  logging:
    log_level: DEBUG
```

Play API 的监听和日志放在 `play_api/settings.yaml`。

LLM provider 选择放在 `llm_service/llm.yaml`：

```yaml
base:
  biz:
    agent.main:
      kind: chat
      provider: openai
      openai:
        model: deepseek-v4-flash
        api_key_env: OPENAI_API_KEY_LOCAL
        base_url: https://api.deepseek.com
    memory.rerank:
      kind: rerank
      provider: llama
      rerank_model_type: qwen3_logit
      llama:
        model_path: ""
        n_ctx: 4096
        temperature: 0.0
```

`rerank_score_weight` 是排序业务参数，留在 `rpg_core/settings.yaml`；不要写入 `llm_service/llm.yaml` 的 provider 配置。

工作区不再放在旧 JSON 配置中。API/WebUI 通过请求参数或 catalog session 解析 workspace；
Telegram/CLI 通过 `channels/settings.yaml` 中各自的 `workspace_id + story_id` 绑定故事。`session_id` 可留空，此时启动时创建系统生成 ID 的默认 session；非空时只校验并加载既有 session。旧 `workspace` 字段、`cli_direct` 默认 ID 和用户自定义 session ID 创建入口都不再保留。`rpg_data` 中的 workspace 根目录来自 `rpg_workspaces.root_path`；workspace/story/session 运行目录使用 workspace-relative 路径时由 `rpg_data.settings` 解析并阻止路径逃逸。

## Session ID 规则

`session_id` 只能包含英文字母、数字和下划线，规则为 `^[A-Za-z0-9_]+$`。
所有创建入口都由 `rpg_data` 生成全局唯一 session ID；用户只允许指定 title。Play WebUI 创建 session 时会在 `rpg_data` 绑定 `workspace_id + story_id`，会话内链路只使用全局短 `session_id`。

### 会话历史字段

会话消息写入 `rpg_session_messages`，冷备份写入 `rpg_session_backup_messages`。数据库自增 `id` 映射为 `Message.uid`；`turn_id` 和 `seq_in_turn` 由 `SessionManager` 管理，持久化路径必须写入正数。主消息表约束同一 session 内 `(turn_id, seq_in_turn)` 唯一；冷备份表保持追加语义，不做唯一约束。

summary 和剧情记忆提取进度标记在 `rpg_session_messages` 对应消息行上；剧情记忆条目写入 `rpg_session_story_memories`，且必须关联正数 `turn_id`。summary 的 `keep_recent_rounds` 和批次切分仍按显式 turn/round 分组；异常 turn metadata 在写入或加载边界失败，不再恢复 user-anchor / pair 降级分组。

Agent Context 与历史展示分离：Play/Agent 的 `history` / `history-page` 接口始终返回完整未删除历史；主 Agent Context 则按 `summary_processed` 字段逐条过滤，`true` 不进入 Context，`false` 进入。只要本次投影中过滤过消息，Summary Layer 可以尝试加载现有 `overall.md`；文件不存在或为空时摘要层为空，但已处理消息仍不回流 Context。删除、清空、编辑回滚和 turn truncate 只直接修改历史，不删除摘要文件、不重置其它消息标记，也不自动重新归纳。

## 测试

所有测试 mock LLM 调用，无需 API key：

```bash
uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests -q
```

当前测试会 mock LLM、Telegram SDK 和网络调用。若本地缺少 `pytest-asyncio`，`rpg_core/tests/test_command.py` 中的 async 测试会提示需要安装异步 pytest 插件。覆盖范围包括：

- `channels/tests/`：ChannelAdapter、CLI、Telegram 渠道和渠道侧会话流程。
- `rpg_core/tests/`：Agent facade、Mailbox、Lifecycle、MainModel、Context/Tool service、turn hooks/runtime/orchestrator、transaction、命令、scene、session 与 summary。
- `rp_memory/tests/`：memory 检索、索引、规划、rerank。
- `llm_service/tests/`：LLM provider 配置、manager 路由与 llama 本地 runtime 协议。
- `play_api/tests/`：Play API workspace/session/scene/turn/stream、characters、lorebook、status-tables 和 ops 等契约。

Telegram 测试已覆盖会话菜单、命令规范化、系统生成 ID 的创建流程、流式编辑节流、
Markdown 渲染和长文本分块。后续修改 Telegram 行为必须补对应测试。

修改 Agent 组合或 turn pipeline 时，先跑组件专项与 Agent Service 契约，再跑完整基线和 Core integration：

```bash
uv run python -m pytest \
  rpg_core/tests/test_agent.py \
  rpg_core/tests/test_agent_mailbox.py \
  rpg_core/tests/test_agent_lifecycle.py \
  rpg_core/tests/test_agent_context_service.py \
  rpg_core/tests/test_agent_tool_service.py \
  rpg_core/tests/test_turn_hooks.py \
  rpg_core/tests/test_turn_runtime_factory.py \
  rpg_core/tests/test_turn_orchestration.py -q
uv run python -m pytest agent_service/tests -q
INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q
```

## 当前实现优先级

1. **P0：Play WebUI 主体验与 Play API 契约**。优先保障 session 房间、SSE/turn、workspace、characters、lorebook、status-tables、ops 等 Web 主链路。
2. **P1：核心数据、上下文与记忆链路**。确保角色卡、世界书、状态表、summary、story memory 和 rp_memory 在全局 `session_id` 语义下稳定可用。
3. **P2：Telegram/CLI 轻量入口稳定性**。保持真实 Telegram 长轮询、会话菜单、stream/non-stream、异常回复、命令菜单和运行配置可靠。
4. **P3：玩法模块与沉浸式细节**。骰子、战斗、物品等新增体验型能力优先沉淀到 Play WebUI，并通过受控工具和状态读写接入核心。

## 相关文档

- [`docs/agent-turn-orchestration.md`](docs/agent-turn-orchestration.md) — Agent turn、Outcome、状态路由、事务和 deferred 完整编排
- `CLAUDE.md` — 完整架构文档和技术细节
- `rpg_core/settings.yaml` — 核心业务、数据路径、memory 参数
- `agent_service/settings.yaml` — Agent 服务监听与 AgentClient 默认值
- `channels/settings.yaml` — CLI / Telegram 渠道配置
- `play_api/settings.yaml` — Play API 监听与日志
- `play_webui/play_webui.config.json` — Play WebUI 通用配置入口
- `llm_service/llm.yaml` — LLM provider、模型、上下文窗口和超时配置
