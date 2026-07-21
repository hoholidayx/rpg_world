# RPG World

RPG 世界管理子系统——故事数据管理、场景上下文构建、LLM Agent 交互。
记忆检索已经拆成 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三个独立 retriever；`HybridRetriever` 只负责组装与融合，不承载底层检索实现。关键词检索通过 `memory.keyword_tokenizer` 选择 `jieba`、`bigram` 或 `both`，配置使用 `keyword_k` / `hybrid_keyword_weight`。raw markdown 由 `memory.raw_md_mode` 控制，`always` 是主召回策略，`fallback_only` 是补候选触发策略。


## 产品路线

RPG World 的产品定位从“Telegram 优先的 RP 聊天入口”升级为“WebUI 主体验 + Telegram 辅助触达”的 AI RPG World 平台：

- **Play WebUI**：前台游玩端，面向玩家，提供沉浸式 RP 聊天、场景 HUD、角色/NPC 信息、剧情日志、行动输入、会话图像与玩法模块交互。
- **Telegram**：保留为轻量入口、推送通知、快速回复和 WebUI 不可用时的兜底交互，不承载复杂沉浸式 UI。

Play WebUI 是唯一 Web 主体验，承担玩家游玩、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口。前端不得复制核心业务规则；渠道之间必须共享 workspace/session 映射，避免故事分裂。Play API 当前挂载 sessions、workspace、characters、lorebook、status-tables、ops 管理接口；不要恢复 Dashboard API/WebUI。

Play WebUI 的会话定位采用 `rpg_data` catalog 中的全局短 `session_id`。创建 session 时绑定 `workspace_id + story_id`；进入会话后，前端 URL 和会话内请求只传 `session_id`，由 Play API 反查 workspace/story 并调用 Agent 服务。不要恢复前端每次传 `workspace + story_id + session_id` 的三元 locator。

## 启动

```bash
# 可选：非本地部署应让 LLM Service 与所有调用进程使用同一个 Bearer 令牌。
# 未设置时各调用方共同使用内置的 rpg-world-local-token，LLM Service 会警告。
export RPG_WORLD_LLM_SERVICE_TOKEN=replace-with-a-secret
# 启用 SessionRoom OpenAI Speech TTS 时设置；仅 LLM Service 读取。
export OPENAI_API_KEY_TTS=replace-with-an-openai-key

# 推荐：一键启动 LLM、Agent、Dream、Media、TTS、Play API（Ctrl-C 优雅停止全部子进程）
uv run python -m run_all
# 或：uv run rpg-world-up

# 也可按需分别启动（不要与 run_all 同时运行）
# LLM 服务（唯一读取 llm.yaml/密钥并持有 Provider/本地 llama runtime）
uv run python -m run_llm
# Agent 服务（唯一持有 AgentManager/RPGGameAgent，读取在线 memory/Context 投影）
uv run python -m run_agent
# Dream 服务（独立离线归纳并写入 rpg_data SQL 账本）
uv run python -m run_dream
uv run python -m run_media
# 或：.venv/bin/python -m run_media
uv run python -m run_tts
uv run python -m run_play_api
uv run python -m run_telegram
uv run python -m run_cli

# 或直接 uvicorn
uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir agent_service --reload-dir media_service --reload-dir tts_service --host 127.0.0.1 --port 8000

# Play WebUI 开发服务器
cd play_webui && npm run dev

# CLI / Telegram 通过 agent_client 访问 Agent 服务
uv run python -m channels.cli.repl

# 验证导入
uv run python3 -c "from rpg_core.status import StatusManager; print('ok')"
```

## 架构总览

```
rpg_world/
├── run_llm.py                     # LLM 服务入口（唯一 provider/config/llama owner）
├── run_agent.py                   # Agent 服务入口（唯一 agent runtime owner）
├── run_dream.py                   # Dream 服务入口（离线记忆提炼 owner）
├── run_media.py                   # Media 服务 + 持久任务 worker 入口
├── run_tts.py                     # TTS 服务 + 持久任务 worker 入口
├── run_play_api.py                # Play API 入口
├── run_all.py                     # 一键拉起六个独立后端进程的前台入口
├── run_cli.py                     # CLI 入口（AgentClient）
├── run_telegram.py                # Telegram 入口（AgentClient）
├── commons/                       # 共享配置加载与 JSON/YAML 类型别名
├── channels/                     # 多渠道适配器
│   ├── base.py                   #   ChannelAdapter 抽象基类
│   ├── config.py                 #   ChannelsSettings 配置加载
│   ├── runner.py                 #   ChannelRunner（生命周期管理）
│   ├── cli/                      #   CLI 渠道（Rich + prompt_toolkit）
│   │   ├── adapter.py            #     CLIAdapter
│   │   └── repl.py               #     独立入口
│   ├── telegram/                 #   Telegram 渠道（python-telegram-bot）
│   │   ├── __init__.py
│   │   └── adapter.py            #     TelegramAdapter（支持 stream/non-stream）
│   └── tests/                    #   渠道测试（mock LLM / Telegram SDK）
│       ├── conftest.py           #    共享 fixture（FakeAgent, FakeBot）
│       ├── test_base.py          #    ChannelAdapter 基类
│       ├── test_cli.py           #    CLIAdapter
│       ├── test_manager.py       #    AgentManager
│       └── test_telegram.py      #    Telegram 会话/命令/渲染/流式发送
├── rpg_core/                     # 核心逻辑（无框架依赖）
│   ├── agent/                    #   LLM Agent 引擎
│   │   ├── agent.py              #     RPGGameAgent — 组合根 + 公开 API 门面
│   │   ├── manager.py            #     AgentManager 单例（统一 agent 缓存）
│   │   ├── protocol.py           #     transport-neutral stream/cancel 类型
│   │   ├── telemetry.py          #     CallRecord / TurnStats
│   │   ├── runtime/              #     lifecycle、resources、session/model/context/tool services
│   │   ├── mailbox/              #     QueueItem、FIFO、stream task、取消与错误映射
│   │   ├── command/              #     dispatcher、handlers 与 AgentCommandTarget
│   │   ├── turn/                 #     plan/runtime、runner、固定 hooks、transaction、orchestrator
│   │   ├── sub_agents/           #     BaseSubAgent / SubAgentContext + memory/status 领域包
│   │   └── tools/                #     Agent state/file tool 适配
│   ├── scene/                    # 场景状态（时间/地点/属性）
│   ├── context/                  # models、builder、fixed layer、渲染边界和诊断
│   ├── session/                  # SessionManager 门面 + history/progress/grouping
│   ├── tooling/                  # 共享 BaseTool / ToolRegistry
│   ├── jinja/                    # Jinja2 模板
│   ├── character.py              # 角色卡（rpg_data 只读适配）
│   ├── lorebook.py               # 世界书（rpg_data 只读适配）
│   ├── status/                   # 状态表业务策略、Context policy 与 Agent facade
│   ├── rp_modules/               # RP 玩法模块（narrative_outcome / dice 等，不是通用 skill）
│   ├── summary/                  # 对话摘要
│   ├── settings.py               # Settings 单例
│   └── utils/
│       ├── manager_base.py       #   BaseManager（注册 FileWatcher）
│       ├── stats_formatter.py    #   LLM 统计格式化
│       ├── tokenizer.py          #   TokenCounter 抽象
│       ├── watcher.py            #   FileWatcher（watchdog 文件监控）
│       └── path_utils.py         #   路径解析
├── rpg_data/                     # Play catalog + 数据 service gateway
│   ├── migrations/               #   SQLite schema / demo data
│   ├── repositories/             #   Peewee records + repository
│   └── services/                 #   catalog / character / lorebook / status services
├── rpg_media/                    # 无框架媒体领域：来源/简报/Provider/图片存储
├── media_service/                # Media HTTP adapter、客户端与持久队列 worker
├── dream_service/                # Dream HTTP adapter、客户端与进程内生成任务
├── play_events/                  # 后台终态事件 wire contract + async HTTP publisher
├── rpg_tts/                      # 无框架 TTS 领域：正文清洗、分段、缓存与 MP3 存储
├── tts_service/                  # TTS HTTP adapter、客户端与持久队列 worker
├── rp_memory/                    # 记忆系统（检索、索引、规划、召回、rerank）
│   ├── dream/                    #   Shallow/Deep 选源、Map/Reduce 与 proposal 规划
│   ├── planning/                 #   QueryPlan / planner
│   ├── retrieval/                #   sqlvec / keyword / raw md retrievers
│   ├── rerank/                   #   pointwise rerank
│   └── storage/                  #   SQLite repository / vector / text index
├── llm_client/                   # 独立 LLM 服务的公共 HTTP/SSE 客户端与 DTO
├── llm_service/                  # 独立 LLM 服务：HTTP、provider/config/manager + 本地 llama runtime
├── play_api/                     # Play WebUI 专用 FastAPI 应用
│   ├── main.py                   #   入口 + CORS + lifespan（不启动渠道）
│   ├── settings.yaml             #   Play API 进程配置（监听 + 日志）
│   ├── settings.py               #   PlaySettings 单例
│   ├── dream_client.py           #   DreamClient 生命周期封装
│   ├── media_client.py           #   MediaClient 生命周期封装
│   ├── backends/                 #   AgentClient / rpg_data 后端适配
│   └── routers/
│       ├── sessions.py           #   session APIs + history/history-page/scene/commands/turn/stream
│       ├── dream.py              #   Session Dream proposal / memory 代理
│       ├── media.py              #   Session 媒体代理与图片流式转发
│       ├── tts.py                #   Session TTS 任务与 Range 音频代理
│       ├── characters.py         #   角色库 + story 挂载 APIs
│       ├── lorebook.py           #   世界书 + story 挂载 APIs
│       ├── status_tables.py      #   状态表模板、story 挂载、session 表 APIs
│       ├── ops.py                #   运维清理和删除确认 APIs
│       ├── chat.py               #   legacy placeholder；不要恢复为主入口
│       ├── commands.py           #   legacy placeholder；不要恢复为主入口
│       ├── scene.py              #   legacy placeholder；不要恢复为主入口
│       └── workspace.py          #   workspace APIs
├── play_webui/                   # Play WebUI：Next.js + React + TypeScript
│   ├── src/app/                  #   App Router
│   ├── src/features/             #   home/session/characters/worldbook/status/settings features
│   ├── src/lib/api/              #   Play API client
│   └── src/components/           #   Timeline、Scene HUD、输入区等
└── data/                         # 运行数据文件
    └── {workspace}/
        ├── assets/images/        #   {sha256}.png|jpg|webp
        └── stories/{story_id}/{session_id}/
            ├── rpg_summaries.json
            ├── summaries/
            └── memory_vectors.db
```

## 进程隔离架构

RPG World 采用 **独立 Agent、LLM、Dream、Media、TTS 服务 + 独立入口** 模式。根目录不再提供持有业务运行时的聚合 supervisor；
`run_all.py` 仅作为可选的前台进程编排器，负责启动/停止独立子进程，不合并任何运行时。
它在启动每个服务前检查对应端口：仅当占用者确认是 Python 或 uv 进程时终止并等待释放，
其他进程保持不动并使启动失败；六个服务配置为重复端口时同样拒绝启动。
只有 `run_agent.py` 进程持有 `AgentManager` 和 `RPGGameAgent`。Agent 进程使用 `rp_memory` 做召回与 Context 投影；`run_dream.py` 使用无框架的 `rp_memory.dream` 做离线提炼并经 `rpg_data` 写 Persistent Memory。`rpg_core` 不运行 Dream consolidation、不写该账本，二者也都不得持有 Provider。
只有 `run_llm.py` 进程读取 `llm_service/llm.yaml`、Provider 密钥并持有 OpenAI/llama Provider 与本地 llama runtime；Agent、Memory、Dream、TTS 及未来 Media planner 只能通过 `llm_client` 调用它。
Play API、CLI、Telegram 不创建 agent，不缓存 agent，不配置 llama，只通过
`agent_service.client.AgentClient` 访问 Agent 服务。

Media service 是另一个独立进程，只持有 `rpg_media`、`rpg_data`、图片 Provider 与数据库持久 worker；它不导入 Agent runtime，也不持有 llama worker。Play API 作为独立后端链路的接入边界：聊天走 `AgentClient`，媒体走 `MediaClient`，TTS 走 `TTSClient`。Media service 中断只使媒体接口返回 503，不得阻塞 SessionRoom、composer 或 Agent SSE。

