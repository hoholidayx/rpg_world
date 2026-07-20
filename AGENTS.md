# Repository Guidelines

## 产品与模块边界

- Play WebUI 是沉浸式 RP 的唯一 Web 主体验，Telegram 只承担轻量入口、通知和兜底交互；不要恢复 Dashboard API/WebUI，新增体验型能力优先落到 Play WebUI。
- 修改启动流程、渠道生命周期、共享状态或 `AgentManager` 前先阅读 `CLAUDE.md`。各进程使用独立入口：`run_agent.py` 独占 `AgentManager` / `RPGGameAgent`，`run_dream.py` 独占 `rp_memory.dream` 编排，`run_llm.py` 独占 Provider 密钥、OpenAI/llama client 和本地 llama runtime；Media、TTS、Play API 与渠道只能通过相应服务客户端访问这些能力。`run_all.py` 只能编排独立子进程，不得持有或合并业务 runtime。
- `play_api/`、`agent_service/`、`dream_service/`、`media_service/`、`tts_service/` 和 `channels/` 是接入/进程边界；`rpg_core/`、`rp_memory/`、`rpg_media/`、`rpg_tts/` 是无框架业务模块。HTTP、SSE、Telegram、CLI 和前端概念不得进入业务模块。
- Play WebUI 访问 Dream、Media、TTS 和 Agent 能力必须经 Play API 代理；Play API 不直接持有 Agent runtime、LLM Provider 或读取媒体二进制工作区文件。独立服务故障不得阻塞基础聊天加载与输入。
- Dream v1 无入站鉴权，只允许监听 localhost/loopback IP，非 loopback 配置必须启动失败。
- `llm_client` 是 loop-owned 纯异步客户端：所有 API 在创建/首次使用它的同一事件循环中 `await`，不得跨线程/loop 复用 `AsyncClient`，不得以 `asyncio.run()`、同步 HTTP 或 sync-to-async 桥接调用；configure/reset/release 必须 await 关闭旧资源。业务代码不得直接创建 OpenAI/llama 客户端或读取 Provider 密钥。
- 本地 llama 保持 LLM Service 进程内、按不可变模型键由 actor 线程串行执行；不要恢复子进程 worker。`request_timeout_ms` 包含排队和执行，无法中断的 native call 超时后自然排空。
- LLM Service `/health` 免 Bearer 鉴权且只表示进程存活/配置已加载；其它业务接口仍鉴权。`RPG_WORLD_LLM_SERVICE_TOKEN` 与 `RPG_WORLD_PLAY_EVENT_TOKEN` 未设置时仅本地开发可回退内置 token 并 warning，生产必须显式覆盖，内部事件 token 不得暴露给 WebUI。
- 会话链路统一使用全局短 `session_id`；创建时绑定 `workspace_id + story_id`，之后由服务端反查上下文。`AgentManager` 只按 `session_id` 缓存 agent；不要恢复三元 locator、`api_key` 缓存键、`cli_direct` 默认 ID 或用户自定义 session ID 创建入口。
- CLI/Telegram 通过 catalog 解析配置的 `workspace_id + story_id + optional session_id + session_title`，运行时能力统一走 Agent service；工作区选择不得写回共享运行时状态。
- `data/` 是运行数据目录，历史、摘要、索引、SQLite WAL/SHM 和导入运行文件默认不纳入提交。

## `rpg_data` 数据层约束

