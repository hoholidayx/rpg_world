# RPG World — 故事数据管理与 LLM Agent 交互子系统

RPG World 是 nanobot 项目的一个子系统，专注于故事驱动的 RPG 数据管理和 LLM Agent 交互。提供角色卡管理、世界书管理、状态表管理、场景上下文构建、记忆召回与 RP 模块运行态等功能。

## 目录

- [产品路线与定位](#产品路线与定位)
- [近期架构变更记录](#近期架构变更记录)
- [快速起步](#快速起步)
- [架构](#架构)
  - [进程隔离架构](#进程隔离架构)
  - [Play 会话与数据目录](#play-会话与数据目录)
  - [RPG Media 与 Session 图像](#rpg-media-与-session-图像)
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

设计原则：Play WebUI 负责 Web 主体验和管理入口，Telegram 负责触达效率；二者必须共享同一套 workspace/session 语义，避免同一个故事在不同渠道分裂。Play WebUI 只访问 Play API：聊天、Dream、媒体和 TTS 分别代理到独立服务，管理数据通过 `rpg_data`；前端不复制角色、世界书、状态、记忆或 RP 规则。

## 近期架构变更记录

- **2026-07-18：后台终态通知链路。** Dream proposal 与 Session Derivation 在 SQL 终态提交后，通过专用异步 publisher 把 `ready / failed / interrupted` 发送到 Play API 的进程内广播 Hub；Play WebUI 在根 Provider 建立唯一全局 EventSource，并在顶栏独立通知中心展示最近事件。通知只保存在页面内存，可标记已读和清除；不增加 Toast、自动刷新或任务状态回写。
- **2026-07-17：Dream 长期记忆系统。** 新增独立 `dream_service` 与 Session 级类型化 Persistent Memory 账本。Play WebUI 可手动执行 Shallow/Deep × Incremental/Full 四种 Dream，逐项检查和编辑 proposal 后原子应用；主 Agent 只读取 Evidence 仍有效的 active revisions，不再读取 `persistent_memory.json`。
- **2026-07-15：LLM Service 完全独立进程化。** 新增 `run_llm.py`、受 Bearer 保护的 `/llm/v1` 业务 HTTP/SSE 边界和独立 `llm_client` 契约包。只有 LLM Service 读取 `llm.yaml`、Provider 密钥并持有 OpenAI/llama runtime；Agent 与 Memory 只通过远端客户端调用，旧 llama 子进程协议已删除。
- **2026-07-15：Agent / Memory / LLM 统一异步线程模型。** `llm_client` 改为 loop-owned 纯异步客户端，Agent 与 Memory 直接 await catalog、provider、embedding 和 recall；Memory 使用 session 级 async coordinator，watchdog 线程只入队。llama 的队列等待与运行期统一受 `request_timeout_ms` 控制，并在 completion、stream、rerank 安全边界协作取消。
- **2026-07-15：RPG Media v1。** 新增与 `rpg_core` 同级的无框架 `rpg_media`，以及独立 `media_service` 持久任务进程。SessionRoom 支持从 1–20 个连续 turn 生成可编辑 `VisualBrief`、异步生图、Gallery 与会话背景；图片按工作区内容寻址存储，媒体故障不影响聊天主链路。
- **2026-07-13：Agent Turn 与状态更新固定编排。** Narrative Outcome 与状态更新拆分为独立阶段；状态更新先 Route，再按 scene 和单张普通表隔离执行。快速状态目标采用 best-effort：单个目标失败只回退该目标，其他成功目标保留且主流程继续；整个 turn 仍只在主 runner 成功后统一提交。字段频率统一为 `realtime | event_driven | deferred | manual`，其中 deferred 在回复交付后、同 session 下一 mailbox 项前归纳。scene 继续以 `status_kind="scene"` 作为数据真源，但在主 Context 和更新工具上走专用路径。完整设计、时序和失败语义见 [Agent Turn 与状态更新编排](docs/agent-turn-orchestration.md)。

## 快速起步

```bash
# 安装依赖
uv sync

# 可选：非本地部署应为 LLM Service 与调用方配置相同的静态令牌。
# 未设置时双方共同使用内置的 rpg-world-local-token，LLM Service 会警告。
export RPG_WORLD_LLM_SERVICE_TOKEN=replace-with-a-secret
# Agent、Dream 与 Play API 的后台事件内部入口必须使用同一个令牌。
# 未设置时共同回退到仅适合本地开发的默认值并记录 warning。
export RPG_WORLD_PLAY_EVENT_TOKEN=replace-with-another-secret
# 启用 SessionRoom OpenAI Speech TTS 时设置；仅 LLM Service 读取。
export OPENAI_API_KEY_TTS=replace-with-an-openai-key

# 推荐：一键启动 LLM、Agent、Dream、Media、TTS、Play API；Ctrl-C 会优雅停止全部子进程
uv run python -m run_all
# 或：uv run rpg-world-up

# 也可以按需分别启动（不要与 run_all 同时运行）
# 先启动 LLM 服务（唯一读取 llm.yaml/密钥并持有 Provider/llama runtime）
uv run python -m run_llm
# 再在另一个终端启动 Agent 服务
uv run python -m run_agent
uv run python -m run_dream
uv run python -m run_media
# 已有项目虚拟环境时也可使用：.venv/bin/python -m run_media
uv run python -m run_tts
uv run python -m run_play_api
uv run python -m run_telegram
uv run python -m run_cli

# CLI / Telegram / API 都通过 agent_client 访问 Agent 服务
uv run python -m channels.cli.repl

# 直接调试 API（自动重载）
uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir agent_service --reload-dir media_service --reload-dir tts_service --host 127.0.0.1 --port 8000

# 启动 Play WebUI（另一个终端）
cd play_webui && npm run dev
```

根目录不再提供持有业务运行时的聚合 supervisor。`run_all.py` 只是可选的前台进程编排器，
负责按顺序启动和停止六个独立 `run_*` 子进程，不合并任何 Agent、LLM、Dream、Media、TTS 或 Play API 运行时。
每个服务启动前都会检查配置端口；占用者确认是 Python 或 uv 时先终止并等待端口释放，
超时后强制结束，其他类型的进程则保留并中止启动。默认端口为 Play API `8001`、
Agent `8010`、Media `8011`、LLM `8012`、TTS `8013`、Dream `8014`。
配置已按进程/模块拆分到各自目录，进程启停不通过配置控制。

## 架构

### 进程隔离架构

RPG World 采用独立 Agent、LLM、Dream、Media 与 TTS 服务拓扑。只有 `run_agent.py` 进程持有
`AgentManager` 和 `RPGGameAgent`；Agent 使用 `rp_memory` 做召回与 Context 投影，Dream Service 使用
`rp_memory.dream` 做离线提炼。只有 `run_llm.py` 进程读取
`llm.yaml`、Provider 密钥并持有 OpenAI/llama Provider 和本地 llama runtime。
Agent/Memory、Dream 与 TTS Service 通过 `llm_client` 调用 LLM 服务；Play API 的聊天、Dream、媒体和语音链路分别通过
`AgentClient`、`DreamClient`、`MediaClient`、`TTSClient` 访问独立服务，CLI 与 Telegram 通过 `AgentClient` 调用 Agent 服务。

```
run_llm            -> llm_service.main:app   -> Provider + local llama runtime
run_agent          -> agent_service.main:app
run_dream          -> dream_service.main:app -> rp_memory.dream + rpg_data + llm_client
run_media          -> media_service.main:app -> rpg_media + rpg_data
run_tts            -> tts_service.main:app   -> rpg_tts + rpg_data + llm_client
run_play_api       -> play_api.main:app      -> AgentClient + DreamClient + MediaClient + TTSClient
run_cli            -> channels.cli.repl      -> AgentClient
run_telegram       -> channels.telegram.runner -> AgentClient

# 可选的前台编排入口，仅负责启动/停止上述独立进程，不合并任何运行时
run_all            -> run_llm + run_agent + run_dream + run_media + run_tts + run_play_api
```

根目录还提供同级快捷入口，便于调试和查找：

```
run_llm.py      -> llm_service.main
run_agent.py    -> agent_service.main
run_dream.py    -> dream_service.main
run_media.py    -> media_service.main
run_tts.py      -> tts_service.main
run_play_api.py -> play_api.main
run_all.py      -> 启动并管理六个独立后端子进程
run_telegram.py -> channels.telegram.runner
run_cli.py      -> channels.cli.repl
```

### 事件循环与线程模型

Agent Service 使用一个主事件循环。每个 session 的 turn 由自己的 `AgentMailbox` FIFO 串行，但不同 session 在等待 LLM HTTP 或 Memory 时可以并发。`llm_client` 只持有一个归属于该 loop 的 `httpx.AsyncClient`；catalog、provider、chat/stream、embedding、dimension、rerank 和 health 都直接 `await`。客户端一旦首次使用就不能跨事件循环或线程复用，重新配置和进程关闭会 await 关闭旧连接池。

```text
Agent event loop
├── session A mailbox ── await LLM / Memory
├── session B mailbox ── await LLM / Memory
└── loop-owned LLMClientManager + AsyncClient

MemoryManager（每个 session 一个）
├── async lock：recall / index / reindex / close 串行
├── watchdog callback thread：只投递 source ID
└── loop consumer：await embedding；file/hash/chunk/SQLite 使用 to_thread

LLM Service
└── 每个 llama model cache key 一个 actor thread + FIFO
```

本地 llama 没有恢复为子进程。`request_timeout_ms` 从任务入队时开始计算，包含同模型排队和运行时间；排队任务取消后不会执行，completion/stream/rerank 在安全边界协作停止。原生 embedding 或单次 eval 无法在 C 调用中途抢占时，调用方仍按 deadline 收到超时，actor 会先自然排空，再处理同模型下一任务。服务关闭最多等待 `llama_shutdown_grace_ms`。

LLM Service 的 `/health` 故意免 Bearer 鉴权，只回答进程是否存活、配置是否加载；它不验证 Agent 配置的 token。catalog、chat、stream、embedding、dimension、rerank 等业务接口仍要求 Bearer token，凭据错误会在受保护请求上明确返回 401。

服务、渠道和客户端配置分别由对应模块的 YAML 管理，所有配置字段都封装为类型化属性：

```python
from channels.config import settings as cfg
from agent_service.settings import settings as agent_cfg
from llm_service.settings import settings as llm_cfg
from media_service.settings import settings as media_cfg
from play_api.settings import play_settings

agent_cfg.service.port
agent_cfg.agent_client.base_url
agent_cfg.llm_client.base_url
llm_cfg.service.port
media_cfg.media_client.base_url
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
- 首次成功绑定且 main history 为空、story `first_message` 非空时，`SessionRoleService` 会按刚绑定的角色渲染模板，再将同一条 assistant 开场消息写入 main 和 backup history；普通历史删除或后续切换角色时不会重复追加。`/clear` 完整重置是例外：有效绑定会按当前模板重新写入 turn 1 开场，下一次玩家输入从 turn 2 开始。
- 玩家身份在 Context 门禁前固化进 `TurnExecutionSnapshot`，由门禁、主 Agent、StatusSubAgent 与 Context Preview 共用。fixed layer 的 `[player_character]` 标签块是身份唯一真源；角色卡只在 Context 投影时标注为 `PLAYER_CHARACTER` 或 `NPC`，不依赖角色 metadata。当前绑定覆盖冲突的旧历史、摘要和记忆，但不会自动改写这些既有数据。

Play API 是 catalog session 到 Agent 服务的边界层：它通过 `session_id` 反查 workspace/story，并只把全局 `session_id` 传给 Agent 服务运行态；Agent service 的 `/chat/history`、`/chat/commands`、`/chat/send`、`/chat/stream`、`/chat/stop` 不再接收 workspace。当前会话内接口集中在 `/play-api/v1/sessions/{session_id}/...`，例如 `history`、`history-page`、`scene`、`commands`、`turn`、`stream`、`stop`、`player-character`。workspace、characters、lorebook、status-tables、ops 等管理接口也在 Play API 下；旧的 `chat.py`、`scene.py`、`commands.py` router 只保留占位，不再挂载为主接口。

会话中心详情面板和 Session Room 设置菜单提供永久删除入口，并统一使用确认弹窗。`DELETE /play-api/v1/sessions/{session_id}` 转发到 Agent service：先阻止该 session 的新请求、取消活动及排队生成并释放 watcher/SQLite，再删除 catalog 行、全部级联数据（包括 append-only 冷备）和 runtime 目录。它与保留 session 身份的 `/clear` 不同；运行目录清理失败时返回 `runtimeCleanup="pending"`，隔离目录可继续在数据清理中处理。

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
- migration `0008_status_update_frequency.sql` 新增 `rpg_session_status_deferred_progress`，以运行时表 ID + 字段 key 保存最后处理 turn。deferred 的 document 值与进度在同一数据库事务中提交；归纳失败不推进进度，truncate 只收缩进度边界且不回滚已经提交的状态值。`/clear` 删除全部进度和旧 Story 模板副本，再按当前挂载重建；`session_native` 表保留 ID、结构、metadata 和字段策略，仅将所有 value 置空。同名原生表与当前 Story 模板冲突时整个 reset 回滚。
- `DataServiceGateway` 初始化时只 materialize workspace/story/session 运行目录并初始化缺失的 session 状态表副本；service 不扫描目录补业务索引，也不维护状态表 type 表、workspace-relative 状态表文件路径或 CSV 内容源。
- Bootstrap 默认不删除不在 SQL 索引里的 workspace/story/session 目录。只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才会执行启动清理；日志会输出每个删除项和汇总计数。
- `当前场景` 是 `status_kind="scene"` 的特殊状态表，仍受 story 挂载约束；多张 scene 表存在时消费排序第一张。scene document 的所有字段固定为 `realtime`，保存边界拒绝 `event_driven` / `deferred` / `manual`。LLM 默认只能修改已有 key 的 value；`agent.scene.allow_runtime_key_changes=true` 才允许通过 scene 工具增删非锁定 key，管理端手工 CRUD 不受影响。
- `rpg_data` 通过 `rpg_workspaces.root_path` 定位 workspace 根目录，workspace/story/session 运行目录使用 workspace-relative 路径时统一由 `rpg_data.settings` 解析并阻止路径逃逸。

Play WebUI 的状态表页分为 `系统模板`、`故事状态模板` 和 `故事运行时` 三个视图。`系统模板` 管理工作区级模板及其 story 挂载；`故事状态模板` 管理当前 story 已挂载模板、故事内创建模板和可选角色绑定；`故事运行时` 只管理当前 session 的运行时副本。

### RPG Media 与 Session 图像

`rpg_media/` 是与 `rpg_core/` 同级的无框架高级能力模块；FastAPI、队列生命周期和 HTTP 客户端位于独立的 `media_service/`。Play WebUI 始终经 Play API 访问媒体链路，Play API 使用 `MediaClient` 代理 JSON 和图片字节流，不直接读取工作区文件。Media service 默认监听 `http://127.0.0.1:8011/media/v1`；它未启动时图像工作室显示独立故障状态，SessionRoom 聊天、输入和 Agent SSE 继续工作。

v1 的交互是“手动触发 + 可检查提示词 + 异步生成”：

1. 从 Session 已提交历史中选择 1–20 个连续 turn；前端提供 1/5/10/20 快捷范围和每个 turn 的紧凑预览。
2. 后端固化包含 message ID/version/content 的来源快照和 SHA-256 指纹，生成九字段 `VisualBrief`；用户可编辑场景、主体、环境、动作、构图、光线、风格、负面约束和画幅。
3. 提交时再次校验来源指纹，数据库 Job 进入持久队列；默认单 worker、无自动重试，支持取消和显式重试。服务启动时扫描 `queued`，创建/重试通过事件即时唤醒 worker，队列排空后阻塞等待；重启会把遗留 `running/cancelling` 标记为 `interrupted`。
4. 成功图片进入 Session Gallery，可设置为 Session 背景。若原 turn 被编辑、截断或删除，Gallery 只标记来源陈旧，不自动删除图片。

当前 `DemoVisualBriefPlanner` 是配置驱动的确定性实现，不调用外部文本模型；`VisualBriefPlanner` 是可替换契约。未来接入文本 LLM 时应通过 `llm_client` 使用通用 chat biz 选择，不对 llama 等 Provider 做业务黑名单；Media service 不直接读取 LLM 配置或创建 Provider，本地 llama runtime 仍只存在于 LLM Service。

图片二进制固定存放在：

```text
{workspace_root}/assets/images/{sha256}.png|jpg|webp
```

写入前按魔数识别 PNG/JPEG/WebP。数据库 Blob 用 `(workspace_id, sha256)` 去重；SHA-256 不作为业务 Asset ID，每次成功生成建立独立 UUID Asset，保留本次 Provider、简报、参数和来源语义。背景引用会阻止 Asset 删除，最后一个 Asset 引用删除后才回收 Blob 行与文件。`/clear` 清除当前 Session 的 Job、Gallery 和背景，但保留 Workspace Asset/Blob；永久删除 Session 也只级联清理 Session 关联。图片与消息历史分离，不进入正文、message metadata、turn/SSE 或 localStorage。

### SessionRoom TTS

`rpg_tts/` 是与 `rpg_core/`、`rpg_media/` 同级的无框架高级能力模块，负责从已提交 assistant 消息解析可朗读正文、确定性分段、缓存指纹和 MP3 内容寻址存储；FastAPI、持久任务 worker 与客户端位于独立的 `tts_service/`。SessionRoom 仅在玩家点击回复气泡的朗读按钮后，经 Play API → `TTSClient` 创建任务。TTS 不进入 Agent turn、正文 SSE、message metadata 或 localStorage。OpenAI Speech Provider、音色和密钥仍由 LLM Service 唯一持有，TTS Service 只通过 `llm_client` 调用；默认监听 `http://127.0.0.1:8013/tts/v1`。

### Telegram 渠道

Telegram 渠道当前支持：

- 长轮询启动与优雅关闭。
- `streaming=true` 时由 Application 托管后台生成任务，通过占位消息和增量编辑实现流式输出。
- 同一 Telegram chat 或同一 session 同时只接受一个生成，新输入会立即提示忙碌而不进入 AgentMailbox 排队；streaming bot 可用 `/stop` 或生成中按钮按 request ID 停止。
- RP 标签展示投影、Markdown 到 Telegram HTML 的渲染与 4096 字符分块发送；原始 assistant content 不改写。
- `/start` 游玩入口卡、按钮角色选择、本地动态 `/help`、精简 Bot 菜单及后端高级斜杠命令透传。
- Inline Keyboard callback 使用带 10 分钟 TTL、chat/session 归属校验和一次性 claim 的短 token。
- 每个 bot 绑定 `workspace_id + story_id`，启动时解析一个默认 session；未 pin 的 chat 使用 bot 默认 session，显式切换后会在当前 chat 内钉住 session。
- `/sessions` 使用标题和短 ID 展示会话；`/session_create <title>` 直接新建并进入，无标题命令或按钮进入标题输入状态，支持 `/cancel`。
- `proxy`、流式编辑间隔、最小编辑字符数、请求超时等参数由 `channels/settings.yaml` 的 bot 配置控制。

### 核心引擎

| 模块 | 说明 |
|---|---|
| `agent/agent.py` | `RPGGameAgent` 组合根与公开门面，只组装组件并委托公开 API |
| `agent/runtime/` | session-scoped lifecycle/resources、会话操作、主模型、Context 与工具服务 |
| `agent/mailbox/` / `command/` | FIFO/取消与命令 dispatcher/handlers/models |
| `agent/turn/` | 单轮请求、不可变执行计划、runner、固定 hooks、transaction 与同步/流式共享编排 |
| `agent/sub_agents/memory/` / `status/` | 子 Agent 实现、结果模型、解析和稳定 prompt/schema |
| `context/` | canonical models、结构化构建、LLM 边界渲染与上下文诊断 |
| `session/` | `SessionManager` 门面与 history/progress/grouping/models 职责拆分 |
| `tooling/` | 跨 Agent/RP Module 共享的 `BaseTool` 与 `ToolRegistry` |
| `scene/` | 场景状态跟踪（时间/地点/属性） |
| `character.py` | 角色卡只读适配，通过 `rpg_data` 按 session/story 读取挂载 |
| `lorebook.py` | 世界书只读适配，通过 `rpg_data` 按 session/story 读取挂载 |
| `status/` | 状态表薄适配，通过 `rpg_data` 按 session 读取 SQLite document 真源 |
| `rp_modules/` | RP 玩法模块框架，当前包含 Narrative Outcome 剧情裁定与 Dice 低层随机模块 |
| `summary/` | 对话摘要压缩 |
| 顶层 `llm_client/` | 供 Agent、Memory、Dream、TTS 及未来 Media planner 使用的稳定 HTTP/SSE 客户端、DTO 与 Provider facade |
| 顶层 `llm_service/` | LLMProvider 抽象、OpenAI/llama provider、LLMManager、llm.yaml 解析与本地 llama runtime |
| 顶层 `rp_memory/dream/` | 无框架的 Shallow/Deep 选源、Map/Reduce、Evidence 校验与 proposal 规划领域 |
| 顶层 `dream_service/` | 独立 Dream HTTP 进程、DreamClient 与进程内 async 生成任务 |
| 顶层 `play_events/` | Dream/Derivation 共用的无框架事件 wire contract、内部令牌解析与 loop-owned HTTP publisher |
| 顶层 `rpg_media/` | 来源快照、VisualBrief、图片 Provider 契约、内容寻址存储与媒体用例 |
| 顶层 `media_service/` | 独立 Media HTTP 进程、MediaClient 与数据库持久任务 worker |
| 顶层 `rpg_tts/` | 正文标准化、确定性分段、缓存指纹与 MP3 内容寻址存储 |
| 顶层 `tts_service/` | 独立 TTS HTTP 进程、TTSClient 与数据库持久任务 worker |

顶层 `rp_memory/` 是独立记忆系统包：在线部分负责检索、索引、规划、召回和 rerank，`rp_memory.dream` 负责无框架的离线长期记忆归纳；Persistent Memory 的读写真源仍统一位于 `rpg_data` SQL。`rpg_core` 只读取其 Context 投影。顶层 `llm_service/` 是独立 LLM 服务实现，负责 provider 路由、配置解析、OpenAI-compatible provider 与本地 llama.cpp runtime。业务进程只依赖 `llm_client/`，不导入 `llm_service/`。

### Agent 组合式门面与 turn 事务

`RPGGameAgent` 是组合根和公开门面，不再拥有队列、Context、工具、模型选择或 turn 阶段实现。公开接口保持 `send()`、`send_stream()`、`cancel_current_turn()`、命令、Context inspection、history、角色绑定和 reload/switch；内部稳定接口为幂等 `initialize()`、只读 `session_id` / `session_manager` 与 `reindex_memory()`。

```text
RPGGameAgent（composition root + public facade）
├── AgentMailbox              FIFO、stream task、requestId 取消、错误事件
├── AgentSessionService       角色、history、truncate/delete/reset、reload/switch
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

- `context/models.py` 是 `Message` / `Role`、各层数据和 `RPGContext` 的唯一实现；调用方直接从 canonical 模块导入，不保留旧路径重导出。
- `RPGContextBuilder` 消费预组装的 `FixedLayerData`，并负责摘要、记忆、状态表和用户扩展块，产出结构化 `RPGContext`。
- 主 Agent 的 `send()`、`send_stream()` 和 `context-preview` 统一通过 `SessionManager.context_history()` 读取历史投影：仅排除 `summary_processed=true` 的单条消息，不校验 `summary_batch_id`、batch 文件、`overall.md` 或 turn 完整性；当前 turn 的 user message 仍来自事务 scratch。
- `FixedLayerAssembler` 通过 contributors 统一装配固定层 section，例如核心 RP 指令、文本输出格式、世界书、角色卡和已启用 RP Module 的静态契约。
- `ContextRenderer` 只在 LLM 请求边界把结构化层渲染为 message objects。
- `ContextInspector` 只服务 `/context`、日志和调试输出，不进入主业务数据模型。
- `context/usage.py` 封装最终渲染 messages 的共享 token 估算和 provider usage 归一化。`context-preview` 只返回下一轮主 Context 估算并驱动圆环/正文门禁；准确 usage 只来自正常 `/turn` 返回或 `/stream` 的 `turn_completed.payload.usage`，仅用于回复气泡和详情复盘，当前不落库。
- 主 Agent LLM 选择使用 `config default < story override < session override`：Story 详情编辑页立即保存故事默认，SessionRoom context 圆环左侧设置会话覆盖；生成中切换只影响下一 turn，不触发自动压缩。
- `rpg_core/rp_modules/` 是 RP 业务模块体系，不做通用 skill 体系。`narrative_outcome` 负责主 Agent 的剧情分支随机裁定；`dice` 只保留表达式解析和手动调试命令；`text_output_format` 仍由 fixed layer contributor 约束 assistant 正文使用 RP XML 标签。
- 内置模块登记在 `rpg_rp_module_catalog`。Story 挂载是 Session 的能力上限，新 Story 默认挂载当前全部内置模块；Session 可覆盖模块启用状态和稀疏配置，但不能重新启用 Story 已停用的模块。每次 preview/turn 都解析独立不可变快照，生成中的配置修改只影响下一 turn。
- `RP_MODULES` 是模块动态运行态层，位置在 `STATUS_TABLES` 后、`USER_MESSAGE` 前。Narrative Outcome 平时依靠 fixed contract 判断隐式变数；检测到明确随机意图时加入本轮强制裁定指令。若 StatusSubAgent 已预裁定，本轮不再注入 Narrative Outcome fixed section，只在动态层注入最终结果和明确的状态工具边界。

结构化 Context 与实际 provider messages 共用以下顺序：

1. Fixed Layer：固定 RP 指令、Story Prompt、当前玩家角色标签块、文本输出格式、已启用 RP Module 静态契约、世界书、带 PLAYER/NPC 标注的角色卡。
2. Persistent Memory / Summary。
3. Hot History。
4. 独立的动态 system messages 固定为 Story Memory / Status Tables / Recalled Memory / RP Modules。
5. User Message。

`ContextRenderer` 不合并 system message：Fixed、Persistent Memory、Summary 各自先发送，Hot History 保留包括 system 在内的原始 role 与位置，之后再发送 Story Memory、Status Tables、Recalled Memory、RP Modules 和当前 User Message。动态层按 `Story Memory → Status Tables → Recalled Memory → RP Modules` 排列：低频累积的 Story Memory 前置，当前状态放在按 turn 变化的 Recall 之前。Recall 块自身明确声明它只是可能过时的历史参考；与当前 scene、状态表、玩家角色绑定或更新事实冲突时，以当前/更新状态为准。

“只能有一条且必须首位 system”不是跨模型/provider 的通用约束，而是具体 API 或 chat template 的兼容能力。局域网原生 llama.cpp/Qwen 部署应使用 `--jinja` 与 `--chat-template` / `--chat-template-file` 在服务端正确渲染多段、交错 system，不应改变本项目的全局 Context 语义。

prefix cache 以 provider 最终序列化/tokenized 请求的共同前缀为准，不以结构化层、消息边界或整条 system message 的应用层 hash 为独立缓存单元。动态 system 位于 Hot History 后，变化不会截断更早的稳定指令和历史前缀；rolling history 自身发生滑窗时仍会改变共同前缀。整条 system/context hash 不同仍可能命中更早的部分 token，实际缓存效果只看 provider usage 返回的 hit/miss token。开启 `verbose_logging` 后，`TurnPreparation` 会在最终主 Agent messages 和 tool schemas 完成后、首次主 LLM 调用前输出一次不含正文的 `contextHash` / `systemHash` / `toolsHash`、逐消息 `index/role/hash/chars`、role 计数和工具名；后续工具 round 不重复输出这条初始指纹。

`当前场景` 在数据层仍是必须挂载到 story 的 `status_kind="scene"` SQL document，在主 Context 中则是高优先级 `[scene]` user prefix，不进入普通 `STATUS_TABLES`。Status Route 只在本轮涉及且存在可用 scene 工具时选择它；scene 不走普通表工具或 deferred。默认关闭结构编辑时，已有字段都保持可见且可改 value，`scene_attr` 只接受现有 key，`scene_time` 只在已有 `时间` key 时出现，`scene_del_attr` 不注册；空 scene 完全不暴露写工具。完整差异见 [scene 的特殊语义](docs/agent-turn-orchestration.md#scene-的特殊语义)。

StatusSubAgent 的 Outcome、Route、scene Update 和单表 Update 是不同缓存族。隔离 Update 使用稳定 system contract，并按 `Recent Conversation → User Action → Selected State Target` 排列 user 内容；每次仍只下发当前目标 schema。MemorySubAgent 的 Recall、Story、Summary、Batch Summary 和 Overall Summary 同样各自保持一条稳定 system + 一条动态 user，并使用独立 source。`verbose_logging` 会按 source 使用与主 Agent 相同的无正文指纹口径，并记录 SubAgent provider usage 的 cache hit/miss/rate。完整说明见 [缓存前缀与观测](docs/agent-turn-orchestration.md#缓存前缀与观测)。

普通 `STATUS_TABLES` 层展示 session 运行时表 ID、表名、`description`（用途与更新规则）和完整 KV，不展示模板来源或通用挂载范围。绑定角色的表单独进入“角色状态表”段落并按角色名分组；当前只用角色绑定辅助模型理解所属角色，不扩展其它行为。

RP Modules 采用上下文分层策略：

- 稳定、低频变化的规则只放进 fixed layer，例如主 Agent 仍需裁定时 Narrative Outcome 的“何时裁定、调用哪个工具、不得替玩家做选择”；预裁定成功的 turn 不再重复注入这组规则。
- 文本输出格式是默认启用的 fixed layer 约束；RP 正文使用 `<rp-narration>` 和 `<rp-character name="...">` 标签区分旁白与角色发言。
- 高频或临时模块状态才进入 `RP_MODULES` 动态层；Narrative Outcome 为明确随机意图加入本轮强制指令，并把 StatusSubAgent 已暂存的裁定结果注入主 Agent 首次调用。
- 未预裁定时，主 LLM 的 RP schema 只暴露高层 `rp_story_outcome(reason, actor?)`；已预裁定时，该工具同时从主 Agent schema 和可执行 registry 移除。两种情况都不暴露表达式、DC、随机数、权重或低层 Dice 工具。
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

`rp_memory/` 是一个独立的记忆子系统，不再把离线归纳、向量、keyword FTS、原始 markdown 扫描和 query 规划混在一个类里。当前结构按职责拆分为五个职责层：

```text
rp_memory/
├── dream/       Shallow/Deep source selection、Map/Reduce 与 proposal 规划
├── planning/    QueryPlan 生成与 query rewrite
├── retrieval/   SqlVec / keyword / raw markdown recall
├── rerank/      基于 LLMProvider 的可选最终重排
└── storage/     SQLite repository、vector index、text index
```

### Dream 长期记忆

Dream 是手动、Session 级的离线归纳链路。Persistent Memory 的真源是 SQLite 类型化事实账本，
每条记忆保存不可变 revision、主历史 Evidence 和 `active | retired | superseded` 生命周期；主 Agent
只注入 Evidence 仍匹配当前主消息的 active revision，每个 Session 最多 64 条 active。

账本只保存跨 turn 仍值得复用的世界内持久事实；OOC 内容、用户偏好、系统或 Provider 配置以及 scene
等易变当前状态都不属于 Dream。旧 `persistent_memory.json` 不再读取或创建；升级时已有文件会原样保留，
系统不会自动删除它，也不会把它迁移为 SQL 事实。

- **Shallow**：从仍能精确匹配当前主消息 ID/version/hash 的 story memory，以及来源消息仍完整属于原 batch 的 summary 提炼；派生材料只用于增量整理，不能因局部缺失全局退休旧事实。
- **Deep**：以当前主消息表的 IC/GM user/assistant 历史为事实真源；Full 可全局校准，Incremental 只处理新增、修改、删除及 Evidence 受影响的记忆。
- **Incremental / Full**：与 Shallow/Deep 独立组合，形成四种手动运行方式。
- Map、分层 Reduce 和最终 Proposal 共用 `map_concurrency` 并发上限；若 Reduce 不收敛而触发代码侧候选截断，Full Deep 会禁用基于“候选缺席”的退休，只保留显式证据驱动的修订或替换。
- 每次运行先持久化 proposal。WebUI 可逐项选择并编辑文本、类型、认知状态和显著度；Apply 在串行 repository worker 中取得 SQLite `IMMEDIATE` 写锁，事务内重新捕获并再次确认 history/source/ledger 快照后原子提交。
- Dream 使用进程内异步生成任务。页面不自动轮询；服务重启把未完成任务标记为 `interrupted`，运行中若终态落库连续失败也会尽力中断残留 `generating`。WebUI 的“检查并重试”会携带原 proposal ID：已完成时只刷新终态，仅在该 ID 仍为无本地 task 的孤儿 `generating` 时按原 depth/scope 新建替代任务，不重复消耗 LLM。
- Dream proposal 与 Session Derivation 只在 `ready / failed / interrupted` 落库后发布紧凑终态事件。通知失败不回滚任务；完整结果仍必须通过原 GET 接口读取。
- retired 事实仍保留稳定 Memory ID 和历史 revisions。后续 Dream 若从新的有效 Evidence 再次提取出同一规范化事实，ADD 会在原 ID 上追加新 revision 并恢复为 active；手动 Restore 仍只适用于旧 revision Evidence 尚有效的记录。
- `/clear` 清空 Session Dream 账本、revision/Evidence、proposal 和增量 state/manifests；历史编辑/截断不会自动运行 Dream，但 Evidence 失效会立即阻止旧记忆继续进入 Context。

Play WebUI 从 Session 设置菜单进入 Dream Memory 管理页。Dream Service v1 不提供入站鉴权，
因此服务配置强制使用 loopback 地址（默认 `http://127.0.0.1:8014/dream/v1`），非 loopback
监听会在配置加载时失败；它不可用时只影响该管理页，不影响正常游玩。

### Play 后台终态事件

后台事件使用独立于 Agent 正文 SSE 的全局链路：

```text
DreamTaskManager / SessionDerivationWorker
  -> 领域 NotificationSink
  -> play_events.PlayEventPublisher
  -> POST /play-api/v1/internal/events
  -> Play API 进程内 Hub
  -> GET /play-api/v1/events/stream
  -> 根 Providers 下唯一 PlayEventBridge
```

- `POST /internal/events` 使用 `RPG_WORLD_PLAY_EVENT_TOKEN` Bearer 鉴权；浏览器订阅端不携带该内部令牌。
- 每个订阅者使用容量 64 的内存队列，慢订阅满载时丢弃最旧事件；SSE 约每 15 秒发送 heartbeat，并声明 3 秒重连间隔。
- 事件不写 SQL outbox，不补发、不确认消费。断线期间的状态恢复仍依赖 Dream Proposal / Derivation Job GET 接口。
- 首版要求 Play API 单进程、单 worker。WebUI 严格解析并在 Zustand 内存保存最近 50 条事件；独立通知模块只负责展示、未读和清除状态，清除不会确认消费或修改后台任务。通知中心不做 Toast、导航、自动 Query invalidation 或 localStorage。

### 运行链路

```text
进程启动 / session 初始化
  -> MemoryManager.create() / initialize()
     - 只建立本地 text index、keyword、raw-md 和 watcher coordinator
     - 不访问 LLM Service
首次 recall / reindex
  -> 并发懒加载 embedding、QueryPlanner 和 reranker
     - 远程能力失败时保留 keyword / raw-md / rule-based fallback
     - 未就绪能力在后续调用中重试
用户 query
  -> MemoryManager session operation lock
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
- `LlamaQueryPlanner` / `OpenAIQueryPlanner`：可选的 LLM query planner，通过 `await LLMClientManager.get().get_provider(...)` 获取远端 provider facade
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
- `llm_service/llm.yaml`：仅由 LLM Service 读取的 LLM 强相关配置，例如 `memory.embed`、`memory.query_planner`、`memory.rerank` 的 provider、model、model_path、上下文窗口、温度、超时

业务代码不读取 `llm.yaml`，只通过 `await LLMClientManager.get().get_provider(biz_key)` 使用远端契约；`LLMManager` 与 `llm_service.config` 只在 LLM Service 进程内使用。

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
- `MemoryManager.create()` / `initialize()` 只初始化本地能力，不产生 LLM HTTP I/O；远程能力在首次 `recall()` / `reindex()` 懒加载
- 同一 session 的 recall、index、reindex 和 close 由单一 async lock 串行；不同 session 之间可并行
- watchdog 回调只使用 `call_soon_threadsafe` 向所属 loop 入队，不在 watcher 线程运行 embedding、索引或 SQLite
- 文件读取、hash、chunk 和 SQLite 操作通过 `asyncio.to_thread()` 移出 Agent 事件循环
- `QueryPlanner` 是增强能力，不是主链路硬依赖
- keyword 查询格式始终由 tokenizer 保证
- raw md 的 `always` 是主召回策略，`fallback_only` 是触发策略；一旦进入候选池，raw md 候选与其他候选同样参与 merge、hybrid scoring 和 rerank
- 检索层优先保持可解释的分数融合，避免把排序黑箱化

## 配置

### 配置文件拆分

根目录不再保留 `settings.yaml` / `llm.yaml`。配置按进程和业务边界拆分：

| 文件 | 职责 |
|---|---|
| `rpg_core/settings.yaml` | 核心业务配置：Agent 行为、scene 的 LLM 结构写权限、主 Context 正文拒绝阈值、memory 检索参数、核心日志 |
| `agent_service/settings.yaml` | Agent 服务监听参数、AgentClient/LLMClient，以及 Derivation 终态事件 publisher 地址、超时和令牌环境变量名 |
| `channels/settings.yaml` | CLI / Telegram 渠道行为、Telegram bot、渠道日志 |
| `play_api/settings.yaml` | Play API 监听参数、后台事件 subscriber 队列/heartbeat/retry 与 Play API 日志 |
| `rpg_media/settings.yaml` | VisualBrief Demo planner、默认图片 Provider 与 Local file Demo 图片目录 |
| `media_service/settings.yaml` | Media 服务监听、MediaClient 地址/超时与 worker 并发参数 |
| `rpg_tts/settings.yaml` | TTS 正文标准化版本、speech biz key 与单段字符上限 |
| `tts_service/settings.yaml` | TTS 服务监听、TTSClient、LLMClient 与持久 worker |
| `dream_service/settings.yaml` | Dream 服务监听、DreamClient/LLMClient、Map/Reduce 参数及终态事件 publisher；64 条 active 是固定数据层不变量 |
| `llm_service/settings.yaml` | LLM 服务监听、Bearer 令牌环境变量名、本地 llama 并行模型数、`llama_shutdown_grace_ms` 与日志 |
| `play_webui/play_webui.config.json` | Play WebUI 通用配置入口，例如 SessionRoom 历史分页窗口和 context 正文门禁阈值 |
| `llm_service/llm.yaml` | LLM provider、模型、上下文窗口、speech 音色、温度、超时等 LLM 强相关配置 |

`RPG_WORLD_LLM_SERVICE_TOKEN` 存在时会覆盖默认令牌，LLM Service 与所有调用进程必须使用相同值。环境变量缺失或仅含空白时，各进程共同使用内置的 `rpg-world-local-token`，LLM Service 记录 warning 但继续启动；该默认值只适合本地开发，非本地部署应显式覆盖。Agent Service 可以在 LLM Service 暂不可用时启动并将 health 标为 degraded，实际推理请求会以独立错误快速失败。LLM Service 自身的 `/health` 故意免 Bearer 鉴权，只表示进程与配置健康；health 成功不代表调用方 token 正确，token 会在 catalog、chat、embedding、rerank、speech 等受保护请求上验证。

`RPG_WORLD_PLAY_EVENT_TOKEN` 由 Agent、Dream 和 Play API 共同读取，用于保护 `/play-api/v1/internal/events`。缺失时三者共同回退到 `rpg-world-local-event-token` 并记录 warning；该默认值同样只用于本地开发。浏览器的 `/events/stream` 订阅不读取或暴露该令牌。

独立入口会统一接管 Loguru、Python `logging` 和 Uvicorn 日志，同时保留控制台输出，并在项目根目录写入 `logs/agent.log`、`llm.log`、`dream.log`、`media.log`、`tts.log`、`play_api.log`、`telegram.log` 或 `cli.log`。默认每个文件达到 20 MB 后滚动，保留最近 10 个 ZIP 压缩归档；`logs/` 不纳入版本控制。各进程的 `logging` 配置均支持 `directory`、`rotation_size_mb`、`retention_count`、`compression` 和 `console_enabled` 覆盖。

正文门禁由 `play_webui` 的 `session.contextUsage.inputBlockThresholdRatio` 和 Core 的 `agent.context_window_reject_threshold_ratio` 独立控制，合法范围均为 `(0, 1]`、默认均为 `0.9`。前端非法值回退 `0.9`，Core 非法值会阻止启动；两侧都只计算不含当前待发送 input 的主 Agent Context。

上述 YAML 配置使用同一套 `base + profiles` 结构，通过 `RPG_WORLD_PROFILE` 选择 profile，默认读取各文件自己的 `default_profile`。`local` / `test` / `prod` 是固定 profile 名称；不需要在 `profiles.*.file` 里声明覆盖文件。当前 profile 会自动读取同级覆盖文件，例如：

```text
rpg_core/settings.local.yaml
channels/settings.local.yaml
agent_service/settings.local.yaml
llm_service/settings.local.yaml
play_api/settings.local.yaml
rpg_media/settings.local.yaml
media_service/settings.local.yaml
dream_service/settings.local.yaml
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
    scene:
      allow_runtime_key_changes: false
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
    cli:
      workspace_id: demo_workspace
      story_id: 1
      session_id: ""
      session_title: CLI
      streaming: true
  logging:
    log_level: DEBUG
    directory: logs
    rotation_size_mb: 20
    retention_count: 10
    compression: zip
    console_enabled: true
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
    directory: logs
    rotation_size_mb: 20
    retention_count: 10
    compression: zip
    console_enabled: true
```

Play API 的监听和日志放在 `play_api/settings.yaml`。

LLM provider 选择放在 `llm_service/llm.yaml`：

```yaml
base:
  biz:
    agent.main:
      kind: chat
      provider_key: deepseek_v4_flash
    dream.shallow:
      kind: chat
      provider_key: deepseek_v4_flash
    dream.deep:
      kind: chat
      provider_key: deepseek_v4_flash
    memory.rerank:
      kind: rerank
      provider_key: memory_rerank
      rerank_model_type: qwen3_logit
```

`rerank_score_weight` 是排序业务参数，留在 `rpg_core/settings.yaml`；不要写入 `llm_service/llm.yaml` 的 provider 配置。

工作区不再放在旧 JSON 配置中。API/WebUI 通过请求参数或 catalog session 解析 workspace；
Telegram/CLI 通过 `channels/settings.yaml` 中各自的 `workspace_id + story_id` 绑定故事。`session_id` 可留空，此时启动时创建系统生成 ID 的默认 session；非空时只校验并加载既有 session。旧 `workspace` 字段、`cli_direct` 默认 ID 和用户自定义 session ID 创建入口都不再保留。`rpg_data` 中的 workspace 根目录来自 `rpg_workspaces.root_path`；workspace/story/session 运行目录使用 workspace-relative 路径时由 `rpg_data.settings` 解析并阻止路径逃逸。

## Session ID 规则

`session_id` 只能包含英文字母、数字和下划线，规则为 `^[A-Za-z0-9_]+$`。
所有创建入口都由 `rpg_data` 生成全局唯一 session ID；用户只允许指定 title。Play WebUI 创建 session 时会在 `rpg_data` 绑定 `workspace_id + story_id`，会话内链路只使用全局短 `session_id`。

### 会话历史字段

会话消息写入 `rpg_session_messages`，冷备份写入 `rpg_session_backup_messages`。`SessionManager` 保持公开门面，内部由 `session/history.py` 管消息与持久化、`progress.py` 管 summary/story-memory 行标记、`grouping.py` 管 turn 算法。数据库自增 `id` 映射为 `Message.uid`；`turn_id` 和 `seq_in_turn` 由会话层管理，持久化路径必须写入正数。主消息表约束同一 session 内 `(turn_id, seq_in_turn)` 唯一；冷备份表保持追加语义，不做唯一约束。

summary 和剧情记忆提取进度标记在 `rpg_session_messages` 对应消息行上；剧情记忆条目写入 `rpg_session_story_memories`，且必须关联正数 `turn_id`。summary 的 `keep_recent_rounds` 和批次切分仍按显式 turn/round 分组；异常 turn metadata 在写入或加载边界失败，不再恢复 user-anchor / pair 降级分组。

Dream 的 Persistent Memory、不可变 revisions、Evidence、proposal/items 和增量 manifests 全部由 `rpg_data` SQLite 管理。`rpg_core` 构建 Context 时只读取 Evidence 仍有效的 active 当前 revision；Session `/clear` 清空这些 Dream SQL 状态。旧 `persistent_memory.json` 既不读取也不新建，但升级不会自动删除已有文件。

Agent Context 与历史展示分离：Play/Agent 的 `history` / `history-page` 接口始终返回完整未删除历史；主 Agent Context 则按 `summary_processed` 字段逐条过滤，`true` 不进入 Context，`false` 进入。只要本次投影中过滤过消息，Summary Layer 可以尝试加载现有 `overall.md`；文件不存在或为空时摘要层为空，但已处理消息仍不回流 Context。删除、清空、编辑回滚和 turn truncate 只直接修改历史，不删除摘要文件、不重置其它消息标记，也不自动重新归纳。

## 测试

默认测试全部 mock LLM 调用，无需 API key：

```bash
uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests rpg_media/tests media_service/tests rpg_tts/tests tts_service/tests dream_service/tests -q
```

当前测试会 mock LLM、Telegram SDK 和网络调用。若本地缺少 `pytest-asyncio`，`rpg_core/tests/agent/command/test_command.py` 中的 async 测试会提示需要安装异步 pytest 插件。覆盖范围包括：

- `channels/tests/`：ChannelAdapter、CLI、Telegram 渠道和渠道侧会话流程。
- `rpg_core/tests/`：按源码领域镜像组织；Agent 测试继续按 runtime/mailbox/command/sub_agents/turn/tools 分组，其余 Context、Session、Summary、RP Modules、Scene、Status 与 utils 各自归档。
- `rp_memory/tests/`：memory 检索、索引、规划、rerank，以及 Dream 选源、分批、Map/Reduce 和 retirement policy。
- `dream_service/tests/`：Dream source adapter、进程内生成生命周期、HTTP/Client 契约与错误隔离。
- `rpg_data/tests/`：catalog、消息、状态、Dream proposal/ledger/revision/Evidence、原子 Apply 与 `/clear` 数据语义。
- `llm_service/tests/`：LLM HTTP/SSE 客户端契约、鉴权、provider 配置、manager 路由与 llama 本地 runtime。
- `play_api/tests/`：Play API workspace/session/scene/turn/stream、Dream service 代理、characters、lorebook、status-tables 和 ops 等契约。
- `rpg_media/tests/`：来源指纹、简报、Provider、图片魔数/存储与高层媒体用例。
- `media_service/tests/`：HTTP 契约、持久队列、取消、重试和重启恢复。
- `rpg_tts/tests/` / `tts_service/tests/`：正文清洗与分段、MP3 存储、缓存复用、HTTP Range、持久队列与恢复语义。

Telegram 测试已覆盖入口卡、角色选择、会话菜单、命令帮助、系统生成 ID 的创建切换、
停止生成、RP/Markdown 渲染、流式编辑节流和长文本分块。后续修改 Telegram 行为必须补对应测试。

Dream 后端与 Play WebUI 的聚焦验证为：

```bash
uv run python -m pytest \
  rp_memory/tests/test_dream.py \
  rpg_data/tests/test_dream_memory_service.py \
  dream_service/tests \
  play_api/tests/test_dream.py \
  play_api/tests/test_events.py -q
cd play_webui && npm run build
```

修改 Agent 组合或 turn pipeline 时，先跑组件专项与 Agent Service 契约，再跑完整基线和 Core integration：

```bash
uv run python -m pytest \
  rpg_core/tests/agent/test_agent.py \
  rpg_core/tests/agent/mailbox/test_agent_mailbox.py \
  rpg_core/tests/agent/runtime/test_agent_lifecycle.py \
  rpg_core/tests/agent/runtime/test_agent_context_service.py \
  rpg_core/tests/agent/runtime/test_agent_tool_service.py \
  rpg_core/tests/agent/turn/test_turn_hooks.py \
  rpg_core/tests/agent/turn/test_turn_runtime_factory.py \
  rpg_core/tests/agent/turn/test_turn_orchestration.py -q
uv run python -m pytest agent_service/tests -q
INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q
SERVICE_INTEGRATION_TEST=1 uv run python -m pytest tests/integration -m service_integration -q
```

真实 Dream 模型验收是显式 opt-in。`llm_service/llm.test.yaml` 可把 `dream.shallow` 与
`dream.deep` 路由到当前配置的 `deepseek_v4_flash`；测试使用临时 Session，只断言结构化契约与
Evidence/Proposal 不变量，不固定模型措辞，也不得把 API key 写入测试或日志：

```bash
# 终端 A：LLM Service 自身也必须使用 test profile，保持运行直到验收结束
RPG_WORLD_PROFILE=test uv run python -m run_llm

# 终端 B：显式调用 dream.shallow / dream.deep 的真实 Provider
RPG_WORLD_PROFILE=test DREAM_LIVE_TEST=1 \
  uv run python -m pytest dream_service/tests/integration -m dream_live -q

# 验收结束后回到终端 A，按 Ctrl-C 关闭 LLM Service
```

测试本身只连接已经运行的 LLM Service，不会代为启动或切换远端进程的 profile。没有
`DREAM_LIVE_TEST=1` 时真实 Provider 测试跳过；一旦显式开启，Provider 或 schema 失败应让测试失败。

跨服务覆盖矩阵见 [`docs/backend-integration-matrix.md`](docs/backend-integration-matrix.md)。`service_integration` 使用随机本地端口启动独立 LLM、Agent、Media 与 Play API 测试进程，覆盖真实 HTTP/SSE、服务生命周期、SQLite 和媒体落盘；模型与图片 Provider 使用 deterministic fake，不访问公网。

## 当前实现优先级

1. **P0：Play WebUI 主体验与 Play API 契约**。优先保障 session 房间、SSE/turn、Session 图像、workspace、characters、lorebook、status-tables、ops 等 Web 主链路。
2. **P1：核心数据、上下文与记忆链路**。确保角色卡、世界书、状态表、summary、story memory 和 rp_memory 在全局 `session_id` 语义下稳定可用。
3. **P2：Telegram/CLI 轻量入口稳定性**。保持真实 Telegram 长轮询、会话菜单、stream/non-stream、异常回复、命令菜单和运行配置可靠。
4. **P3：玩法模块与沉浸式细节**。骰子、战斗、物品等新增体验型能力优先沉淀到 Play WebUI，并通过受控工具和状态读写接入核心。

## 相关文档

- [`docs/agent-turn-orchestration.md`](docs/agent-turn-orchestration.md) — Agent turn、Outcome、状态路由、事务和 deferred 完整编排
- `CLAUDE.md` — 完整架构文档和技术细节
- `rpg_core/settings.yaml` — 核心业务、数据路径、memory 参数
- `agent_service/settings.yaml` — Agent 服务监听与 AgentClient 默认值
- `llm_service/settings.yaml` — LLM 服务监听、鉴权与本地 runtime 配置
- `channels/settings.yaml` — CLI / Telegram 渠道配置
- `play_api/settings.yaml` — Play API 监听与日志
- `dream_service/settings.yaml` — Dream 监听、DreamClient/LLMClient 与 Map/Reduce 分批配置
- `rpg_media/settings.yaml` — VisualBrief Demo planner 与图片 Provider 配置
- `media_service/settings.yaml` — Media 服务、客户端与 worker 配置
- `play_webui/play_webui.config.json` — Play WebUI 通用配置入口
- `llm_service/llm.yaml` — LLM provider、模型、上下文窗口和超时配置