TTS service 与 Media service 同级，只持有 `rpg_tts`、`rpg_data`、持久 worker 和 `llm_client`。`TTSApplicationService` 统一决定已提交 assistant message 资格、正文清洗与分段、fingerprint、cache 命中/失效、retry 资格和 worker interrupted 策略；worker 只调用该 application service。`TTSDataService` 只提供 typed 查询/read model、Job/Cache/Blob/Part CRUD、条件 claim/transition、引用查询和调用方准备结果后的原子 completion。TTS 不导入 Agent runtime，不写消息 metadata/SSE/localStorage；OpenAI Speech Provider、模型配置和密钥仍只由 LLM Service 持有。TTS service 中断只影响回复气泡的朗读控件。

Dream service 是 Session 级离线记忆提炼边界，只持有 `rp_memory.dream`、`rpg_data` 与 loop-owned `llm_client`。它通过 `dream.shallow` / `dream.deep` biz key 获取远端 Provider facade，不导入 Agent runtime、`MemorySubAgent` 或 `llm_service`。Play API 只用 `DreamClient` 代理手动管理请求；Dream 中断不得影响 Agent Context 构建、聊天或其它服务。v1 不提供入站 Bearer 鉴权，配置层强制监听 localhost/loopback IP；非 loopback host 必须启动失败，不支持非本地暴露。

Dream Proposal 状态机、恢复、Apply、Persistent Memory 生命周期与 Context projection 的唯一业务 owner 是 `rp_memory.dream`；Story Memory 的 normalize、exact dedupe、merge、Evidence、version 和 Context projection 统一归 `rp_memory.story_memory_service`。`rpg_data` 只通过 `dream_memory` / `story_memory` 提供 frozen DTO、CRUD、CAS、批量读写与无业务语义事务，不得恢复状态迁移、动作分支、active-limit、来源指纹、Evidence 有效性或 Story Memory 合并策略；业务调用方不得直接访问 `gateway.database` 或 Peewee record。

`DataServiceGateway` 保持数据库生命周期与 Data Service 注册表职责，不需要移除；进程/Agent composition root 从 Registry 取得 `sessions`、`plot_scheduling`、`dream_memory`、`story_memory`、`status`、`media`、`tts` 等具体 service 后逐项注入，领域/application service 不得持有整个 Gateway。`rpg_core` 内只有 `agent/agent.py` 与 `context/factory.py` 是合法 Gateway 获取点；Main LLM、工具、Session 命令、Character/Lorebook Manager 与 fixed-layer contributor 都必须显式接收各自的窄 Port 或具体 Read/Data Service。公开类型化持久化边界统一使用 Service 语义，新的大业务聚合入口命名为 `*DataService`，Repository 仅为 `rpg_data` 内部 Peewee 实现；既有简单 Character/Lorebook CRUD 可保留明确的 `*ReadService` / `*ManagementService`，不要为后缀或形式统一机械复制 application service、adapter 和 DTO 转换层。`rpg_data` 的边界是“决定数据如何可靠、高效、原子存取”，不是“只能做简单 CRUD”：复杂查询、分页、批量、CAS、数据库级原子操作和高效 read model 都应留在数据层。Session、Memory、Status、Media 与 TTS 的 canonical 存储契约位于对应的 `rpg_data.model.*` 模块，旧 `rpg_data.models` 暂作兼容重导出。

`rpg_data` 的正式分层、依赖、事务、类型所有权与 Review 规范见 [`docs/rpg-data-architecture.md`](docs/rpg-data-architecture.md)；`todos/` 中的整改计划只保留实施历史和待办顺序，不作为长期边界定义。

后台终态事件不进入 Agent 正文 SSE。`SessionDerivationWorker` 与 `DreamTaskManager` 只依赖各自的类型化 NotificationSink，在 `ready / failed / interrupted` 成功落库后通知；service composition root 注入映射适配器，再由无框架 `play_events` 的 loop-owned async publisher 调用 Play API。`rpg_data` 不持有 publisher 或 WebUI 语义。通知是 best-effort，失败只记录 warning，GET Proposal/Derivation Job 仍是事实真源。

Play API 独占进程内事件 Hub：`POST /play-api/v1/internal/events` 使用 `RPG_WORLD_PLAY_EVENT_TOKEN` Bearer 鉴权，`GET /play-api/v1/events/stream` 为 WebUI 提供全局 SSE。每订阅者有界队列满时丢最旧事件；不实现 SQL outbox、补发或消费确认。首版只支持 Play API 单进程/单 worker。WebUI 根 `Providers` 只挂一个 EventSource bridge，严格解析并把最近 50 条事件留在 Zustand 内存；独立 `features/notifications` 模块可展示、标记已读和清除这些事件，但不得据此 Toast、跳转、自动刷新 Query、回写任务状态或写 localStorage。

```
run_llm            -> llm_service.main:app        -> Provider + local llama runtime
run_agent          -> agent_service.main:app
run_dream          -> dream_service.main:app      -> rp_memory.dream + rpg_data + llm_client
run_media          -> media_service.main:app      -> rpg_media + rpg_data
run_tts            -> tts_service.main:app        -> rpg_tts + rpg_data + llm_client
run_play_api       -> play_api.main:app           -> AgentClient + DreamClient + MediaClient + TTSClient
run_cli            -> channels.cli.repl           -> AgentClient
run_telegram       -> channels.telegram.runner    -> AgentClient
```

根目录还提供同级快捷入口，便于单独调试和查找：

```
run_llm.py -> llm_service.main
run_agent.py -> agent_service.main
run_dream.py -> dream_service.main
run_media.py -> media_service.main
run_tts.py -> tts_service.main
run_play_api.py -> play_api.main
run_telegram.py -> channels.telegram.runner
run_cli.py      -> channels.cli.repl
```

Agent runtime 只存在于 Agent 服务进程：

```
agent_service 进程
├── AgentManager 单例
│   ├── RPGGameAgent 实例池（只按全局 session_id 缓存）
│   ├── FileWatcher（watchdog 文件监听）
│   └── rp_memory（召回、索引与 Persistent Memory 只读投影）
├── llm_client -> http://127.0.0.1:8012/llm/v1
└── HTTP + SSE: /agent/v1
```

LLM Service 默认监听 `http://127.0.0.1:8012/llm/v1`，优先使用环境变量 `RPG_WORLD_LLM_SERVICE_TOKEN` 的静态 Bearer 令牌。环境变量缺失或仅含空白时，LLM Service 与 `llm_client` 共同回退到内置的 `rpg-world-local-token`，服务继续启动并在启动阶段记录一次 warning；该默认值只用于本地开发，非本地部署应显式覆盖。Agent Service 不因 LLM Service 暂不可用而拒绝启动，health 返回 degraded；需要 catalog 或推理的请求返回 503/SSE `LLM_SERVICE_UNAVAILABLE`。LLM Service 自身的 `/health` 故意免 Bearer 鉴权，只表示进程存活与配置是否加载，不校验调用方 token；catalog、chat、stream、embedding、dimension、rerank 和 speech 仍全部鉴权。调用方凭据是否有效由首次受保护请求确认，不得把 health 成功解释为 token 有效。

`RPG_WORLD_PLAY_EVENT_TOKEN` 必须在 Agent、Dream 与 Play API 间一致；缺失时三者共同使用只适合本地开发的 `rpg-world-local-event-token` 并 warning。它只保护内部事件 POST，不得下发给浏览器 EventSource。

### Agent / Memory / LLM 异步与线程模型

Agent 进程只有一个服务事件循环，单个 session 的 turn 继续由 `AgentMailbox` FIFO 串行；不同 session 可以在网络 await 或 memory await 期间并发推进。`llm_client` 不再维护同步 HTTP 客户端，`health()`、catalog、provider 解析、chat/stream、embedding、dimension 和 rerank 都是原生 async API。`LLMServiceClient` 在首次使用时绑定当前 loop，之后禁止跨 loop 或线程复用；`LLMClientManager.aconfigure()` / `areset()` / `aset_for_tests()` 会 await 关闭被替换实例的 `httpx.AsyncClient` 连接池。业务代码不得用 `asyncio.run()`、同步 HTTP 或 run-awaitable bridge 包装这些 API。

```text
Agent event loop
├── session A AgentMailbox ── turn FIFO ── await LLM / await Memory
├── session B AgentMailbox ── turn FIFO ── await LLM / await Memory
└── one loop-owned LLMClientManager / httpx.AsyncClient

MemoryManager(session A)
├── one async operation lock：recall / index / reindex / close 串行
├── watcher callback thread：只 call_soon_threadsafe(source_id)
└── loop-owned consumer：去重 source → await embedding → to_thread(file/hash/chunk/SQLite)

LLM Service
├── async HTTP/SSE boundary
└── DirectLlamaRuntime：每个不可变 model cache key 一个 actor thread + FIFO
```

`MemoryManager.create()` 只创建本地壳，`initialize()` 只建立 text index、keyword、raw-md 与 watcher coordinator，二者都不访问 LLM Service。首次 `recall()` / `reindex()` 才并发懒解析 embedding、query planner 和 reranker；远端能力失败时继续使用 keyword/raw-md/rule-based fallback，未就绪能力在之后调用中重试。每个 MemoryManager 的操作锁只约束该 session，因此同 session 不会并发操作同一 SQLite/索引状态，不同 session 仍可并行。watchdog 所在线程不得执行索引、embedding 或 SQLite。

本地 llama 保持 LLM Service 进程内 actor 线程，不使用子进程。`request_timeout_ms` 从任务提交时开始计算，覆盖同模型队列等待与实际运行；排队任务超时/取消后不会执行，completion 使用 stopping criteria、stream 在 chunk 边界、rerank 在 document/native eval 边界协作停止。原生 embedding 或单次 eval 无法安全抢占时，HTTP/调用方会按时收到超时，actor 继续自然排空，且同 cache key 的下一任务必须等待它结束，绝不并发进入同一模型。关闭时先取消排队与活动任务，并最多等待 `llama_shutdown_grace_ms`；超过 grace 只记录仍在排空的 native call。

### RPG Media 与图片资产

`rpg_media/` 是与 `rpg_core/` 同级的无框架高级能力模块。v1 的用户链路是：手动选择 1–20 个连续已提交 turn，生成可检查和编辑的九字段 `VisualBrief`，再提交数据库持久异步任务。当前 `DemoVisualBriefPlanner` 是配置驱动的确定性实现，不发起外部文本模型调用；`VisualBriefPlanner` 保留可替换契约。未来 LLM planner 应通过 `llm_client` 复用通用 chat biz 选择，不硬编码 OpenAI/llama 等 Provider 黑名单；Media service 不读取 LLM 配置或创建 Provider，本地 llama runtime 只能由 LLM Service 持有。

来源快照保存 message ID、version、role、content、turn/seq，并以 SHA-256 指纹检测提交或重试前的历史变化。工作区图片只接受经魔数识别的 PNG、JPEG、WebP，原始内容写到 `{workspace_root}/assets/images/{sha256}.<ext>`。Blob 在数据库中按 `(workspace_id, sha256)` 去重；hash 不是业务 Asset ID，每次成功生成仍建立独立 UUID Asset，以保留不同的 Provider、简报、参数和来源语义。

Media Job 默认由单 worker 消费，无自动重试；服务启动时扫描 `queued`，创建/重试通过进程内事件即时唤醒，队列排空后阻塞等待而不轮询数据库。重启把遗留 `running/cancelling` 标成 `interrupted`，用户可显式重试。Session Gallery、背景引用与消息历史完全分离，不写入正文、message metadata、turn/SSE 或 localStorage。背景使用中的 Asset 禁止删除；最后一个 Asset 引用删除后才回收 Blob 行和文件。`/clear` 清除 Session Job/Gallery/背景但保留 Workspace Asset/Blob，Session 永久删除也依靠外键清理 Session 关联而保留 Workspace 资产。

上述来源、图库、删除、背景状态机与 worker 恢复规则统一由 `MediaApplicationService` 决定；`media_service` worker 不直接操作数据层。`MediaDataService` 只负责 typed CRUD/read model、CAS claim、引用查询、条件状态更新及调用方准备的原子 completion。

### 配置（`settings.yaml` / `llm.yaml` / WebUI config）