- `rpg_data` 负责数据如何可靠、高效、原子地存取，不应被窄化为简单 CRUD：数据库连接/migration、Peewee record、typed DTO、复杂关联查询、分页/排序、高效 read model、批量写入、CAS/条件更新、数据库级原子操作、序列化、归属与完整性校验都应留在数据层；业务层不得拼装 SQL 语义或制造 N+1/事务竞争。
- `rpg_data` 不得决定产品行为：不做默认选择、调度/抽样、优先级合并、冷却/重试、状态机下一步、生命周期策略、派生/重置/删除保留矩阵、Prompt/模板渲染、玩家文案或跨聚合业务编排。
- `DataServiceGateway` 是合法的数据库生命周期与 Data Service 注册表；composition root 可从中取得具体 service，但业务 service 必须依赖窄 Protocol/Data Service，不得持有整个 Gateway 作为 service locator。现有非组装层 Gateway lookup 与整 Gateway 注入分别由架构测试显式 allowlist，禁止新增。
- `rpg_data` 的公开类型化持久化边界统一使用 Service 语义；Session、Plot、Dream/Memory、Status 等新的大业务聚合入口命名为 `*DataService`，Repository/Peewee 实现只在 `rpg_data` 内部使用。既有简单 Character/Lorebook CRUD 可保留清晰的 `*ReadService` / `*ManagementService`，不为后缀或形式统一机械增加 application/facade/adapter 样板层。
- 业务归属固定：Plot Scheduler 与 Narrative Outcome 在 `rpg_core/rp_modules`，Session/角色/Opening/状态/Scene 在 `rpg_core`，Dream/Story Memory/Persistent Memory 在 `rp_memory`，媒体与语音分别在 `rpg_media`、`rpg_tts`；service composition root 只负责依赖组装和进程适配。
- 需要跨多次数据操作保持原子性时，由 `rpg_data` 提供无业务语义的 transaction/unit-of-work 或调用方指定的 bulk primitive，业务层决定事务内做什么。业务层不得直接使用 Repository/Peewee record，跨层结果使用 typed contract；Session、Memory、Status 与 Media 存储契约优先从 `rpg_data.model.*` 引用，`rpg_data.models` 仅保留兼容重导出。
- 数据层错误只表达 not found、integrity、conflict、conditional update failed 等数据事实；领域错误码、HTTP 状态和玩家提示由上层映射。`rpg_data` 不得导入业务模块、事件 publisher、WebUI 或渠道语义。
- 完整范式与 Review 清单见 [docs/rpg-data-architecture.md](docs/rpg-data-architecture.md)。新代码不得扩大现有越界；后续整改只以迁出真实业务决策、收紧依赖或修复事务/查询问题为目标，不按文件长度或层次数量机械拆分。

## Agent 与 Turn 不变量

- `RPGGameAgent` 只作为 composition root + public facade；FIFO/取消归 `AgentMailbox`，Session 操作归 `AgentSessionService`，生命周期归 `AgentRuntimeLifecycle`，模型/Context/工具/正文协议分别归对应 runtime/turn service。生产代码不得访问 `agent._*`、builder 或 SubAgent 私有字段。
- Session scoped Context 使用不可变 `AgentContextResources` 整组替换；reload/switch 后显式重绑 SubAgent provider、memory store、compressor、RP registry 与 base tools。玩家角色、RP Module、Plot Schedule 和 Persistent Memory 等本轮选择必须在 Context 门禁前进入不可变 snapshot/plan，并由门禁、Preview、SubAgent 和主 Agent 共用。
- Context 主流程保持结构化，最终只由 `ContextRenderer` 渲染；调试 markdown/token 概览归 `ContextInspector`，不得回流到 `RPGContext`。内部随机 sample、权重和来源诊断不得进入 LLM Context、公开工具结果或玩家界面。
- Turn 生命周期保持 `TurnRequest → TurnExecutionSnapshot/Plan → TurnRuntime`。`send` / `send_stream` 共用 preprocessor、plan resolver、runtime factory、preparation 和 orchestrator，只允许 LLM runner 与输出适配不同，不复制 preflight、Context、工具、commit、discard 或 close 分支。
- Hook 顺序固定为 `StatusPreflightHook → PlotSchedulingPreflightHook → MemoryRecallHook → runner/commit → PostCommitHooks`。Status 未处理异常终止；Plot soft 判断失败记录 error 并继续；memory recall 和 commit 后 story-memory/summary 失败 warning-and-continue。不要引入事件总线、动态优先级或第三方 hook 注册。
- `AgentTurnTransaction` / `TurnScratch` 是 turn 写入的唯一事务边界。通过角色校验、RP/Plot snapshot 和 Context 门禁后，user/assistant message、Narrative Outcome、Plot decision、scene/status 才能进入 scratch；完整成功后短事务统一提交。取消、Provider/stream ERROR、缺失 DONE 或 commit 失败必须 discard，流式 DONE 只能在 commit 成功后携带最终 usage 与 `committed_turn_id` 发出。
- 主 Context 门禁只估算当前下一轮 Context，不计待发送 input，并为同轮最多两条 Plot directive 保守预留；达到 `agent.context_window_reject_threshold_ratio` 拒绝正文但始终允许斜杠命令。SessionRoom 圆环只使用 `context-preview` 估算，上一轮 Provider usage 只展示在对应回复/详情，不得覆盖门禁数据、持久化或写 localStorage。
- 主 Agent LLM 选择保持 `config default < story override < session override`，只允许 `agent.main.provider_option_keys` 白名单；`null` 清除当前层覆盖。生成中切换从下一 turn 生效，不取消当前 turn、不自动压缩。
- Agent/Play SSE 业务错误使用 `error_code` / `errorCode`，底层文本留在 `content` / `message`，不得把错误码拼入正文或与 HTTP `statusCode` 混用。停止生成必须按 `requestId` 经 Play API → Agent service；只有收到 `cancelled` 才展示 stopped，不补偿已提交 turn。

