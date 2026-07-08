# RPG World — 故事数据管理与 LLM Agent 交互子系统

RPG World 是 nanobot 项目的一个子系统，专注于故事驱动的 RPG 数据管理和 LLM Agent 交互。提供角色卡管理、世界书管理、状态表管理、场景上下文构建、记忆召回与 RP 模块运行态等功能。


## 产品路线与定位

RPG World 的长期产品目标是成为一个 **AI RPG World / 沉浸式 RP 平台**，而不是单一聊天机器人。后续体验重心调整为：

- **Play WebUI（前台游玩端）**：主客户端，承载沉浸式 RP 聊天、场景状态、玩家扮演角色、角色/NPC 面板、剧情日志、行动输入、骰子/战斗/物品等玩法机制。
- **Telegram**：轻量入口、App 推送、快速回复和兜底交互；不再作为复杂沉浸式 UI 的主要承载面。
- **CLI**：开发调试和最小交互入口。

设计原则：Play WebUI 负责 Web 主体验和管理入口，Telegram 负责触达效率；二者必须共享同一套 workspace/session 语义，避免同一个故事在不同渠道分裂。Play WebUI 通过 Play API 复用 `rpg_core`、`rp_memory` 和 `rpg_data` 后端能力，不在前端复制角色、世界书、状态或 RP 规则。

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
- Story 主数据中，`summary` 是短摘要，`first_message` 是会话开场首条消息模板，`story_prompt` 是 story 专属固定系统提示词，会通过 fixed layer 参与上下文渲染。当前 schema 变更直接体现在 `0001_initial.sql` 与 `0002_demo.sql`，不新增迁移版本。
- 角色卡和世界书条目属于 workspace，通过挂载表关联到 story；同一个角色卡或世界书条目可以挂载到多个 story。
- 状态表模板属于 workspace，通过 `rpg_story_status_tables` 挂载到 story；创建 session 时会把已挂载模板复制为该 session 独立副本。
- Play 侧公开 `session_id` 是全局唯一短 ID，创建入口由 `rpg_data` 生成，当前生成格式为 `s_` + 10 位小写字母/数字；创建 session 时绑定 `workspace_id + story_id`，之后会话内接口只传 `session_id`。
- CLI / Telegram 启动时也先通过 Agent service 的 `ensure_session(workspace_id, story_id, session_id, title)` 解析会话；`session_id` 为空时创建系统生成 ID 的 session，非空时只校验并加载既有 session。
- `rpg_session_profiles` 保存会话标题、描述、`player_character_id` 和 `player_character_snapshot_json`；`rpg_sessions.id` 保持稳定，用作 URL 和 Agent session id。

玩家扮演角色绑定是 session 级能力：

- 状态只暴露 `bound | invalid`。缺失绑定、角色不存在、未挂载到当前 story、snapshot 损坏或 snapshot mount/story 不匹配，都统一视为 `invalid`。
- Play WebUI 新建或进入 session 后统一在 SessionRoom 内处理选角；invalid 时打开不可取消弹窗，绑定前禁用输入区。设置菜单可以切换当前扮演角色，切换只影响后续 user 消息展示和后续 prompt 语义，不重写历史。
- CLI / Telegram / Agent API 允许建立空 session；绑定前普通消息只返回固定编号角色列表，不调用 LLM、不写 user history。
- 绑定与切换统一走 Agent 命令 `/role_bind <序号>`。WebUI 的 `PATCH /play-api/v1/sessions/{session_id}/player-character` 会转发到 Agent service，由 Agent service 将角色 ID 映射为当前 story 已挂载角色序号并执行同一命令；不要在 Play API/DataManager 中直接写绑定。
- 绑定成功且 main history 为空、story `first_message` 非空时，`SessionRoleService` 会追加一条 assistant 开场消息到 main 和 backup history；已有 history 时不会重复追加。

Play API 是 catalog session 到 Agent 服务的边界层：它通过 `session_id` 反查 workspace/story，并只把全局 `session_id` 传给 Agent 服务运行态；Agent service 的 `/chat/history`、`/chat/commands`、`/chat/send`、`/chat/stream`、`/chat/stop` 不再接收 workspace。当前会话内接口集中在 `/play-api/v1/sessions/{session_id}/...`，例如 `history`、`scene`、`commands`、`turn`、`stream`、`stop`、`player-character`。workspace、characters、lorebook、status-tables、ops 等管理接口也在 Play API 下；旧的 `chat.py`、`scene.py`、`commands.py` router 只保留占位，不再挂载为主接口。