配置已拆分到各进程/模块目录：`rpg_core/settings.yaml` 管核心业务配置，`agent_service/settings.yaml` 管 Agent 服务监听、Agent/LLM 客户端和 Derivation 终态 publisher，`channels/settings.yaml` 管 CLI/Telegram 行为，`play_api/settings.yaml` 管 Play API 监听、事件 Hub 与日志，`dream_service/settings.yaml` 管 Dream 监听、客户端、Map/Reduce 参数和终态 publisher，`rpg_media/settings.yaml` 管简报与图片 Provider，`media_service/settings.yaml` 管 Media 监听、客户端与 worker，`rpg_tts/settings.yaml` 管正文清洗与分段，`tts_service/settings.yaml` 管 TTS 监听、客户端与 worker，`llm_service/settings.yaml` 管 LLM 服务监听/鉴权/runtime，`llm_service/llm.yaml` 仅供 LLM Service 解析 provider、模型、上下文窗口、speech 音色、温度、超时和密钥，`play_webui/play_webui.config.json` 管 Play WebUI 通用前端配置。YAML 配置采用 `base + profiles`，通过 `RPG_WORLD_PROFILE` 选择 profile，默认 `local`；同级 `settings.local.yaml` / `llm.local.yaml` 等 profile 覆盖文件会自动加载。
进程启停不由配置控制。监听和客户端配置通过 `ChannelsSettings` 的类型化属性访问（`channels/config.py`），外部调用不做字符串拼接：

```python
channels_settings.telegram_bots
channels_settings.cli_workspace_id
channels_settings.cli_story_id
channels_settings.cli_session_id
```

核心配置访问规则：

- 业务代码读取业务配置走 `rpg_core.settings.settings` 的属性或方法，例如 `settings.memory_settings`。
- Agent、Memory 等业务代码通过 `await LLMClientManager.get().get_provider(biz_key)` 获取远端 provider facade，不得导入 `llm_service`、读取 `llm.yaml` 或直接 new OpenAI/llama client。
- Dream Map/Reduce 分别只使用 `dream.shallow` / `dream.deep` biz key；test profile 可将二者显式覆盖到 `deepseek_v4_flash`，不得在 Dream 代码或文档复制 API key。
- TTS 通过 loop-owned `llm_client` 的 `get_speech_profile()` / `speech()` 使用 Speech 能力，不直接创建 OpenAI client，也不读取 Provider 密钥。
- `LLMManager` 与 `llm_service.config.resolve_biz_config()` 只允许在 LLM Service 实现内部使用。
- memory 检索、融合、chunk 和 rerank pool 参数都属于 `settings.yaml`，包括 `keyword_tokenizer`、`keyword_k`、`raw_md_mode`、`raw_md_min_results`、`hybrid_*_weight`、`rerank_candidate_k`、`rerank_score_weight`。
- `keyword_k` / `hybrid_keyword_weight` 是当前 keyword 架构配置；不要恢复旧 `bigram_k` / `hybrid_bigram_weight`。
- `llm.yaml` 的 `memory.rerank` 只放 provider/model/model_path/n_ctx/temperature/request_timeout_ms 等 LLM 参数，并且 `kind: rerank` 必须显式声明 `rerank_model_type`。

### AgentManager（`rpg_core/agent/manager.py`）

进程内单例，统一管理 `RPGGameAgent` 的创建与缓存。当前生产拓扑中只有 Agent 服务进程应持有实例池；Play API、CLI、Telegram 只能通过 `AgentClient` 访问它。

```python
from rpg_core.agent.manager import AgentManager

agent = AgentManager.get_or_create(session_id="mygame_01")
await agent.initialize()
```

单个进程内，所有模块通过同一个 `AgentManager` 获取 agent，确保 FileWatcher
只初始化一次、BaseManager 缓存一致。跨进程不共享这些对象。

`AgentManager` 的缓存键只包含全局唯一 `session_id`；`RPGGameAgent` 也只按该 ID 解析 catalog session 和运行目录，不再接收 workspace 作为运行态 locator。`api_key` 不再作为 Agent service schema、AgentClient 参数或缓存键。LLM provider / key 选择统一走 `llm_service/llm.yaml`。
跨模块初始化只能调用公开且幂等的 `RPGGameAgent.initialize()`；不要恢复 `_ensure_initialized()`，也不要读取 Agent 私有字段。可信内部命令协作者只使用 `AgentCommandTarget` 的 `session_id`、`session_manager`、`reindex_memory()` 与公开操作。
所有入口必须先解析出有效 catalog session；Telegram/CLI 通过 `channels/settings.yaml`
配置的 `workspace_id + story_id + optional session_id + session_title` 调用 Agent service
`/chat/session/ensure`。

### Play catalog 与 session 定位

`rpg_data` 的数据关系是：workspace 下有多个 story，story 下有多个 session；角色卡和世界书条目属于 workspace，并通过 `rpg_story_characters`、`rpg_story_lorebook_entries` 挂载到 story。同一个角色卡或世界书条目可以挂载到多个 story，挂载表只禁止同一 story 内重复挂载。

Story 主数据字段中，`summary` 是短摘要，`story_prompt` 是 Story 专属固定系统提示词，会通过 fixed layer 参与上下文渲染。会话开局真源是 `rpg_story_openings` 中按顺序保存的 0–3 条稳定 Opening（标题＋正文）；旧 `rpg_stories.first_message` 物理列只供 `0018_story_openings.sql` 迁移读取，不得用于新生产路径。Opening 正文与 Story Prompt 当前只支持白名单变量 `{USER_PLAY_ROLE_NAME}`；数据库和 API 返回原始模板，选中 Opening 在首次绑定且历史为空时渲染后持久化，Story Prompt 在 turn snapshot 中按 session 角色渲染。未知单花括号变量在保存边界失败，不执行 Jinja、表达式或递归替换。第一条 Opening 是默认项；CLI/Telegram 与未指定 Opening 的调用方使用它。

状态表的 SQLite `document_json` 仍是模板表和会话表正文真源，SQL 同时保存模板、Story 挂载、Session 副本、来源关系、排序和 `status_kind`。`status_kind` 只允许 `scene | normal`；状态表必须挂载到 Story 后才能绑定该 Story 的可选角色挂载。新 Session 的复制策略由 `rpg_core.session.SessionCatalogService` / `SessionStatusLifecycleService` 决定，`rpg_data.StatusDataService` 只复制调用方明确给出的 mount ID，或原子应用调用方准备好的 typed reset plan。模板后续修改不影响既有 Session 副本。`rpg_data` bootstrap 仅为既有缺失副本执行兼容性 materialize，不承载新的 Session 创建策略，也不硬编码 demo 数据。Bootstrap 默认保留 SQL 未索引目录，只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才允许清理并记录结果。

Session 生命周期业务统一归 `rpg_core.session`：角色有效性、首次绑定、Opening 默认/回退和渲染归 `SessionRoleService`；Story/Session 默认挂载归 `SessionCatalogService`；`/clear`、Derivation 状态机/继承、永久删除资格与 runtime 目录补偿分别归 reset、derivation、deletion application service。`rpg_data.sessions` 聚合角色/Opening read model、Session/profile/job 持久化、调用方指定的复制/删除、复杂查询与原子事务，但不得恢复玩家文案、默认选择、状态机推进或清理矩阵。

`当前场景` 是 `status_kind="scene"` 的特殊状态表，展示名可以自定义，但仍必须挂载到 story 才会被 session 感知。多张 scene 表存在时，v1 消费排序第一张 active scene。LLM 结构写权限由 `agent.scene.allow_runtime_key_changes` 控制且默认关闭：现有字段继续完整注入并允许更新 value，但不能新增、删除或重命名 key；只有显式开启后才恢复非锁定 key 的运行时增删能力。该开关只收紧 Agent 工具，不改变 Play API / `rpg_data` 的手工管理 CRUD。

`rpg_sessions.id` 是跨 workspace/story 全局唯一的稳定定位 ID，兼容 `rpg_core` 当前 `^[A-Za-z0-9_]+$` 校验。所有创建入口都由 `rpg_data` 生成 session ID，用户只允许指定 title；`rpg_session_profiles` 保存 title、description、玩家扮演角色 ID 和角色快照。Play API 是 catalog session 到 Agent 服务的边界层：会话内接口只收 `session_id`，内部解析出 workspace/story；Agent 服务运行态只接收全局 `session_id`。CLI / Telegram 启动时也先 ensure session：配置了 `session_id` 只校验并加载既有 session，未配置则创建系统生成 ID 的默认 session。

会话永久删除由 Agent service 统一协调。删除期间 `AgentManager` 阻止同 ID runtime 重建，取消活动和排队 turn、丢弃未提交 scratch，并关闭 mailbox、watcher 与向量 SQLite；随后删除 `rpg_sessions` 及其所有外键级联数据（包含冷备、状态表、裁定、记忆和配置覆盖），最后清理整个 runtime 目录。runtime 先重命名隔离，数据库失败时恢复；数据库提交后目录删除失败返回 `runtime_cleanup=pending`，隔离目录由未索引数据清理能力继续发现。Play API 只通过 AgentClient 转发删除，不直接操作 AgentManager。

玩家扮演角色是 session 级运行语义。绑定状态对外只暴露 `bound | invalid`：缺失绑定、角色不存在、未挂载到当前 story、snapshot 损坏或 snapshot 的 mount/story 与当前挂载不一致，都统一视为 `invalid`。WebUI 不在进入 SessionRoom 前拦截，而是在 SessionRoom 内打开不可取消的角色选择弹窗；没有可选角色时显示阻塞空态。CLI / Telegram / Agent API 允许创建空 session，但普通消息在绑定前只返回固定编号角色列表，不调用 LLM、不写 user history。

绑定和切换必须统一经 Agent 命令链路：`/role_bind <角色序号> [开局序号]`。WebUI 的 `PATCH /play-api/v1/sessions/{session_id}/player-character` 只负责把角色 ID 与可选稳定 Opening ID 转发到 Agent service，由 Agent service 映射角色序号并通过内部稳定 ID 参数执行命令；不要在 Play API 或 DataManager 中直接写 `rpg_session_profiles`。空 SessionRoom 使用“角色 → 开局”两步向导，只有 2–3 条 Opening 才显示第二步，最终一次提交角色与 Opening；0/1 条直接使用缺省项。首次成功绑定且 main history 为空时，`SessionRoleService` 追加选中 Opening 的渲染正文到 main history 和 backup history；普通历史删除/截断或后续切换不重复追加。`/clear` 沿用 Session 保存的稳定 Opening ID 并读取 Story 最新正文，已删除则回退第一条。Agent 的 send/send_stream 在命令分发之后、进入 LLM 前强校验玩家角色，只有 `bound` 才进入正常生成。

玩家角色必须在 Context 门禁前进入不可变 turn snapshot，并由主 Agent、StatusSubAgent 与 Context Preview 共用。fixed layer 的 `[player_character]` 标签块是玩家身份唯一真源：角色卡按当前 session 投影为 `PLAYER_CHARACTER` 或 `NPC`，Story Prompt、开场消息、历史、摘要、记忆或旧 metadata 与其冲突时均以绑定快照为准。玩家/NPC 标记不得写回 workspace 角色 metadata；角色切换后刷新 MemorySubAgent 等缓存上下文，但不重写已有历史。

### ChannelAdapter 基类（`channels/base.py`）

多渠道抽象基类，所有渠道（CLI / Telegram / Future）遵循同一接口：

| 方法 | 职责 |
|---|---|
| `start()` | 启动长连接 |
| `stop()` | 优雅关闭 |
| `send_text()` | 发送完整文本 |
| `send_delta()` | 可选流式增量 |
| `_handle_message()` | 统一消息管线（解析全局 session_id → AgentClient send/stream → 发送回复） |

命令分发统一由 Agent turn 的 `TurnPreprocessor` 在 snapshot/transaction 前处理，
不放在渠道层，确保所有渠道行为一致；同步和流式入口共用同一 preprocessor 与 orchestrator。

Telegram 例外：入口卡、角色按钮、`/sessions`、无参数 `/session_switch` 和会话菜单 callback 属于
渠道交互状态；callback 只携带 `TelegramActionRegistry` 生成的短 token，并在执行前校验 TTL、chat
与当前 session。`/session_create <title>` 在 Telegram 渠道内直接创建系统生成 ID 的 session；无标题
命令及“新建并进入”按钮使用 `TelegramSessionFlow` 的短期 pending 状态收集标题。创建成功后必须经
现有 `/session_switch <id>` 命令切换，确认 active session 后才 pin 当前 chat。

### Telegram 渠道当前能力

Telegram 是轻量入口、推送通知、快速回复和兜底交互；新增沉浸式体验优先沉淀到 Play WebUI。