## RP Module、Scene 与状态表

- RP Modules 是仓库内置 RP 玩法模块，不是通用 Skill 或第三方代码加载系统。Story 挂载定义能力上限，Session 只能在已挂载模块内稀疏覆盖；配置按 `system < story < session` 合并。新 Story 自动挂载当时 catalog 中的默认模块，后续新增模块不回填既有 Story。Agent 在门禁前解析不可变 `RPModuleSelectionSnapshot`，不得把动态选择写回共享 Registry。
- Narrative Outcome 只向 LLM 暴露 `rp_story_outcome(reason, actor?)`；每 turn 最多一个五级结果且重复调用幂等复用。不得向 LLM 暴露 Dice 表达式、DC、权重或随机数；Dice 仅保留手动 `/roll`、`/check_dc` 与解析调试。权重五项均为 `0..100` 且总和严格为 100，`success_with_cost` 必须完整达成原目标。
- Plot Scheduler 是 Story 级 RP Module。每个 IC/GM turn 最多选择一个到期大纲节点和一个池事件，同一事件不得由两个 lane 同轮注入，OOC 不调度；Scene 时间统一由 `SceneTime` 严格解析。强制候选到时直接注入，软候选通过 `agent.plot_scheduler` 读取完整 fixed layer、scene/状态表、最近 N 个完整 IC/GM turn 和当前输入判断适宜性。
- Plot 的 `deferred | error` 不阻断主 turn，并按完整 IC/GM turn 间隔重试；注入只进入 RP Module 动态层，不写 SSE/历史正文。大纲节点不重复，池事件按稳定 `event_id` 承载触发/延期/冷却身份，移动池不得重置语义；`container_id` 仅为当时来源快照。`/clear` 清决策账本但保留 Session 覆盖，派生只复制分支点前 `triggered` 与覆盖。
- Plot WebUI 使用独立 `/plot-scheduling` 页面，不向 SessionRoom 增加 HUD、轮询或前端 LLM 判断。决策历史按自增 `id DESC` + `beforeId` 分页，公开页最大 200，内部可多取一条判断 `hasMore`。
- `当前场景` 仍以 Story 挂载的 `status_kind="scene"` SQL document 为真源，但在 Agent 中是专用高优先级 user prefix，不进入普通 `STATUS_TABLES`。Scene 字段固定 `realtime`，不用普通 `status_table_set_values`；默认只允许 LLM 修改既有 key，只有显式开启 `agent.scene.allow_runtime_key_changes` 才能增删非锁定 key。
- 普通状态字段频率只允许 `realtime | event_driven | deferred | manual`：`event_driven` 需要非空 `updateRule`，`deferred` 仅用于 normal 表并在同 Session 下一 mailbox 项前提交，`manual` 禁止 LLM 写入。统一工具只修改当前 Session 表的既有 key，并在工具层复核 table/key/frequency allowlist。
- StatusSubAgent 固定执行 Outcome 判定 → 状态目标路由 → scene/逐表更新；每次 LLM 调用只获得一个目标和 key allowlist。快速更新按目标使用内存 checkpoint，单目标失败只回滚该目标并继续；checkpoint 创建/恢复失败终止并 discard 整个 turn。retry/edit/truncate 重抽裁定，但不回滚已提交状态表。
- 状态表 SQL 真源是封装后的 `document_json`，`status_kind` 仅 `scene | normal`；对外返回 typed document/row，不暴露原始 JSON。模板挂载后才影响新 Session 副本，现有副本不随模板修改；`session_native` 独立保存。并发写入保持 last-write-wins，scratch baseline 偏离只 warning，不改为 CAS 冲突。
- 角色绑定状态表按 `characterName` 分组；角色名缺失时可按 mount 关系修复，无法解析则 warning 并从 LLM Context 排除，不使用“未知角色”共享降级组。一名角色可绑定多张表，一张 Story 状态表最多绑定一个角色，不给 `story_character_mount_id` 加唯一约束。

## Story、Session 与消息