状态表在 `rpg_data` 中采用 SQLite document 真源：

- 模板表和会话表都在 SQL 行内保存封装后的 `document_json`，对外通过 `StatusTableDocument` / `StatusTableRow` 等 dataclass 暴露，不把原始 JSON 字符串作为正文数据返回。
- SQLite 同时记录模板、story 挂载、session 副本、来源关系、排序、`metadata_json` 和 `status_kind`；`status_kind` 当前只允许 `scene` / `normal`。
- 状态表模板属于 workspace，通过 `rpg_story_status_tables` 挂载到 story；创建 session 时会把当时已挂载模板的 `document_json` 复制到 `rpg_session_status_tables`，`origin="template_copy"`。
- 模板后续修改不影响已有 session 副本；运行时直接新建的会话表写入 `rpg_session_status_tables`，`origin="session_native"`。
- `DataServiceGateway` 初始化时只 materialize workspace/story/session 运行目录并初始化缺失的 session 状态表副本；service 不扫描目录补业务索引，也不维护状态表 type 表、workspace-relative 状态表文件路径或 CSV 内容源。
- Bootstrap 默认不删除不在 SQL 索引里的 workspace/story/session 目录。只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才会执行启动清理；日志会输出每个删除项和汇总计数。
- `当前场景` 是 `status_kind="scene"` 的特殊状态表，仍受 story 挂载约束；多张 scene 表存在时消费排序第一张。
- `rpg_data` 通过 `rpg_workspaces.root_path` 定位 workspace 根目录，workspace/story/session 运行目录使用 workspace-relative 路径时统一由 `rpg_data.settings` 解析并阻止路径逃逸。

### Telegram 渠道

Telegram 渠道当前支持：

- 长轮询启动与优雅关闭。
- `streaming=true` 时通过编辑消息实现流式输出。
- Markdown 到 Telegram HTML 的渲染与 4096 字符分块发送。
- `/start`、后端斜杠命令透传，以及 Telegram 菜单命令规范化。
- 每个 bot 绑定 `workspace_id + story_id`，启动时解析一个默认 session；未 pin 的 chat 使用 bot 默认 session，显式切换后会在当前 chat 内钉住 session。
- `/sessions` 会话菜单、按钮切换会话、`/session_create [title...]` 立即创建系统生成 ID 的 session；`/cancel` 保留给 Telegram 专属二段交互状态。
- `proxy`、流式编辑间隔、最小编辑字符数、请求超时等参数由 `channels/settings.yaml` 的 bot 配置控制。

### 核心引擎

| 模块 | 说明 |
|---|---|
| `agent/` | LLM Agent 引擎（消息队列、chat loop、子 Agent、命令系统） |
| `context/` | 结构化 RPG 上下文构建、LLM 边界渲染、上下文诊断 |
| `scene/` | 场景状态跟踪（时间/地点/属性） |
| `character/` | 角色卡只读适配，通过 `rpg_data` 按 session/story 读取挂载 |
| `lorebook/` | 世界书只读适配，通过 `rpg_data` 按 session/story 读取挂载 |
| `status/` | 状态表薄适配，通过 `rpg_data` 按 session 读取 SQLite document 真源 |
| `rp_modules/` | RP 玩法模块框架，当前包含 Dice 骰子模块 |
| `summary/` | 对话摘要压缩 |
| 顶层 `llm_service/` | LLMProvider 抽象、OpenAI/llama provider、LLMManager、llm.yaml 解析与本地 llama runtime |

顶层 `rp_memory/` 是独立记忆系统包，负责检索、索引、规划、召回和 rerank；顶层 `llm_service/` 是统一 LLM 服务包，负责 provider 路由、配置解析、OpenAI-compatible provider 与本地 llama.cpp runtime。

### Agent turn 事务

`send()` 和 `send_stream()` 的 RP 主链路通过 `AgentTurnTransaction` 管理本轮写入。这里的事务不是长数据库事务，而是“一轮 Agent turn 的内存 scratch + 短 commit 点”：