| 能力 | 当前实现 |
|---|---|
| 启动方式 | `uv run python -m run_telegram`（通过 `agent_client` 访问 Agent 服务） |
| 长轮询 | `python-telegram-bot` `Application` + `updater.start_polling()` |
| 流式输出 | `TelegramTurnFlow` 通过 Application 托管任务发送占位、增量编辑和最终分块，支持间隔和最小字符数节流 |
| 非流式输出 | 同样通过托管任务发送占位和完整回复 |
| 渲染 | Telegram 展示层投影 `<rp-narration>` / `<rp-character>`，再转 Markdown HTML；原始 assistant content 不变 |
| 命令 | 轻量 Bot 菜单、本地动态 `/help`、后端斜杠命令和 Telegram 命令规范化 |
| 入口 | `/start` 展示故事、会话短 ID、玩家角色及角色/会话/开始游玩按钮；invalid 角色先进入按钮选择 |
| 会话 | 每个 bot 启动时 ensure 默认 catalog session；会话菜单显示 title + 短 ID，支持按钮切换 |
| 创建 | `/session_create <title>` 或“新建并进入”标题流程创建 session，成功执行 `/session_switch` 后固定切换 |
| 二段状态 | `TelegramSessionFlow` 用进程内 pending 状态收集新会话标题，支持 `/cancel` 和超时 |
| 并发 | 同一 chat 或同一 session 只允许一个 Telegram 生成；新输入立即拒绝，不进入 AgentMailbox 排队 |
| 停止 | streaming bot 提供 `/stop` 和“停止生成”按钮，按 active session/request ID 调用 Agent service `/chat/stop`，仅 `cancelled` 结束本地任务 |
| 网络参数 | `proxy`、请求超时、流式编辑节流参数来自 `channels/settings.yaml` 的 bot 配置 |

后续涉及 Telegram 的修改应优先补 `channels/tests/test_telegram.py`，尤其是：
会话菜单、命令规范化、stream 编辑节流、请求失败/超时、Markdown 渲染、长文本分块。

### Agent 组合式门面与消息队列

`RPGGameAgent` 只负责组件组装、幂等 `initialize()` 和公开 API 委托。队列状态全部由 `AgentMailbox` 独占：

```
send(A)        → QueueItem(TurnRequest A) → [consumer] → TurnPreprocessor → TurnOrchestrator
send(B)        → QueueItem(TurnRequest B) → [queue]    → ...等待...
send_stream(C) → QueueItem(TurnRequest C) → [queue]    → ...等待...
/compact       → QueueItem(command)       → [queue]    → CommandDispatcher
```

工作类型常量为 `QueueKind.SEND` / `SEND_STREAM` / `COMMAND` / `TRUNCATE_HISTORY`。普通正文工作项只以规范化 `TurnRequest` 为输入真源，request ID 从该对象读取；命令使用独立 command payload。

```text
RPGGameAgent（composition root + public facade）
├── AgentMailbox              QueueItem、consumer、stream task、取消与错误事件
├── AgentSessionService       角色、history、truncate/delete/reset、reload/switch
├── AgentRuntimeLifecycle     初始化、AgentContextResources、SubAgents、compressor、watcher
├── MainModelRuntime          MainLLMSelection、provider cache、model
├── AgentContextService       fixed layer、Context 构建/预览、窗口门禁
├── AgentToolService          base/turn-local tools、主 schema 过滤
└── AgentTurnService          TurnPreprocessor + TurnOrchestrator 的协议适配
```

`AgentContextResources` 是不可变的 session-scoped 引用集合，包含 builder、角色、世界书、状态、scene 与 memory manager。初始化、reload 或 switch 只能整体构建/替换该集合，再由 `AgentRuntimeLifecycle` 按顺序重绑 SubAgent context/tool providers、memory stores、compressor、RP registry 与 base tools；不要恢复 `_rpg_ctx` 字典或在 Agent 上散落 manager/store 字段。

### Agent Turn 分层

`AgentTurnService` 处理命令/角色旁路和公开协议适配，`rpg_core/agent/turn/` 负责同步/流式共享业务模板：

```text
TurnRequest                            调用方原始、不可变输入
  → TurnPreprocessor
  → TurnPlanResolver
      → TurnSnapshotResolver
      → TurnExecutionPlan             mode/style + 主 LLM/RP Module 快照
  → TurnOrchestrator                  同步/流式共享模板
      → TurnRuntimeFactory
          → Context window gate       门禁失败时尚未创建 transaction
          → TurnRuntime               本轮资源 owner
          → AgentTurnTransaction
          → TurnScratch               message/status/scene COW
          → RPModuleTurnRuntime
          → StatusPreflightHook
      → TurnPreparation
          → MemoryRecallHook
          → AgentContextService + AgentToolService
      → sync/stream runner
      → commit → AgentReply/SSE DONE → PostCommitHooks
```

- `TurnRequest` 不得持有 scratch、transaction、manager、provider 或解析后的配置。
- `TurnExecutionSnapshot` / `TurnExecutionPlan` 在 Context 门禁前形成，生成期间不可变；新增 turn 配置应先进入 snapshot，再由 policy/preparation 消费。
- `TurnRuntime` 只持有本轮可变资源并统一执行 commit/discard/close，不复制 `AgentTurnTransaction` 的持久化职责。
- `TurnPreparation` 直接依赖 Context/Tool service 与 `MemoryRecallHook`，是正式 turn 的 Context、turn-local tools 与 schemas 统一构建入口；context preview 复用 snapshot resolver 和共享 Context builder 的只读路径，但不创建 transaction。
- 同步和流式只允许 runner/输出适配不同；不得复制 preflight、Context 构建、工具装配、commit 或清理流程。
- turn 代码不得依赖 `RPGGameAgent`、`TurnHost` 或 `TurnPreparationHost`，也不得反向调用 facade 私有方法。所有依赖必须通过 plan resolver、runtime factory、service 和固定 hook 显式注入。

阶段 hook 不使用通用事件总线：顺序固定为 `StatusPreflightHook → PlotSchedulingPreflightHook → MemoryRecallHook → runner/commit → PostCommitHooks`。Status preflight 的未处理异常会终止并 discard；Plot 强制候选直接暂存，软判断失败记录 error 并继续主 turn；memory recall 失败只记录 warning；story-memory/summary 两个 post-commit hook 各自隔离失败，永不回滚 commit。不得增加动态优先级、运行时重排或第三方 hook 注册。

### Agent Turn Transaction

`send()` / `send_stream()` 的普通 RP turn 通过 `AgentTurnTransaction` 管理写入一致性。事务边界是内存 scratch 加最终短 commit 点，不跨 LLM 调用打开数据库事务。

- turn 开始后，user message、assistant reply 和 scene/status document 变更先写入 scratch。
- 创建 turn scratch 前先解析不可变 RP Module 快照，Narrative Outcome 权重随该快照固定；turn 开始后 `rp_story_outcome` 与 scratch 版 scene/status 工具一起绑定给 `StatusSubAgent`。代码固定编排为 Outcome 独立判定 → 状态表/字段路由 → scene 与每张命中表分别更新；Outcome 已暂存或判定失败时不进入状态路由与预写。
- 状态路由只能选择具有实际可用工具的 scene，以及普通表中的 `realtime` / 已明确命中 `updateRule` 的 `event_driven` 字段；每个更新调用只获得对应 scene 或单张表的被选字段，并由工具层再次校验 table ID、key allowlist 和频率。隔离 Update 使用稳定 system contract，明确只能调用本请求实际提供的工具；user 内容按 `Recent Conversation → User Action → Selected State Target` 排列，每次仍只下发当前目标 schema。默认结构权限关闭时只允许更新已有 value。快速更新按 scene/单张普通表目标各自创建内存 checkpoint；provider、工具或范围校验失败只恢复当前目标，保留此前成功目标并继续后续目标和主 Agent。checkpoint 创建或恢复失败才终止并 discard 整个 turn；不新增持久化 journal 或可靠重试队列。
- 主 Agent context builder 读取按 `summary_processed` 投影后的历史、当前 scratch user message、scratch 后的状态，以及主调用前已暂存的 Narrative Outcome runtime section。预裁定成功后不再注入 Narrative Outcome fixed section，只用简短无序条目要求执行最终结果并明确列出本轮可用的 scene/status 工具，同时从主 Agent schema 和可执行 registry 移除 outcome 工具；漏判或预裁定失败时才保留原 fixed contract 和补判工具。主 Agent 每次 outcome 后都检查 scene/status，但只有实际、持久、确定的值变化才写，允许零状态工具。有变化时工具调用轮不得夹带 RP 正文，最终正文不得新增尚未同步的可追踪确定事实；状态同步无需询问玩家。
- 普通表统一使用 `status_table_set_values`，只能按当前 session 运行时表 ID 批量修改已有 key 的 value；no-op 不进入 scratch，普通表即使没有 scene 也可独立触发状态预更新。字段更新频率固定为 `realtime | event_driven | deferred | manual`，旧字段默认 `realtime`，scene 永远只能是 `realtime`；`deferred` 由回复交付后的慢状态归纳维护，`manual` 不允许 LLM 写入。
- LLM 完整成功后再提交 main history、backup history 和状态表；stream 模式 commit 成功后才发 DONE。
- WebUI 停止生成通过 `requestId` 走 Play API `/sessions/{session_id}/stop` 到 Agent service `/chat/stop`；取消成功的 stream turn 丢弃 scratch，不发 DONE，不提交消息、状态或 usage。
- 持久化 session 的 commit 使用 `rpg_data` database atomic；`history_enabled=False` 仅作为测试/内存模式，不承诺补偿回滚已写入的外部 status manager。
- summary compression 和 story memory extraction 是 commit 后副作用，失败只记录 warning，不回滚已提交 turn。
- 已提交 turn 的回复/SSE 完成先交付调用方，再由同一 session mailbox 执行到期的 deferred 字段归纳；归纳不延迟本轮回复展示，但在下一队列项前完成。默认间隔来自 `agent.status_sub_agent.deferred.default_interval_turns`，字段可用 `deferredIntervalTurns` 覆盖；值与逐字段进度原子提交，失败不推进进度。
- session 状态表并发暂采用 last-write-wins，不使用 `version`/CAS；提交发现 document 已偏离 scratch 基线时在 data 层记录 warning 后继续覆盖。

## 关键设计

### Dream 长期记忆

Dream 是独立于在线 turn pipeline 的手动 Session 级归纳系统。Persistent Memory 真源位于 SQLite：稳定 Memory UUID 指向不可变 revision，revision 保存类型、认知状态、显著度和主历史 Evidence；生命周期固定为 `active | retired | superseded`。每个 Session 最多 64 条 active，历史 revision 与非 active 记录不限。主 Context 只读取 Evidence 的 message ID/version/content hash 全部仍匹配当前主消息的 active revision；历史编辑或 truncate 后失效项立即停止注入，但不会在读路径修改账本。

Dream 只保留可跨 turn 复用的世界内持久事实，不归纳 OOC 内容、用户偏好、系统/Provider 配置或 scene 等易变当前状态。旧 `persistent_memory.json` 已退出读写路径：新运行不读取、不创建，也不自动删除工作区里已有的遗留文件。

运行维度相互独立：

- `shallow + incremental` 消费相对 manifest 新增或变化、且精确来源 Evidence 仍有效的 story memory 与 summary batch。
- `shallow + full` 重扫全部当前派生源；派生源局部缺失不得触发退休，只有明确矛盾可 revise/supersede。
- `deep + incremental` 对比当前主历史与上次 Deep manifest，只处理新增、修改、删除、相邻 turn 与 Evidence 受影响项；只能退休明确失效且重析后不成立的事实。
- `deep + full` 以当前主消息表完整有效分支全量 Map/Reduce，是唯一可因完整历史无证据而全局退休的模式。

Deep 只读取 IC/GM user/assistant 主消息，不读取冷备、system/tool/OOC，也不套用 `summary_processed` Context 过滤；story memory/summary 不参与 Deep 的事实提取，最终非 retire 项必须引用当前主消息 Evidence。Story memory extraction 必须持久化原始 message ID/turn/version/content hash；失效条目被排除，没有任何仍精确匹配的 Evidence 时才跳过该派生源，同一事实被重新抽取时以最新一批精确来源替换旧 manifest。新 summary batch 必须保存 `source_turn_start/end` 与 `source_message_ids`，并与当前仍标记为同一 `summary_batch_id` 的完整消息集合一致；旧文件只允许在当前 turn 范围仍被该 batch 完整覆盖时回填，两种来源都无法验证时跳过。Map 按 turn/字符预算分批，Map、分层 Reduce 和最终 Proposal 共用 `map_concurrency` 并发上限；模型不收敛时使用代码侧有界、高价值且保留类别多样性的选择，不把无界候选一次送入最终 proposal。发生实际候选截断时，Full Deep 必须禁用基于“候选缺席”的退休，避免把未进入最终有界集合但仍受完整历史支持的事实误判为缺失。