- Catalog 保持 `workspace → stories → sessions`；角色卡和世界书通过 Story mount 复用，同一资源可挂载多个 Story，只禁止同 Story 重复挂载。`session_id` 规则为 `^[A-Za-z0-9_]+$` 且由系统生成，用户只指定 title。
- Story 的 `summary` 是短摘要，`story_prompt` 是固定提示模板；Opening 真源是 `rpg_story_openings` 中有序的 0–3 条标题＋正文，旧 `rpg_stories.first_message` 仅为迁移来源。Story 业务层只允许 `{USER_PLAY_ROLE_NAME}` 模板变量，第一条为缺省 Opening；Story Prompt 每 turn snapshot 只渲染一次。
- 玩家角色是 Session 级绑定，对外状态只为 `bound | invalid`。WebUI 空会话使用不可取消的“角色 → 开局”向导，最终通过 Agent `/role_bind <角色序号> [开局序号]` 原子提交；invalid 时普通正文不写历史、不调用 LLM。首次有效绑定且主历史为空时才向 main/backup 追加 Opening，切换角色或普通历史操作不得重放。
- 玩家角色必须进入本轮不可变 snapshot；fixed layer `[player_character]` 是身份唯一真源，角色 metadata 不得承载 PLAYER/NPC 身份。切换只影响后续 turn，并刷新共享 Context 资源，不改写历史、摘要或记忆。
- `/clear` 保留 Session 身份/profile、append-only 冷备、角色/Opening、标题、模型和 RP Module 覆盖；清除主历史、Outcome/Plot ledger、Story/Persistent Memory、Dream、Session runtime、deferred progress 和 Session 媒体引用，重建模板状态表并清空 native 表值。有效绑定按稳定 Opening ID 重放 turn 1，缺失时回退当前第一条。
- 删除 Session 与 `/clear` 严格区分：Agent service 先隔离 Session、取消 turn、释放资源，再删除 catalog/级联数据、冷备与 runtime；数据库失败恢复隔离目录，提交后目录清理失败返回 `pending`。Play API 只转发删除，WebUI 两个入口都必须确认。
- 持久消息必须有正数 `turn_id`、`seq_in_turn`，主表唯一 `(session_id, turn_id, seq_in_turn)`，冷备 append-only。Summary/Story Memory 进度只使用消息行 `summary_processed` / `story_memory_processed`，不恢复 last-turn 游标；主 Agent Context 仅过滤 `summary_processed=true`，其它历史 API 和 SubAgent 仍读取完整未删除历史。
- `text_output_format` 是默认 fixed layer 约束，不进入 RP Module；带 `<rp-narration>` / `<rp-character>` 标签的全文是 assistant `content` 真源，原样进入 SSE、历史和数据库，不写解析后的 message metadata。

## Memory 与 Dream

- Memory 保持 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三路独立，`HybridRetriever` 只融合。配置使用 `keyword_k` / `hybrid_keyword_weight`；`raw_md_mode` 仅 `disabled | always | fallback_only`；rerank 统一使用 `PointwiseMemoryReranker`。
- 每个 Session 的 Memory 操作由同一 async lock 串行，不同 Session 可并发。watchdog 线程只经 `loop.call_soon_threadsafe()` 入队，loop-owned consumer 执行索引与 SQLite 更新，文件/hash/chunk/SQLite 阻塞工作使用 `asyncio.to_thread()`。本地能力初始化不触发远端解析，远端失败保留本地 fallback 并在后续调用重试。
- Dream 只生成 Session 级、长期稳定的世界内事实；OOC、用户偏好、Provider/系统配置和易变 Scene 不进入 Persistent Memory。运行维度固定为 `shallow | deep × incremental | full`，Shallow 只使用来源仍精确有效的 Story Memory/Summary，Deep 以当前主消息表 IC/GM user/assistant 为真源。
- Dream 必须 proposal-first：生成只创建持久 proposal，WebUI 手动刷新且不轮询；用户可编辑 `text / memory_kind / epistemic_status / salience`，不可编辑动作目标与 Evidence。同 Session 最多一条 generating，进程重启将 orphan generating 标为 interrupted，不使用持久 worker 或自动模型重试。
- Dream Proposal/恢复/Apply 与 Persistent Memory 生命周期只归 `rp_memory.dream`，Story Memory 规范化、exact dedupe、合并、Evidence 和 version 只归 `StoryMemoryApplicationService`；`rpg_data` 仅暴露 `dream_memory` / `story_memory` typed CRUD/CAS/transaction。Apply 由领域层唯一编排 SQLite `IMMEDIATE`，写入前后各重捕获一次来源；第二次确认失败必须回滚 ledger，再独立把仍为 ready 的 Proposal 标为 stale。
- Memory identity 由代码按规范化 `memory_kind + epistemic_status + text` 生成。稳定 Memory ID 指向不可变 revision，Evidence 固定 message ID/version/content hash，生命周期仅 `active | retired | superseded`，每 Session 最多 64 条 active；命中 retired identity 时复用 ID 并新增 revision，active/superseded 冲突拒绝。Persistent Memory 唯一真源是 SQL ledger，Context 只投影 Evidence 仍有效的 active 当前 revision，不读写旧 `persistent_memory.json`。
- Dream Map/Reduce/Proposal 共用有界 LLM 并发与候选硬上限；模型不收敛时确定性裁剪，Full Deep 发生实际截断时不得仅因候选缺席退休事实。Dream repository 在单独 worker 线程内创建/使用/关闭，不能阻塞 service loop。