- 进入 LLM 前，user message 不直接写入 `SessionManager.append()`，而是暂存在 `MessageScratch`。
- `StatusSubAgent` 和 scene 工具绑定到 scratch 版 `SceneTracker` / `ScratchStatusManager`，状态表变更以 `StatusTableDocument` copy-on-write 方式暂存到 `StatusDocumentScratch`。
- 上下文构建读取 scratch 后的 history 与 scene/status，因此主 LLM 能看到本轮预更新状态。
- LLM 完整成功后，事务一次性提交 staged user message、assistant message 和 staged status documents；`send_stream()` 只有 commit 成功后才发送最终 DONE。
- WebUI 停止生成走 `requestId` 精准取消：Play API `/sessions/{session_id}/stop` 转发到 Agent service `/chat/stop`，被取消的 stream turn 只丢弃 scratch，不发送 DONE，也不提交消息、状态或 usage。
- WebUI `retry/edit` 保持历史语义可预期：如果目标是最后一个已持久化 turn，先截断该 turn 再用同一 turn id 重新流式发送；如果目标不是最后一轮，不改写旧历史，而是追加一个新的 turn。
- 持久化 session 的 commit 在 `rpg_data` database atomic 中执行，不跨 LLM 调用持有数据库事务；`history_enabled=False` 是测试/内存模式，只回滚内存 history，不承诺补偿已写入的外部 status manager。
- summary compression 和 story memory extraction 是 commit 后副作用；失败只记录 warning，不回滚已提交 turn。

事务生命周期有日志覆盖：begin 构建失败、send/send_stream 异常、commit 失败、commit 成功摘要和 post-commit 副作用失败都会记录，便于排查 turn 是否进入 scratch、是否提交、是否在副作用阶段失败。

### 上下文与 RP 模块

`rpg_core/context/` 的主流程保持结构化数据，直到发送给 LLM 前才由 Jinja2 模板统一渲染：

- `RPGContextBuilder` 消费预组装的 `FixedLayerData`，并负责摘要、记忆、状态表和用户扩展块，产出结构化 `RPGContext`。
- `FixedLayerAssembler` 通过 contributors 统一装配固定层 section，例如核心 RP 指令、文本输出格式、世界书、角色卡和已启用 RP Module 的静态契约。
- `ContextRenderer` 只在 LLM 请求边界把结构化层渲染为 message objects。
- `ContextInspector` 只服务 `/context`、日志和调试输出，不进入主业务数据模型。
- `context/usage.py` 封装 context/token 用量快照和 provider usage 归一化。`context-preview` 只返回估算摘要；准确 usage 只来自正常 `/turn` 返回或 `/stream` 的 `turn_completed.payload.usage`，当前不落库。
- `rpg_core/rp_modules/` 是 RP 业务模块体系，不做通用 skill 体系。当前 `dice` 模块通过 `RPModuleRegistry` 注册固定层契约、工具和斜杠命令；`text_output_format` 由 fixed layer contributor 约束 assistant 正文使用 RP XML 标签。
- `RP_MODULES` 是模块动态运行态层，位置在 `STATUS_TABLES` 后、`USER_MESSAGE` 前。Dice MVP 默认不注入动态运行态，只在固定层声明稳定规则。

当前发送顺序按缓存稳定性和 RP 注意力组织：

1. Fixed Layer：固定 RP 指令、文本输出格式、已启用 RP Module 静态契约、世界书、角色卡。
2. Persistent Memory / Summary。
3. Hot History。
4. Story Memory / Recalled Memory / Status Tables / RP Modules。
5. User Message。

`当前场景` 不作为普通状态表进入 `STATUS_TABLES`。它由 `SceneTracker` 作为高优先级 user prefix 合入最终用户消息，确保故事时间、地点和场景状态被模型重点关注，并随 user message 进入历史用于后续有序归纳。`rpg_data` 用 `status_kind="scene"` 表达这一类特殊状态；未挂载到 story 时 session 不会感知 scene，也不会注册 scene 工具。

RP Modules 采用上下文分层策略：

- 稳定、低频变化的规则只放进 fixed layer，例如 dice 的“何时掷骰、必须调用工具、不得替玩家做选择”。
- 文本输出格式是默认启用的 fixed layer 约束；RP 正文使用 `<rp-narration>` 和 `<rp-character name="...">` 标签区分旁白与角色发言。
- 高频或临时模块状态才进入 `RP_MODULES` 动态层；Dice MVP 没有动态层内容。
- 工具 schema 常驻注册，但骰子点数只在 LLM 调用 `rp_dice_roll` / `rp_dice_check_dc` 或用户显式输入 `/roll` / `/check_dc` 时产生。
- `/rp_modules`、`/rp_module dice`、`/roll`、`/check_dc` 都由 `CommandDispatcher` 在 LLM 前拦截，不进入对话历史。