每次运行先写 `generating` proposal，再由进程内 async task 生成；同 Session 同时只允许一条 generating，不建持久 worker、不自动重试模型任务。服务启动把遗留 generating 标为 interrupted；ready/failed 状态落库允许有限重试，耗尽后必须尽力把该 proposal 转为 interrupted，且没有本地 task 的新建请求必须先协调同 Session 遗留 generating。WebUI 只手动刷新状态，“检查并重试”必须携带预期 generating proposal ID：真实本地 task 返回冲突，已终态则直接返回旧 proposal，只有该 ID 仍为 SQL orphan 时才按原 depth/scope 创建替代任务。用户可逐项选择、编辑 `text / memory_kind / epistemic_status / salience`；动作目标与 Evidence 不可编辑。Dream HTTP、轮询和 Apply 的同步 SQLite/文件工作统一交给单线程串行 repository worker，repository 必须在该 worker 内创建、使用并关闭，不得阻塞事件循环。Apply 只由 `rp_memory.dream.application` 编排：在 SQLite `IMMEDIATE` 事务中写入前完整重捕获 history/source/ledger/Story Memory，执行 typed mutation plan 后、提交前再次重捕获来源。第一次门禁失败只提交 stale；第二次确认失败必须回滚全部 ledger/checkpoint 写入，再用独立条件事务把仍为 ready 的 Proposal 标为 stale。成功时原子写 revision/evidence、生命周期、manifest、Story Memory checkpoint 与 applied 终态。任何快照变化都拒绝 Apply。

Persistent Memory 的 `(session_id, dedupe_key)` 跨 lifecycle 唯一性保持不变。ADD 命中同 key 的 retired 事实时必须复用稳定 Memory ID、追加新的不可变 revision/Evidence 并恢复 active；旧 revisions 继续保留。active 或 superseded key 仍视为冲突。手动 Restore 只恢复当前 revision Evidence 仍有效的 retired 记录，不承担新 Evidence 复活语义。

`/clear` 必须清除该 Session 的 Persistent Memory、revision/evidence、proposal 和 Dream state；Session 删除依靠外键完整级联。Dream Service 不可用时只影响 Play WebUI Dream 管理能力，不得影响聊天、Context、summary/story memory 或召回。

### 记忆 `meta` 字段

最终返回的记忆 `meta` 是由 `candidate.metadata`、检索分数和 rerank 调试信息合并而成。
`HybridRetriever` 负责把 `sqlvec / keyword / raw_md` 三路结果合并，`MemoryManager.hybrid_search()`
会再把候选转成对外返回的 `metadata`。

召回主流程：

- sqlvec 可用时执行向量召回。
- keyword 可用时执行 tokenizer 可插拔的 FTS 召回。
- `raw_md_mode=always` 时 raw md 每次作为主召回一路参与 merge / scoring / rerank。
- `raw_md_mode=fallback_only` 时，主候选数低于阈值或主检索失败才执行 raw md。`raw_md_min_results > 0` 使用显式阈值；否则有 reranker 时使用 `rerank_candidate_k`，无 reranker 时使用 `top_k`。
- rerank 取最多 `rerank_candidate_k` 个 hybrid 候选，最终仍只返回 `top_k`。

| 字段 | 来源 | 作用 |
|---|---|---|
| `type` | `summary/overall.md` front matter，来自 `BatchSummaryStore.save_overall()` | 摘要类型，通常是 `overall` |
| `last_batch_id` | `summary/overall.md` front matter | overall 记录追踪到的最新批次 |
| `memory_id` | SQL chunk 的 `chunks.id` 或 raw md 的稳定哈希 ID | 召回项唯一标识，也是分数合并键 |
| `source` | 原始文件元信息或 raw md 目录名 | 例如 `summaries` |
| `file` | 原始文件路径 | 定位到源文件 |
| `chunk_idx` | 分块索引 | 同一文件内的 chunk 序号 |
| `created_at` | SQL chunk 的写入时间；raw md 的文件 mtime | 用于 `recency_score` |
| `vector_score` | `SqlVecRetriever` / `VectorIndex` | 向量相似度分数 |
| `keyword_score` | `KeywordRetriever` / FTS | keyword / BM25 分数 |
| `raw_md_score` | `RawMarkdownGrepSearch` | raw markdown 原文 query / term 覆盖分 |
| `exact_score` | `exact_and_fuzzy_scores()` | query 完全命中时为 1.0 |
| `fuzzy_score` | `exact_and_fuzzy_scores()` | query 模糊匹配分数 |
| `expanded_score` | `RawMarkdownGrepSearch` / `HybridRetriever._finalize()` | query planner 扩展查询或扩展分词命中分 |
| `recency_score` | `HybridRetriever._finalize()` | 时间越近分数越高 |
| `granularity_score` | `HybridRetriever._finalize()` | 记忆粒度优先级分，front matter 中的 `batch_id`、`type: overall` 等会参与解析 |
| `hybrid_score` | `apply_hybrid_scores()` | 向量、keyword、raw md、exact、expanded、recency、granularity 的融合分 |
| `rerank_score` | `PointwiseMemoryReranker` | 最终重排分 |
| `debug` | 各检索 / 重排阶段逐步写入 | 调试信息，通常包含 `*_norm`、`*_reason`、`raw_md_*` |

常见 `debug` 键：

| debug 键 | 来源 | 说明 |
|---|---|---|
| `keyword_bm25` | `KeywordRetriever` | keyword FTS 的原始 BM25 分数 |
| `keyword_relevance` | `KeywordRetriever` | BM25 转换后的有界 keyword 相关性分 |
| `keyword_tokenizer` | `TextIndex` | 当前 keyword FTS 使用的 tokenizer：`jieba` / `bigram` / `both` |
| `keyword_query_hits` | `KeywordRetriever` | 多 query 命中明细，包含 query、来源权重、原始分和加权分 |
| `keyword_queries` | `KeywordRetriever` | 参与 keyword 搜索的 query 列表 |
| `raw_md_source` | `RawMarkdownGrepSearch` | raw markdown 源文件路径 |
| `raw_md_terms` | `RawMarkdownGrepSearch` | raw markdown 计算命中的 term |
| `raw_md_expanded_queries` | `RawMarkdownGrepSearch` | raw markdown 使用的扩展查询 |
| `raw_md_expanded_terms` | `RawMarkdownGrepSearch` | 扩展查询再次分词得到的 raw md term |
| `raw_md_match_score` | `RawMarkdownGrepSearch` | raw md 阶段 exact、raw_md、expanded 三者的最大命中分 |
| `vector_score_norm` | `apply_hybrid_scores()` | 向量分归一化结果 |
| `keyword_score_norm` | `apply_hybrid_scores()` | keyword 分归一化结果 |
| `recency_score_norm` | `apply_hybrid_scores()` | 时间分归一化结果 |
| `exact_or_fuzzy_score` | `apply_hybrid_scores()` | exact / fuzzy 的合并分 |
| `expanded_score` | `apply_hybrid_scores()` | 参与 hybrid scoring 的扩展查询命中分 |
| `granularity_score` | `apply_hybrid_scores()` | 参与 hybrid scoring 的记忆粒度分 |
| `memory_granularity` | `HybridRetriever._finalize()` | 解析出的记忆粒度，如 `batch`、`event`、`global`、`unknown` |
| `llama_score_norm` | `PointwiseMemoryReranker` | llama provider rerank 归一化分 |
| `llama_reason` | `PointwiseMemoryReranker` | llama provider rerank 给出的原因 |
| `openai_score_norm` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 归一化分 |
| `openai_reason` | `PointwiseMemoryReranker` | OpenAI-compatible provider rerank 给出的原因 |

### 结构化 RPG 上下文（`context/`）

上下文主流程保持结构化数据，直到发送给 LLM 前才统一渲染。核心分工：

| 模块 | 职责 |
|---|---|
| `fixed_layer/` | `FixedLayerContributor` / `FixedLayerAssembler` 与 `FixedLayerSection`，统一装配稳定固定层 |
| `builder.py` | 消费预组装 fixed layer、已投影历史和当前 user message，并读取摘要、记忆、状态表、用户扩展块，构建结构化 `RPGContext` |
| `models.py` | `Message` / `Role`、上下文层数据结构与 `RPGContext` 薄委托方法的唯一实现 |
| `renderer.py` | LLM 请求边界渲染，将结构化层转成 OpenAI-compatible messages |
| `inspector.py` | `/context`、日志和调试用 markdown / token 诊断 |
| `usage.py` | context/token 用量快照、provider usage 聚合与 wire payload 归一化 |
| `rendering.py` | 共享 Jinja2 环境和模板渲染工具 |

`RPGContext` 的结构化概念顺序如下：

| 层 | role | 内容 | 变更频率 |
|---|---|---|---|
| [0] Fixed | system | 系统提示 + 已启用 RP Module 静态契约 + Story Prompt + 世界书 + 当前玩家角色绑定 + 已标注角色卡 | ★ 几乎不变 |
| [1] Persistent Memory | system | 常驻记忆 | ★ 离线更新 |
| [2] Summary | system | 历史摘要（条件触发） | ★☆ 少量 |
| [3..N] Hot History | mixed | 最近 N 轮对话 | ★★☆ 每轮追加 |
| [N+1] Story Memory | system | 剧情细节 | ★★☆ 累积 |
| [N+2] Status Tables | system | 普通状态表，不包含 `status_kind="scene"` 的当前场景 | ★★★★ 当前状态 |
| [N+3] Recalled Memory | system | 动态召回；冲突时服从当前状态和更新事实 | ★★★ 动态注入 |
| [N+4] RP Modules | system | RP 模块动态运行态；Narrative Outcome 注入预裁定结果，Plot Scheduler 注入已触发的本轮剧情指令 | ★★★★ 动态 |
| [N+5] User Message | user | `[scene]` + 用户输入 + 前后缀 | 总是新的 |

`ContextRenderer` 必须保持多消息结构，provider wire 顺序固定为 Fixed → Persistent Memory → Summary → Hot History（所有 role 原位保留）→ Story Memory → Status Tables → Recalled Memory → RP Modules → User Message；各结构化 system 层分别发送，不得为特定模型全局合并。动态 system 层将当前状态放在按 turn 变化的 Recall 前；Recall 块明确自身只是可能过时的历史参考，与 scene、普通状态表、玩家角色绑定或更新事实冲突时必须服从当前/更新状态。“只能有一个首位 system”属于具体 API/chat template 的部署约束，不是通用准则；原生 llama.cpp/Qwen 应通过 Jinja chat template 适配多段、交错 system。prefix cache 匹配实际序列化/tokenized 请求的共同前缀，不以结构化层、消息边界或整条消息 hash 为独立缓存单元；完整 hash 不同仍可能命中较早的部分 token 前缀，实际命中以 provider usage 为准。

开启 `verbose_logging` 时，`TurnPreparation` 在最终主 messages 和 tool schemas 完成后、首次主 LLM 调用前只输出一次无正文的 `contextHash` / `systemHash` / `toolsHash`、逐消息 `index/role/hash/chars`、role 计数和工具名，后续工具 round 不重复。StatusSubAgent 与 MemorySubAgent 的每个 provider 调用使用相同指纹口径按独立 source 输出上述字段，并记录 provider cache hit/miss/rate；不同阶段/pipeline 使用不同 system/schema，仍应视为不同缓存族。

主 Agent Context 与历史展示分离。`SessionManager.context_history()` 是主 Agent 的历史投影入口：
持久化 session 每次构建 Context 都重新读取 `rpg_session_messages.summary_processed`，仅把
`summary_processed=false` 的消息交给 builder；`summary_processed=true` 的消息逐条排除。
该投影不校验 `summary_batch_id`、summary batch 文件、`overall.md` 或 turn 完整性，也不影响
Play/Agent history 接口返回完整未删除历史。`send()`、`send_stream()`、`context-preview` 和
`/context` 都使用同一个主 Context 构建入口；`StatusSubAgent`、`MemorySubAgent` 等独立处理链路
继续使用各自原有历史输入，不套用这层过滤。

Summary Layer 只把“本次投影过滤过至少一条消息”作为尝试加载 `overall.md` 的条件。`overall.md`
缺失或为空时摘要层为空，但已标记 processed 的消息仍不进入主 Agent Context。`context-preview`
的 `messages`、`totals.tokenCount` 和 `usageEstimate.usedTokens` 以最终渲染出的主 Agent messages
为准，不用完整历史估算。