## Media、TTS 与后台事件

- 生图保持“手动选择 1–20 个连续已提交 turn → 检查/编辑 `VisualBrief` → 异步提交”；来源快照/指纹在提交和重试前校验历史变化。图片、Gallery、背景引用不得写入消息正文、metadata、turn/SSE 或 localStorage。
- 图片二进制存入 `{workspace_root}/assets/images/{sha256}.<ext>`，只接受魔数确认的 PNG/JPEG/WebP；Blob 按 `(workspace_id, sha256)` 去重，但每次成功生成独立 UUID Asset。Media Job 使用持久单 worker 队列、无自动重试；重启保留 queued 并中断遗留 active job。正在作为背景的 Asset 不可删除，最后一个引用删除后才回收 Blob 与文件。
- Media 来源范围、VisualBrief 来源确认、Library metadata、删除门禁、背景选择/评估和 worker 恢复策略归 `MediaApplicationService`；worker 只依赖该业务入口。`MediaDataService` 仅执行 typed CRUD/read model、CAS claim、引用查询、条件转换和调用方准备的原子 completion。
- TTS 只按已提交 assistant `message_id` 派生，正文清洗、分段、指纹和 MP3 缓存归 `rpg_tts`；语音不得进入 Agent turn、正文 SSE、message metadata 或 localStorage，OpenAI Speech 仍通过 LLM Service。
- Dream 与 Derivation 终态通知独立于正文 SSE：领域 worker 在 `ready | failed | interrupted` 落库后通过 typed NotificationSink 通知，publisher 只在 service composition root 注入，发布失败只 warning。Play API 独占单进程 best-effort 事件 Hub，GET job/proposal 仍是真源；WebUI 根 Providers 只建一条 EventSource，通知 UI 不自动轮询、跳转、回写任务或持久化。

## 配置、测试与提交

- 配置按进程/模块拆分并通过 typed accessor 读取；业务代码不得直接解析 YAML key。只有 LLM Service 读取 `llm_service/llm.yaml`；Play WebUI 通过 typed loader 读取 `play_webui/play_webui.config.json`。Workspace 相对路径必须经 `rpg_data.settings.resolve_workspace_relative_path()` 校验不逃逸根目录。
- 跨模块状态值、阶段名和 document 字段名使用集中常量/枚举；固定协作者使用明确类型或 Protocol，不用 `getattr` 和静默 fallback 掩盖接口错误。
- `rpg_data` bootstrap 不硬编码 demo 数据；默认保留 SQL 未索引的 workspace/story/session 目录，只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才允许清理并记录结果。
- 常用入口：`uv sync`；`uv run python -m run_all`；单进程使用对应 `run_agent|run_llm|run_dream|run_media|run_tts|run_play_api|run_cli|run_telegram` 模块；前端使用 `cd play_webui && npm run dev|build`。
- Python 基线：`uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests rpg_media/tests media_service/tests rpg_tts/tests tts_service/tests dream_service/tests -q`。外部调用默认 mock；真实 Provider 验收必须显式 opt-in，密钥不得进入测试、文档或日志。
- 测试跟随业务 owner：Agent/Context/Session/Plot/Status 改动补 `rpg_core/tests`，Memory/Dream 规则补 `rp_memory/tests`，数据 CRUD/migration 补 `rpg_data/tests`，服务/代理边界补对应 service 与 Play API 合约测试；Play WebUI 管理能力改动必须运行构建。保留 `pytest.ini` 的 `asyncio_mode = auto`。
- 提交信息使用 `feat:`、`fix:`、`refactor:`、`chore:` 等前缀；一次提交只处理一个逻辑主题。提交前排除 `data/` 运行文件；PR 说明包含影响模块、行为/配置/数据结构变化和测试结果。