Assistant 回复的 `content` 是唯一真源：带标签全文会原样进入 SSE、历史和数据库，不再通过 `metadata.messageDisplay` 保存旁白/角色分段。Play WebUI 只在展示层做容错解析；解析失败、半截标签或非标准流内容必须原文展示，不丢消息。

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
| `rpg_core/settings.yaml` | 核心业务配置：Agent 行为、workspace 数据目录、memory 检索参数、核心日志 |
| `agent_service/settings.yaml` | Agent 服务监听参数、非 Agent 进程访问 Agent 服务的客户端默认值、Agent 服务日志 |
| `channels/settings.yaml` | CLI / Telegram 渠道行为、Telegram bot、渠道日志 |
| `play_api/settings.yaml` | Play API 监听参数、Play API 日志 |
| `llm_service/llm.yaml` | LLM provider、模型、上下文窗口、温度、超时等 LLM 强相关配置 |

所有这些 YAML 都使用同一套 `base + profiles` 结构，通过 `RPG_WORLD_PROFILE` 选择 profile，默认读取各文件自己的 `default_profile`。`local` / `test` / `prod` 是固定 profile 名称；不需要在 `profiles.*.file` 里声明覆盖文件。当前 profile 会自动读取同级覆盖文件，例如：

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

会话消息写入 `rpg_session_messages`，冷备份写入 `rpg_session_backup_messages`。数据库自增 `id` 映射为 `Message.uid`；`turn_id` 和 `seq_in_turn` 由 `SessionManager` 管理。
剧情记忆写入 `rpg_session_story_memories`，续提游标保存在 `rpg_sessions.story_memory_last_turn_id`。

## 测试

所有测试 mock LLM 调用，无需 API key：

```bash
uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests -q
```

当前测试会 mock LLM、Telegram SDK 和网络调用。若本地缺少 `pytest-asyncio`，`rpg_core/tests/test_command.py` 中的 async 测试会提示需要安装异步 pytest 插件。覆盖范围包括：

- `channels/tests/`：ChannelAdapter、CLI、Telegram 渠道和渠道侧会话流程。
- `rpg_core/tests/`：命令分发、上下文、scene、session、summary、AgentManager。
- `rp_memory/tests/`：memory 检索、索引、规划、rerank。
- `llm_service/tests/`：LLM provider 配置、manager 路由与 llama 本地 runtime 协议。
- `play_api/tests/`：Play API workspace/session/scene/turn/stream、characters、lorebook、status-tables 和 ops 等契约。

Telegram 测试已覆盖会话菜单、命令规范化、系统生成 ID 的创建流程、流式编辑节流、
Markdown 渲染和长文本分块。后续修改 Telegram 行为必须补对应测试。

## 当前实现优先级

1. **P0：Play WebUI 主体验与 Play API 契约**。优先保障 session 房间、SSE/turn、workspace、characters、lorebook、status-tables、ops 等 Web 主链路。
2. **P1：核心数据、上下文与记忆链路**。确保角色卡、世界书、状态表、summary、story memory 和 rp_memory 在全局 `session_id` 语义下稳定可用。
3. **P2：Telegram/CLI 轻量入口稳定性**。保持真实 Telegram 长轮询、会话菜单、stream/non-stream、异常回复、命令菜单和运行配置可靠。
4. **P3：玩法模块与沉浸式细节**。骰子、战斗、物品等新增体验型能力优先沉淀到 Play WebUI，并通过受控工具和状态读写接入核心。

## 相关文档

- `CLAUDE.md` — 完整架构文档和技术细节
- `rpg_core/settings.yaml` — 核心业务、数据路径、memory 参数
- `agent_service/settings.yaml` — Agent 服务监听与 AgentClient 默认值
- `channels/settings.yaml` — CLI / Telegram 渠道配置
- `play_api/settings.yaml` — Play API 监听与日志
- `llm_service/llm.yaml` — LLM provider、模型、上下文窗口和超时配置