`当前场景` 是 `status_kind="scene"` 的特殊状态表，不走普通 `STATUS_TABLES` 层。`SceneTracker.get_context()`
会将它作为 user prefix 注入最终用户消息：一方面提高模型对当前时空、地点、场景属性的注意力，
另一方面让场景状态随 user message 进入历史，便于后续摘要和记忆按时间顺序归纳。
`rpg_data` 状态表 service 用 `status_kind="scene"` 表达这一类特殊状态，且仍由 story
挂载关系决定 session 是否可见；未挂载 scene 时，Agent 不注入 `[scene]`，也不注册 scene 工具。
当 Plot Scheduler 启用时，`SceneTracker` 每 turn 必须从 scratch 状态表重新解析“时间”，且只接受
`第 Y 年 M 月 D 日 H 时 [M 分]`。缺失、空值或非法格式使调度安全跳过，不得回退到默认时间或系统时钟；
虚拟时间 ordinal 固定按 12 月 × 31 日换算世界内分钟。
默认配置 `agent.scene.allow_runtime_key_changes=false` 时，非空 scene 只注册已有 value 更新能力：
`scene_attr` 的 key schema 枚举当前已有字段，`scene_time` 仅在 `时间` 字段已存在时注册，
`scene_del_attr` 不注册；空 scene 没有任何 scene 工具，Route 也不能选择 scene。工具执行层会再次校验，
因此旧 schema 或手工构造的工具实例也不能越权创建/删除 key。显式开启该配置后才恢复原有结构编辑能力。

普通 `STATUS_TABLES` 层只展示 session 运行时表 ID、表名、作为“用途与更新规则”的
`description`、完整 KV、更新频率和事件规则，不展示模板来源或通用作用范围。绑定角色的普通表进入独立的
“角色状态表”段落并按 `characterName` 分组；当前角色绑定不触发额外工具或业务行为。
角色绑定入库必须校验角色 name 非空；旧 session 缺 name 时优先通过 `characterMountId`
反查，必要时由状态表 `mountId` 回退到 `story_character_mount_id`，成功后回填。仍无法解析
的表记录 warning 并从 LLM 上下文排除，不得合并到“未知角色”分组。

上下文基于 Jinja2 模板（`rpg_core/jinja/`），通过 `RPGContext.to_message_objects()`
展平为 OpenAI-compatible 消息列表。不要在 builder 或 dataclass 中提前拼接最终 prompt，
也不要把 markdown 诊断输出放回主业务数据模型。

SessionRoom 的 context 用量状态位不走独立 usage 查询接口：`context-preview.v1` 只提供估算摘要，
准确 usage 只从正常 `/turn` response 或 `/stream` 的 `turn_completed.payload.usage` 读取。
usage 暂不持久化，不写 message metadata；后端只提供 token、context window、cache token、model、source
等元数据，比例、阈值、K/M 单位和 cache 命中率由 Play WebUI 组装展示。context window 通过
`llm_service` 类型化配置解析，OpenAI-compatible provider 使用显式 `openai.context_window`，
llama provider 使用 `llama.n_ctx`。

圆环始终只呈现不含当前待发送 input 的 `context-preview`，provider usage 不得覆盖圆环，只进入对应
assistant 气泡和展开详情。WebUI 在普通发送、retry/edit 前重新请求 preview，并按
`session.contextUsage.inputBlockThresholdRatio` 在达到阈值时阻止正文；斜杠命令始终放行。
Core 使用相同渲染 messages/token counter，按 `agent.context_window_reject_threshold_ratio` 在 transaction、
StatusSubAgent 和 LLM 之前兜底拒绝，业务错误码为 `MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED`。
两侧合法范围均为 `(0, 1]`、默认均为 `0.9`；WebUI 非法值回退 `0.9`，Core 非法值启动失败。
窗口未知时不做误判；门禁只引导手动 `/compact` 或切换更大窗口，不自动压缩。

RP Modules 不是通用 skill 体系。骰子、战斗、物品、关系等能力必须定义为围绕 RP 语义的模块：
模块可以注册工具、暴露运行态 section、读写受控状态，但固定 instruction 层和不可变模块描述应保持稳定，
避免频繁变化破坏 prefix cache。当前实现位于 `rpg_core/rp_modules/`：`RPModuleRegistry` 只持有内置
Python 定义与配置校验；`RPModuleSelectionSnapshot` 是一次 preview/turn 的不可变 Story/Session 选择，
`RPModuleTurnRuntime` 才持有本轮模块实例、tools 和 sections。Story 挂载是能力上限，Session 只能覆盖
已挂载模块；新 Story 默认挂载 catalog 中当前全部默认模块。不要把动态选择或 active scratch 写回共享 Registry。

RP Modules 使用常规上下文分层/分配策略：

- 静态契约进入 fixed layer：例如 narrative_outcome 的“何时裁定、必须调用工具、不得替玩家选择行动”。
- `text_output_format` 作为 fixed layer 输出格式约束默认启用，用 `<rp-narration>` 和 `<rp-character name="...">` 约束 assistant 正文中的旁白/角色分离，不进入 `RPModuleRegistry`。
- 动态运行态只在模块确有临时状态时进入 `RP_MODULES` system layer；Narrative Outcome 平时依赖 fixed contract，检测到明确随机意图时注入本轮强制工具指令；StatusSubAgent 已预裁定时省略该 fixed section，仅以简短无序条目注入最终结果和明确的 scene/status 工具边界。Plot Scheduler 只在本 turn 实际触发候选时注入最多两条指令，不把定义或判断过程写入正文。
- `verbose_logging=true` 时，主 Agent 记录 RP runtime section 总数，并在 Context Builder 后按结构化分层输出完整当前 Context；会话历史只记录 logical turn 数，不输出历史正文。空 runtime 记录 `count=0`，不输出 sample、权重等内部随机细节。
- RP 工具只注册到本轮 `ToolRegistry`；当前主 LLM/StatusSubAgent 的 RP schema 最多只有 `rp_story_outcome`。模块命令按最新非 turn 快照动态解析。
- RP Modules 不进入 user prefix，不写 history；`[scene]` 仍是唯一高优先级 user prefix 运行态。

Assistant 回复的 `content` 是唯一真源：带标签全文原样写入主历史、备份历史、Agent service stream 和 Play SSE。不要把旁白/角色分段写入 message metadata，也不要恢复 `metadata.messageDisplay` 空壳。Play WebUI 可以在展示层容错解析这些标签；解析失败、半截标签或非标准 SSE 坏帧必须原文展示，不丢内容。

Narrative Outcome 是当前剧情分支随机机制：

- 主 LLM 的 RP schema 只暴露 `rp_story_outcome(reason, actor?)`；不得重新暴露 `rp_dice_roll`、`rp_dice_check_dc`、表达式、DC、权重或随机数。
- `auto_adjudication_enabled=true` 时，主 Agent 必须结合用户完整语义、当前场景和状态判断外部实质变数。触发不依赖关键词；未知信息、能力、阻力、风险、时机、环境或 NPC/世界反应导致多个合理剧情分支时，在叙事结果前调用工具。玩家内心选择、已确定结果和无实质代价的小事不裁定。
- 结果固定为 `critical_success / success / success_with_cost / setback / critical_failure` 五档，系统默认比例 `5/25/40/25/5`。`reason` 是不可缩小的整体目标边界；`success_with_cost` 必须完整达成目标，代价不得抵消成功。重大失败不得自动死亡、硬停局或永久剥夺玩家角色主权。
- 每 turn 最多一条裁定；重复调用复用 scratch 结果。有效权重在 turn 开始前形成模块快照，优先级 `config < story < session`；各层可以不覆盖 `weights`，但一旦提供就必须是总和严格等于 100 的完整五项原子组。
- `StatusSubAgent` 负责可选预裁定：需要 outcome 的同批状态预写全部延后，结果以 `outcomeCode / label / narrativeGuidance / reason / actor?` 在主 Agent 首次调用前进入 `RP_MODULES` runtime section。漏判或预裁定失败时主 Agent 保留明确写出 `rp_story_outcome` 的 fixed contract 与补判工具；已预裁定时不注入该 fixed section，outcome 工具也从主 Agent schema 和可执行 registry 同时移除。工具自身的幂等只用于预裁定边界内的重复保护。
- 裁定与消息、Plot decision、状态表在同一个短 SQLite transaction 中提交；transaction port 与 Outcome/Plot ledger adapter 由 Agent composition root 显式注入。`NarrativeOutcomeLedgerService` 校验 code/sample/权重来源并映射唯一 turn 冲突，`NarrativeOutcomeDataService` 只持久化调用方准备的 typed row。取消、provider 错误或 commit 失败不落库；truncate、clear、用户消息编辑和相关历史删除同步清理裁定，retry/edit 重新抽取。
- retry/edit/truncate 不回滚已经提交的状态表；状态分支回滚留作独立能力，不增加 `status_turn_journal` 或其它状态 journal。
- 持久化表是 `rpg_session_narrative_outcomes`，内部保存 sample 和有效权重快照；LLM、Play API outcome 与 WebUI 卡片不得展示 sample、区间或百分比。
- 配置统一走 `/rp-modules/catalog`、Story `/rp-modules/{module_name}` 和 Session `/rp-modules/{module_name}` 通用接口。PlayTurn 的 nullable `outcome` 用于刷新/分页恢复；流式卡按 turn 去重且不受 `showTools` 控制。
- canonical 系统配置位于 `rp_modules.modules.narrative_outcome`；`dice.allow_auto_checks` 已移除且旧 key 必须启动失败。
- 开发期 `0005` 已重写为 `0005_rp_modules.sql`，不兼容执行过旧 `0005_narrative_outcome.sql` 的数据库；此类本地数据应直接重建。

Plot Scheduler 是 Story 级剧情动态调度模块：

- Plot Scheduler 的业务 owner 是 `rpg_core/rp_modules/plot_scheduler`。定义管理的默认位置、移动/重排、重复/冷却、时间线和删除占用规则，以及 turn ledger 校验、派生复制与 `/clear` 保留策略都由 Core 的类型化 application service/policy 决定；`rpg_data.plot_scheduling` 提供定义、Session 覆盖和决策账本的类型化查询/写入、分页 read model、调用方指定的复制过滤与通用事务，不得恢复调度或继承策略。
- Story 可同时挂载多条线性大纲和多个事件池。大纲节点引用稳定 Story 事件并保存固定 `SceneTime`；事件池按 priority 仲裁，池内使用 `random | sequential`。每个 IC/GM turn 最多选一个到期大纲节点和一个池事件，OOC 完全旁路。
- `forced` 候选到时直接暂存为 triggered；`soft` 候选通过 `agent.plot_scheduler` 独立 biz key 调用 LLM。Judge 只读完整 fixed layer、当前 scratch scene/普通状态表、最近 N 个完整原始 IC/GM turn 和当前输入，不读 Summary、Story Memory、Persistent Memory 或 Recall。Judge `reason` 由 schema 与 parser 双重限长，避免无界元数据突破主 Context 门禁预留。
- 门禁在 scratch 创建前按当前 Story 最长两条 directive、事件/容器名称与有界判断元数据保守预留。调度实际发生在 Status preflight 之后、Memory recall 之前；因此读取本轮最新 scratch 状态，并让主 Agent 在记忆召回完成后看到已触发指令。
- 大纲节点不重复；池事件可配置基于世界内分钟的重复冷却。池 lane identity 固定为 `event_id`，事件移到其它池后仍沿用已触发、延期和冷却状态；`container_id` 只表示当时所属池。大纲 lane 与池 lane 独立，但同一事件不得在同 turn 重复注入。
- Session 只保存池事件/大纲节点禁用覆盖与决策账本。`deferred | error` 不中断主 turn，并跳过配置数量的完整 IC/GM turn 后重试。决策与消息、Narrative Outcome、scene/status 在同一短事务提交；`/clear` 清账本但保留覆盖，Session 派生只复制分支点前 triggered 和覆盖。
- Play WebUI 只在 `/plot-scheduling` 独立页管理定义、覆盖和运行态；运行态不轮询、不调用 Judge。决策历史按 `id DESC` + `beforeId` 分页，不能改为 `turn_id` 游标，否则同 turn 的 outline/pool 两条记录可能漏页。迁移只把模块加入 catalog，不追溯挂载旧 Story。

Dice 只保留低层随机与调试能力：

- `/roll`、`/check_dc` 和 `d20`、`2d6+3` 等表达式解析继续可用，但不参与主 LLM 的自然剧情裁定 schema 或 fixed prompt。
- `dice.default_dc` 只服务手动 `/check_dc`；`max_dice_count` / `max_die_sides` 是输入安全限制。
- 手动结果不写 Narrative Outcome 表，不实现 JSONL 审计，不修改状态表或 Scene Runtime。

### Agent 数据流

```
agent.send(user_input)
  → AgentMailbox 将 QueueItem(TurnRequest) 串行出队
  → TurnPreprocessor：CommandDispatcher + 玩家角色校验（旁路不入历史）
  → TurnPlanResolver：TurnExecutionSnapshot + MainLLMSelection + RPModuleSelectionSnapshot + PlotScheduleSnapshot
  → TurnRuntimeFactory 使用同一组不可变快照执行 Context 门禁（不计本次 input；为 Plot 动态指令预留；拒绝时不创建 scratch）
  → TurnRuntimeFactory 创建 AgentTurnTransaction / TurnScratch / RPModuleTurnRuntime
  → StatusPreflightHook 调用 StatusSubAgent.run_preflight() 执行固定编排
    → Outcome 阶段：需要裁定时只暂存 outcome，并停止后续状态阶段
    → Route 阶段：只选择相关 scene、表 ID 及 realtime/event_driven key
    → Update 阶段：scene 与每张命中表分别调用；目标失败只恢复该目标，其他确定性变化保留在 scratch
  → PlotSchedulingPreflightHook：按 scratch SceneTime 选择 outline/pool 候选；forced 直接暂存，soft 隔离调用 Judge
  → SceneTracker.get_context() → [scene] 嵌入 user message
  → MemoryRecallHook：失败 warning-and-continue
  → turn runtime 收集 runtime sections；已暂存 outcome 在主 Agent 首次调用前注入
  → TurnPreparation → AgentContextService + AgentToolService → messages/tools/schemas
  → sync/stream runner → run_chat_loop(provider, tool_registry, messages)
    → 主 Agent 在漏判时可补判 outcome；已预裁定时不再获得重复调用选项，真实持久变化先修正状态，再输出 RP 正文
    → LLM 也可调用其它 RP module tools / file tools
    → 每轮记录 TurnStats + CallRecord
  → TurnRuntime.commit() 短事务写入主/backup 消息、Narrative Outcome、Plot decisions 与状态表
  → 同步适配为 AgentReply；流式仅在 commit 成功后发送带 usage/turn_id 的 DONE
  → PostCommitHooks：story memory extraction / summary compression 逐项隔离
  → 回复已交付后，mailbox 在下一项前执行到期 deferred 字段归纳
```

### 子 Agent 系统（`agent/sub_agents/`）

`sub_agents/__init__.py` 保持跨包稳定导出；生产内部直接使用 canonical 领域模块。`memory/` 分离 Agent、结果模型、候选选择与解析，`status/` 分离 Agent、bootstrap、结果模型、稳定 prompts/schemas 与解析，避免把协议和常量重新堆回主类。

| 子 Agent | 职责 | 执行时机 |
|---|---|---|
| **StatusSubAgent** | 独立 Outcome 预判、状态目标路由、按 scene/单表预更新，以及 committed history 的 deferred 慢状态归纳 | 主 LLM 前执行快速阶段；回复交付后执行到期慢阶段 |
| **MemorySubAgent** | 记忆总结/召回/剧情持久化 | `process()` 由 CommandDispatcher 或自动触发 |

支持独立 LLM provider 配置，通过 `llm_service/llm.yaml` 的 `agent.status_sub_agent` / `agent.memory_sub_agent` biz key 选择 `shared`、`openai` 或 `llama`，通过 `SubAgentContext` 获取世界书、当前玩家角色强约束和带 PLAYER/NPC 标注的角色卡上下文。StatusSubAgent 使用本轮不可变角色快照；MemorySubAgent 在角色绑定或切换后刷新共享上下文。

### 斜杠命令系统（`agent/command/`）

| 命令 | 来源 | 功能 |
|---|---|---|
| `/clear` | 内置 | 保留 session 身份/配置与原生状态表结构，清空游玩数据、重建 Story 状态副本并重新发送开场 |
| `/reload` | 内置 | 重新加载 RPG 数据 |
| `/context` | 内置 | 查看上下文结构和 token 用量 |
| `/compact [N] [K]` | MemorySubAgent | 压缩最老的 N 轮对话为摘要 |
| `/sessions` | 内置 | 列出所有会话 |
| `/session_create [title]` | 内置 | 创建系统生成 ID 的新会话 |
| `/session_switch <id>` | 内置 | 切换到指定会话 |
| `/memory_reindex` | 内置 | 手动重建 memory 索引 |
| `/rp_modules` | RPModuleRegistry | 列出已启用 RP Modules |
| `/rp_module <name>` | RPModuleRegistry | 查看指定 RP Module 状态 |
| `/roll <expr> [reason]` | Dice RP Module | 手动掷骰 |
| `/check_dc <expr> dc=<n> [reason]` | Dice RP Module | 手动 DC 检定 |

命令统一由 agent 内部的 `CommandDispatcher` 处理，不经过 LLM，不入对话历史。
所有渠道（CLI / API / Telegram）共享同一逻辑。

### REST API

Play API 使用 `play_api/settings.yaml` 中的 `api_prefix`，默认 `/play-api/v1`。路由集中在
`play_api/routers/`，作为 Play WebUI 的唯一 Web 后端契约。

当前主要路由：

| 模块 | 路由文件 | 职责 |
|---|---|---|
| workspace | `play_api/routers/workspace.py` | 工作区列表 |
| sessions | `play_api/routers/sessions.py` | 会话列表、创建、读取、永久删除，以及 `history/history-page/scene/commands/turn/stream/stop` 子资源 |
| main-llm | `play_api/routers/main_llm.py` | 主 Agent 安全模型目录、story 默认和 session 覆盖 |
| characters | `play_api/routers/characters.py` | workspace 角色库、角色详情、story 挂载 |
| lorebook | `play_api/routers/lorebook.py` | workspace 世界书条目、story 挂载 |
| status-tables | `play_api/routers/status_tables.py` | 状态表模板、story 挂载、session 运行表 |
| dream | `play_api/routers/dream.py` | Session Dream proposal 的创建/读取/编辑/Apply/Reject，以及 Persistent Memory 列表与恢复代理 |
| events | `play_api/routers/events.py` | 内部终态事件接收与 WebUI 全局 SSE；不查询或修改业务任务 |
| media | `play_api/routers/media.py` | Session 图片任务、Gallery、背景与 workspace 媒体库代理 |
| tts | `play_api/routers/tts.py` | 已提交 assistant 消息的 TTS 任务、状态与 Range 音频代理 |
| ops | `play_api/routers/ops.py` | 未索引运行目录扫描、删除确认与运维清理 |
| scene / commands / chat | 对应 router 文件 | legacy placeholder，保留模块名但不作为主入口 |

- Play API 通过 `agent_service.client.AgentClient` 访问 Agent 服务，并通过 loop-owned `DreamClient` 访问 Dream 服务；不得在 Play API 进程直接运行 Dream 领域或写 Persistent Memory 账本。
- Play WebUI 会话内请求只传 `session_id`；Play API 负责从 catalog 解析 workspace/story。
- Agent service / AgentClient 不接受 Provider API key 参数或 header；provider/key 选择只由 LLM Service 配置控制。Agent → LLM Service 只使用独立的静态 Bearer 服务令牌。
- 主 Agent LLM 只允许 `agent.main.provider_option_keys` 白名单，解析优先级为 `config < story < session`；生成中切换固定当前 turn，从下一 turn 生效。
- `/sessions/{session_id}/context-preview` 可透传估算 `usageEstimate`；它不是 provider usage。
- `/sessions/{session_id}/history-page` 按显式 turn metadata 返回窗口页；分页只校验当前返回页，旧 `/history` 仍保留全量读取语义。
- `/sessions/{session_id}/turn` 在正常 turn 返回中携带本轮 `usage`；流式只在 `turn_completed.payload.usage` 携带，不额外发 usage 事件或请求。
- SSE 流式格式：`data: {json}\n\n`。`turn_completed.payload.text` 承载完整 assistant 原文，成功持久化的普通 turn 同时携带正整数 `committedTurnId`，供 WebUI 将请求期诊断绑定到正式历史 turn；旁白/角色分离由正文标签表达，不通过 `metadata.messageDisplay` 传输。
- SSE 业务错误使用独立 `errorCode`；`message` 保留底层错误文本，不把错误码拼进正文，也不把业务错误和 HTTP `statusCode` 混用。
- 后台 `/events/stream` 与单次 turn SSE 是两个独立协议；不得把 Dream/Derivation 通知混入正文 stream。
- `/sessions/{session_id}/stop` 只取消带 `requestId` 的活动或队列 stream turn，返回 `cancelled | not_running | stale`；前端只有收到 `cancelled` 才展示“已停止”。

### 会话持久化

- `rpg_session_messages` — 主消息表，`id` 映射为 `Message.uid`，支持替换、清空、截断，并承载 summary / 剧情记忆提取处理标记
- `rpg_session_backup_messages` — 冷备份消息表，只追加永不截断
- `rpg_session_story_memories` — 剧情记忆表，记录来源 message ID/turn/version/hash manifest、`turn_id` 和 `dream_processed`
- `rpg_session_persistent_memories` / `rpg_session_persistent_memory_revisions` / `rpg_session_persistent_memory_evidence` — Persistent Memory 身份、不可变 revision 与主历史 Evidence
- `rpg_session_dream_proposals` / `rpg_session_dream_proposal_items` / `rpg_session_dream_proposal_item_evidence` / `rpg_session_dream_states` — proposal-first 审核、候选 Evidence 与增量 manifests/state
- `rpg_summaries.json` / `summaries/` — 对话摘要文件
- `memory_vectors.db*` — memory SQLite / WAL / SHM 索引文件

会话层以 `SessionManager` 作为稳定公开门面：`session/history.py` 负责有序消息、turn 分配、主表/冷备共同写入，以及历史修改对 Outcome/Plot ledger 的联动；`session/progress.py` 负责 summary/story-memory 候选分组、保留窗口和消息级处理进度；`session/grouping.py` 提供纯 turn 算法，`session/models.py` 保存快照和共享运行态。它们只依赖自身声明的窄 Data Port，由 Agent composition root 注入 `SessionDataService`，不再回查 Gateway。`MessageDataService` 仅保留 CRUD、turn window/分页、processed flag 聚合和调用方指定的批量标记，不决定 Context 投影、候选范围或编辑重置。持久化消息必须有正数 `turn_id` 和 `seq_in_turn`：主消息表约束同一 session 内 `(turn_id, seq_in_turn)` 唯一，冷备份表保持 append-only 但同样要求正数 turn metadata。非法 turn metadata 在写入或加载边界失败，不再为 summary、剧情记忆或 history pagination 做 legacy 降级分组。summary 和故事记忆续提进度按主消息表行标记持久化，进程重启后从 rpg_data 继续。历史删除、清空、编辑回滚和 turn truncate 只直接修改主历史，不清理摘要文件、不重置其它消息标记，也不自动重新归纳；主 Agent Context 下次构建时只按剩余行各自的 `summary_processed` 值重新投影。

Agent runtime 会话消息、剧情记忆和 Dream Persistent Memory 账本均由 `rpg_data` 管理；只有摘要和在线 memory 索引文件集中在
`CatalogService.get_session_runtime_dir(session_id)` 返回的 `{workspace_root}/stories/{story_id}/{session_id}/` 下。旧 `persistent_memory.json` 不再读取或创建，升级时也不会自动删除已有遗留文件。
`rpg_data` 管理的状态表 session 副本位于 SQLite `rpg_session_status_tables.document_json`，不再依赖该目录下的 `status/` CSV 或 workspace-relative 状态表路径。

`session_id` 只能使用英文字母、数字和下划线，规则为 `^[A-Za-z0-9_]+$`。所有创建入口都由 `rpg_data` 生成 ID；不要恢复 `cli_direct`、`telegram_<chat_id>` 这类渠道自造默认 ID，也不要允许用户输入新 session ID。

### Manager 模式

仅 summary batch/overall 仍是文件型数据域，并在适用处遵循：

1. **Loader** — 纯文件 I/O
2. **Manager** — 继承 `BaseManager`，持有 `self.data` 缓存
3. **BaseManager** — 向 `FileWatcher` 注册数据目录
4. **FileWatcher** — watchdog Observer，500ms 防抖

Story memory 已由 `rpg_session_story_memories` 持久化，Persistent Memory 则由 Dream SQL 账本持久化；两者都不属于上述文件 Manager 模式。Persistent Memory 的在线 store 不维护 JSON 文件或 watcher：每个 turn plan 和 Context Preview 前通过 `asyncio.to_thread()` 读取 `rpg_data` 的有效投影并返回不可变快照；turn 必须把快照放入 `TurnExecutionPlan`，门禁与实际 Context 显式共用，Preview 捕获自己的快照，读取失败时使用上一份只读快照。

其它 SQL 真源同样不走文件 Manager 模式：`rpg_core.character.CharacterManager`、
`rpg_core.lorebook.LorebookManager` 和 `rpg_core.status.StatusManager` 只保存
`session_id` 与数据访问引用，通过 `rpg_data` service 实时读取当前 session 绑定 story 的挂载数据，
不读取旧 JSON/目录结构，也不注册 `FileWatcher`。是否进入上下文由 story 挂载关系决定。

`rpg_data.services.status.StatusDataService` 是状态表的公开类型化持久化入口：SQL row 内的
`document_json` 是正文真源；service 不通过目录扫描发现状态表。它负责模板、Story 挂载、Session
document、角色关联 read model、deferred progress、last-write-wins 诊断与调用方指定的原子 document
batch，不决定 Scene、Context 或运行时写入策略。`StatusTableAdministrationService` 负责模板/挂载/Session 表管理规则，
`SceneStatusService` 负责 Scene 字段约束与 active Scene，`StatusContextService` 负责角色名修复和 Context
可见性，`StatusManager` 负责 Agent 运行时、deferred 与 bootstrap 写入资格。composition root 从
`get_data_service_gateway().status` 取得 Data Service 后显式注入，不新增 per-service 全局 getter，也不让
业务服务持有整个 Gateway。通用存储写操作仍支持 header 名称、行匹配和 key/value selector；LLM 的
普通表工具只能更新已有 key 的 value，不能增删改 key。key/value 写入以 `StatusTableDocument` 的逻辑
key/value 为准，不依赖 UI 列标题。
每个 `StatusTableRow` 可配置 `updateFrequency`、`updateRule`、`deferredIntervalTurns`；
`event_driven` 必须提供非空 `updateRule`，只有 `deferred` 可设置正整数间隔，旧 document 缺字段时按
`realtime` 读取。deferred 进度保存在 `rpg_session_status_deferred_progress`；历史 truncate 只收缩进度边界、不回滚已经提交的状态值。`/clear` 删除全部进度与旧 `template_copy` 并按当前 Story 挂载重建；`session_native` 表保留 ID 和完整结构，但所有 value 置空。同名原生表与当前模板冲突时 reset 原子失败。
gateway/bootstrap 只 materialize workspace/story/session 运行目录并初始化缺失的 session
状态表副本，不负责发现或创建业务索引。默认不清理不在 SQL 索引中的 workspace/story/session 目录；
开启开关是 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true`。

### Agent 类型边界

生产代码直接使用下列 canonical 类型模块。架构迁移产生的旧模块不提供兼容重导出；移动职责时必须同步迁移全部调用方并删除旧文件。

| 类型 | 用途 |
|---|---|
| `llm_client.types` | `LLMUsage` / `LLMResponse` / `ProviderChunk` |
| `agent/telemetry.py` | `CallRecord` / `TurnStats` |
| `agent/protocol.py` | `AgentStreamEvent` / `StreamEventKind` / cancel 结果 |
| `agent/mailbox/models.py` | `QueueItem` / `QueueKind` |
| `agent/turn/models.py` | `TurnRequest` / snapshot / plan / result |

### 前端注意事项

- Play WebUI 使用 Next.js App Router + React + TypeScript。
- Play WebUI 只访问 Play API，不直接访问 `data/`。
- Web 管理能力也沉淀在 Play WebUI 内，不跳转旧 Dashboard。
- 状态表管理页保持 `系统模板`、`故事状态模板`、`故事运行时` 三个视图：系统模板维护工作区级模板和系统挂载，故事状态模板维护当前 story 已挂载模板、故事内创建模板和角色绑定，故事运行时只维护当前 session 副本。
- 中文路径在前端 API 层用 `encodeURIComponent()` 编码。
- `session_id` 输入必须与后端一致，只允许字母、数字、下划线，不允许连字符。
- Play WebUI 通用配置入口是 `play_webui/play_webui.config.json`；SessionRoom 历史分页读取 `session.historyPagination`，正文门禁读取 `session.contextUsage.inputBlockThresholdRatio`。
- SessionRoom 历史使用 `/history-page` 滑动窗口：只渲染当前 active page，最多缓存相邻页；快速返回最新记录时优先切缓存，缺失时只请求最新页，不逐页请求中间历史。
- SessionRoom context 用量圆圈始终读取 `context-preview`，不被 response/SSE provider usage 覆盖；上一轮准确 usage 仅保存在页面内存，显示于回复气泡和圆圈详情。Story 详情页立即保存 story 默认 LLM，SessionRoom 圆环左侧立即保存 session 覆盖。
- Session 图像工作室通过 Play API 获取来源、简报、任务、Gallery 与背景；媒体请求失败只在工作室内显示，不能改变聊天 query/SSE 状态。背景图片只作为页面内 URL 投影，不进入消息或 localStorage。
- SessionRoom TTS 只读取已提交 assistant `message_id`；前端仅维护页面内单播放器与轮询状态，切换 session、翻页移除当前消息或组件卸载时必须停止并释放音频，不写 message metadata 或 localStorage。
- SessionRoom 设置菜单进入 `/session/{sessionId}/dream` 管理页；该页只经 Play API 操作 Dream。创建 proposal 后不得自动轮询，用户必须点击刷新读取进程内任务状态；对长时间未更新的 generating 只能通过携带当前 proposal ID 的条件恢复请求处理，不得在本地缓存过期时盲目新建。只有 `ready` proposal 可逐项选择、编辑允许字段并原子 Apply/Reject。手动刷新期间必须禁用编辑与 mutation；mutation 开始前取消同 Session 在途的 proposal/ledger 查询，成功后通过同一 QueryClient 刷新，旧 GET 不得覆盖已提交状态。Dream 请求失败只在该页展示，不得影响 SessionRoom 聊天 query、SSE 或 Context。
- `PlayEventBridge` 只允许在根 `Providers` 挂载一次；原始事件 store 只保存接收结果。`features/notifications` 单向读取该 store，并独立持有页面内的已读/清除状态；事件层不得反向依赖通知 UI，通知也不得触发 Dream/Derivation 查询、导航、任务 mutation 或持久化。

### 数据格式

- **Character/Lorebook**: SQLite（`rpg_data` workspace/story/session catalog + story 挂载表）
- **Status**: SQLite document 真源。SQL 保存 template/story mount/session copy/origin/source/status_kind/sort_order 与封装后的 `document_json`；对外通过 `StatusTableDocument` / `StatusTableRow` dataclass 访问
- **会话历史**: SQLite `rpg_session_messages` 主表 + `rpg_session_backup_messages` 冷备份表
- **摘要**: `summaries/` batch + overall 文件；已归纳消息在 `rpg_session_messages` 标记
- **剧情记忆**: SQLite `rpg_session_story_memories`；已提取消息在 `rpg_session_messages` 标记
- **Persistent Memory / Dream**: SQLite 类型化账本，包含 memory identity、不可变 revision、Evidence、proposal/items 和增量 state；旧 `persistent_memory.json` 不再读写但不会自动删除
- **媒体**: SQLite 中保存 Job/Asset/Blob/Gallery/Background 类型化关系；二进制位于 `{workspace_root}/assets/images/{sha256}.<ext>`
- **TTS**: SQLite 中保存 Job/Cache/AudioPart/Blob 类型化关系；MP3 位于 `{workspace_root}/assets/audio/{sha256}.mp3`

summary / 剧情记忆的续处理进度只信任主消息表上的消息级标记。summary 的 `keep_recent_rounds` 和 batch window 仍使用显式 turn/round 分组；持久化 turn metadata 异常应在写入或加载边界抛出，不在读路径恢复 user-anchor / pair 降级。

## 测试基线

当前自动化测试基线：

```bash
uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests rpg_media/tests media_service/tests rpg_tts/tests tts_service/tests dream_service/tests -q
```

这些测试 mock 外部 LLM、Telegram SDK 和网络调用，不需要真实 API key。若本地缺少 `pytest-asyncio`，`rpg_core/tests/agent/command/test_command.py` 中的 async 测试会提示需要安装异步 pytest 插件。

覆盖范围：

- `channels/tests/`：ChannelAdapter、CLI、Telegram 渠道和渠道侧会话流程。
- `rpg_core/tests/`：按源码领域镜像组织；`agent/` 下继续按 runtime/mailbox/command/sub_agents/turn/tools 分组，Context、Session、Summary、RP Modules、Scene、Status 与 utils 使用各自目录。
- `rp_memory/tests/`：memory 检索、索引、规划、rerank，以及 Dream 选源、分批、Map/Reduce 与 retirement policy。
- `dream_service/tests/`：Dream source adapter、进程内任务生命周期、HTTP/Client 契约与错误隔离。
- `rpg_data/tests/`：catalog、消息、状态、Media/TTS 持久化和 Dream proposal/ledger/revision/Evidence 的事务语义。
- `llm_service/tests/`：LLM HTTP/SSE 客户端契约、鉴权、provider 配置、manager 路由与 llama 本地 runtime。
- `play_api/tests/`：Play API workspace/session/scene/turn/stream、Dream service 代理、characters、lorebook、status-tables 和 ops 等契约。
- `rpg_media/tests/` / `media_service/tests/`：来源与简报、Provider/存储、Media application service、HTTP 契约和 worker 恢复/取消语义。
- `rpg_tts/tests/` / `tts_service/tests/`：正文标准化与分段、MP3 存储、缓存、HTTP 契约和 worker 恢复语义。

修改 Agent 组合或 turn pipeline 时使用以下专项集合，随后仍需运行完整基线与 Core integration：

```bash
uv run python -m pytest \
  rpg_core/tests/agent/test_agent.py \
  rpg_core/tests/agent/mailbox/test_agent_mailbox.py \
  rpg_core/tests/agent/runtime/test_agent_lifecycle.py \
  rpg_core/tests/agent/runtime/test_main_model_runtime.py \
  rpg_core/tests/agent/runtime/test_agent_context_service.py \
  rpg_core/tests/agent/runtime/test_agent_tool_service.py \
  rpg_core/tests/agent/turn/test_turn_hooks.py \
  rpg_core/tests/agent/turn/test_turn_runtime_factory.py \
  rpg_core/tests/agent/turn/test_turn_orchestration.py \
  rpg_core/tests/agent/turn/test_turn_transaction.py -q
uv run python -m pytest agent_service/tests -q
INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q
SERVICE_INTEGRATION_TEST=1 uv run python -m pytest tests/integration -m service_integration -q
```

Dream 后端与 Play WebUI 的聚焦验证：

```bash
uv run python -m pytest \
  rp_memory/tests/test_dream.py \
  rp_memory/tests/test_dream_application.py \
  rp_memory/tests/test_dream_recovery.py \
  rp_memory/tests/test_story_memory_application.py \
  rpg_data/tests/test_dream_memory_data_service.py \
  dream_service/tests \
  play_api/tests/test_dream.py \
  play_api/tests/test_events.py -q
cd play_webui && npm run build
```

真实 Dream Provider 验收必须显式 opt-in。`llm_service/llm.test.yaml` 可将 `dream.shallow` / `dream.deep` 覆盖到当前配置的 `deepseek_v4_flash`；测试使用临时 Session，只断言 schema、Evidence 和 Proposal 不变量，不固定生成措辞，也不得输出 API key：

```bash
# 终端 A：LLM Service 自身必须使用 test profile，保持运行直到验收结束
RPG_WORLD_PROFILE=test uv run python -m run_llm

# 终端 B：运行真实 Dream Provider 验收
RPG_WORLD_PROFILE=test DREAM_LIVE_TEST=1 \
  uv run python -m pytest dream_service/tests/integration -m dream_live -q

# 验收结束后回到终端 A，按 Ctrl-C 关闭 LLM Service
```

测试只连接已经运行的 LLM Service，不会代为启动或切换远端进程的 profile。未设置
`DREAM_LIVE_TEST=1` 时 `dream_live` 测试必须跳过；显式开启后 Provider 或结构化契约错误必须使测试失败。

跨服务覆盖矩阵见 `docs/backend-integration-matrix.md`。`service_integration` 会以随机 loopback 端口启动独立 LLM、Agent、Media、Play API 测试进程，真实经过 HTTP/SSE、lifespan、SQLite 和媒体文件落盘，但最终模型与图片 Provider 仍为 deterministic fake，不需要 API key 或公网。

## 当前实现优先级

1. **P0：Play WebUI 主体验与 Play API 契约**。优先保障 session 房间、SSE/turn、workspace、characters、lorebook、status-tables、ops 等 Web 主链路。
2. **P1：核心数据、上下文与记忆链路**。确保角色卡、世界书、状态表、summary、story memory 和 rp_memory 在全局 `session_id` 语义下稳定可用。
3. **P2：Telegram/CLI 轻量入口稳定性**。保持真实 Telegram 长轮询、会话菜单、stream/non-stream、异常回复、命令菜单和运行配置可靠。
4. **P3：玩法模块与沉浸式细节**。骰子、战斗、物品等新增体验型能力优先沉淀到 Play WebUI，并通过受控工具和状态读写接入核心。
