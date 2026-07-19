# Repository Guidelines

## 工作边界
- 当前产品路线：WebUI 是沉浸式 RP 主体验，Telegram 是轻量入口、推送通知与兜底交互；短期仍保持 Telegram 稳定性，但新增体验型能力优先沉淀到 WebUI。
- Play WebUI 是唯一 Web 主体验，承担玩家游玩、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口；不要恢复 Dashboard API/WebUI。
- 修改启动流程、渠道生命周期、共享状态或 `AgentManager` 前，先阅读 `CLAUDE.md`。
- 根目录聚合 supervisor 入口已移除；各进程必须通过独立入口启动。只有 `run_agent.py` 持有 `AgentManager` / `RPGGameAgent`，并使用 `rp_memory` 做在线召回、索引和 Persistent Memory 的只读 Context 投影；`run_dream.py` 独立持有无框架的 `rp_memory.dream` 领域编排，经 `rpg_data` 读写 Dream SQL 账本。其它进程只能通过相应服务客户端访问这些能力。只有 `run_llm.py` 读取 `llm_service/llm.yaml`、Provider 密钥并持有 OpenAI/llama Provider 与本地 llama runtime；Agent、Memory、Dream、Media、TTS 等调用方只能通过 `llm_client` 访问 LLM 服务。
- `llm_client` 是事件循环归属的纯异步客户端：`health()`、`get_catalog()`、`get_provider()`、`get_speech_profile()`、`speech()`、`embed()`、`dimension()` 及推理 API 都必须在创建/首次使用它的同一 loop 中 `await`，不得跨线程/loop 复用 `AsyncClient`，不得在业务代码中用 `asyncio.run()`、同步 HTTP 客户端或 sync-to-async 桥接。重新 configure/reset 必须 await 关闭旧连接池。
- Agent/Memory 的远端 LLM I/O 直接 await；调用方需要等待结果时由调用方 await，不把阻塞转移到 Agent 事件循环。Memory 的 `create()` / `initialize()` 只建立本地 text/keyword/raw-md 能力，首次 `recall()` / `reindex()` 才懒解析 embedding/planner/reranker；远端失败保留本地 fallback，后续调用继续重试。
- 每个 session 的 Memory 操作由同一 async lock 串行，多个 session 可并发。watchdog 回调线程只允许通过 `loop.call_soon_threadsafe()` 入队 source ID，实际去重、索引、embedding 与 SQLite 更新由 loop-owned 单 consumer 执行；memory 文件/hash/chunk/SQLite 阻塞工作使用 `asyncio.to_thread()`。Memory、Agent 与 LLM client 的释放 API 必须 await。
- 本地 llama 仍是 LLM Service 进程内 runtime，不恢复子进程 worker。每个不可变模型缓存键使用一个 actor 线程串行执行；`request_timeout_ms` 包含排队和运行时间，completion/stream/rerank 在安全边界协作取消。无法中断的原生 embedding/eval 超时后允许 actor 自然排空，同模型后续任务继续等待；关闭等待 `llama_shutdown_grace_ms` 后只记录仍在排空的 native call。
- LLM Service `/health` 故意免 Bearer 鉴权，只表示进程存活和配置已加载，不验证调用方 token；catalog、chat、embedding、rerank 等业务接口仍必须鉴权。不要把 health 成功解释成凭据有效。
- `RPG_WORLD_LLM_SERVICE_TOKEN` 未设置时，LLM Service 记录 warning 并与调用方共同回退到 `rpg-world-local-token`，不得阻止进程启动；该默认值只用于本地开发，非本地部署应显式设置环境变量覆盖。
- `RPG_WORLD_PLAY_EVENT_TOKEN` 未设置时 Agent、Dream 与 Play API 共同回退到 `rpg-world-local-event-token` 并 warning；该默认值只用于本地开发。令牌只保护内部事件 POST，不得暴露给 WebUI EventSource。
- 保持 `play_api/`、`channels/` 为接入层，`rpg_core/` 为无框架核心层；不要把 HTTP、Telegram、CLI 细节侵入核心模块。
- `rpg_media/` 是与 `rpg_core/` 同级的无框架高级能力模块；`media_service/` 独立持有图片 Provider、持久任务 worker 和媒体 HTTP 边界。Play WebUI 只能经 Play API → `MediaClient` 访问它，Play API 不得直接读取工作区图片文件，Media service 不得导入 Agent runtime 或持有 llama worker。
- `rpg_tts/` 与 `rpg_core/`、`rpg_media/` 同级，负责正文清洗、分段、缓存指纹与 MP3 存储；`tts_service/` 独立持有持久任务 worker 和 HTTP 边界。TTS 只按已提交 assistant `message_id` 派生语音，不得进入 Agent turn、正文 SSE、message metadata 或 localStorage；OpenAI Speech 仍通过 `llm_client` 由 LLM Service 唯一持有 Provider 与密钥。
- `rp_memory.dream` 是无框架的 Session 级离线归纳领域；`dream_service/` 独立持有 HTTP 边界、进程内 async 生成任务和 loop-owned `llm_client`，默认监听 `127.0.0.1:8014/dream/v1`。Dream v1 无入站鉴权，配置必须强制使用 localhost/loopback IP，非 loopback host 启动失败。Play WebUI 只能经 Play API → `DreamClient` 访问它；Dream service 不得导入 Agent runtime、`MemorySubAgent` 或 `llm_service`，故障不得影响聊天或 Context 构建。
- Dream 与 Session Derivation 的后台终态通知必须独立于 Agent 正文 SSE：领域 worker 只依赖类型化 NotificationSink，在 `ready | failed | interrupted` 成功落库后通知；service composition root 才能注入 `play_events` HTTP publisher。`rpg_data` 不得导入事件模块、持有 publisher 或 WebUI 语义。发布失败只能 warning，不得改变任务终态。
- Play API 独占进程内后台事件 Hub：内部 `POST /play-api/v1/internal/events` 使用 `RPG_WORLD_PLAY_EVENT_TOKEN` Bearer 鉴权，全局 `GET /play-api/v1/events/stream` 供根 WebUI EventSource 使用。首版是单进程/单 worker、无 outbox/补发/消费确认的 best-effort 链路；GET Proposal/Derivation Job 仍为事实真源。WebUI 只在根 `Providers` 建立一条连接并把最近 50 条事件保存在内存；独立 `features/notifications` 模块可单向读取并展示、标记已读或清除通知，但不得自动轮询/刷新、跳转、回写任务状态或写 localStorage，事件层不得反向依赖通知 UI。
- Play WebUI 会话内链路只使用全局短 `session_id` 定位；创建 session 时在 `rpg_data` 绑定 `workspace_id + story_id`，之后由 Play API 反查上下文并调用 Agent 服务。不要恢复前端每次传 `workspace + story_id + session_id` 的三元 locator。
- 玩家扮演角色是 session 级绑定，保存在 `rpg_session_profiles.player_character_id` 和 `player_character_snapshot_json`。WebUI 的选择/切换和 CLI/Telegram 文本渠道都必须统一走 Agent 服务的 `/role_bind <序号>` 命令链路；Play API 只能转发到 Agent service 后刷新 summary，不要直接在 Play API/DataManager 中写绑定。
- CLI / Telegram 也必须通过 `rpg_data` catalog 解析会话：配置使用 `workspace_id + story_id + optional session_id + session_title`；未配置 `session_id` 时由 Agent service 创建系统生成 ID 的 session，配置了则只校验并加载既有 session。不要恢复 `workspace` 字段、`cli_direct` 默认 ID 或用户自定义 session ID 创建入口。
- `AgentManager` 只按全局 `session_id` 缓存 agent；`api_key` 不再作为 Agent service schema、AgentClient 参数或缓存键。LLM key/provider 选择只走 `llm_service` 配置。
- `data/` 是运行数据目录。会话历史、摘要、向量索引、SQLite WAL/SHM 等文件默认不纳入提交。

## 常用命令
- `uv sync`：安装后端依赖。
- `uv run python -m run_llm`：启动 LLM 服务（默认 `http://127.0.0.1:8012/llm/v1`；未设置 `RPG_WORLD_LLM_SERVICE_TOKEN` 时使用本地默认 token 并警告）。
- `uv run python -m run_agent`：启动 Agent 服务（默认 `http://127.0.0.1:8010/agent/v1`，通过同一令牌访问 LLM 服务）。
- `uv run python -m run_dream`：启动 Dream 服务（默认 `http://127.0.0.1:8014/dream/v1`，通过 `llm_client` 访问 LLM 服务）。
- `uv run python -m run_media`：启动 Media 服务与持久任务 worker（默认 `http://127.0.0.1:8011/media/v1`）。
- `uv run python -m run_tts`：启动 TTS 服务与持久任务 worker（默认 `http://127.0.0.1:8013/tts/v1`）。
- `uv run python -m run_play_api`：启动 Play API。
- `uv run python -m run_cli`：启动 CLI（通过 Agent 服务交互）。
- `uv run python -m run_telegram`：启动 Telegram（通过 Agent 服务交互）。
- `uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir channels --reload-dir rpg_core --reload-dir rp_memory --reload-dir llm_service --reload-dir tts_service --reload-dir rpg_tts --host 127.0.0.1 --port 8000`：直接调试 Play API。
- `uv run python -m channels.cli.repl`：启动独立 CLI。
- `uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests rpg_media/tests media_service/tests rpg_tts/tests tts_service/tests dream_service/tests -q`：运行 Python 测试基线。
- `uv run python -m pytest channels/tests/test_telegram.py -q`：专项验证 Telegram。
- `cd play_webui && npm run dev`：启动 Play 前端开发服务器。
- `cd play_webui && npm run build`：构建 Play 前端产物。

## 代码规范
- Python 使用 4 空格缩进，模块/函数用 `snake_case`，类用 `PascalCase`。
- Play WebUI 使用 Next.js App Router + React + TypeScript；React 组件用 `PascalCase.tsx`，hook/composable 用 `useXxx`，前端状态 store 用清晰的 camelCase 命名。
- 新增注释只解释非直观逻辑，避免复述代码。
- 配置访问必须走封装：核心业务用 `settings.memory_settings` 等类型化属性，渠道用 `channels.config.settings`，LLM 调用方用 `LLMClientManager`；只有 LLM Service 内部可使用 `resolve_biz_config()` / `LLMManager`。
- 业务代码不要直接解析 YAML key，不要直接 new OpenAI/llama 客户端。
- 跨模块重复使用的业务状态值、阶段名和 document 字段名不得散落为 magic string；优先复用集中常量或枚举。跨层返回结果优先使用 dataclass/类型化模型，不用约定字符串 key 的裸 dict 传递。
- `getattr`、反射式能力探测只用于真实动态扩展或外部兼容边界，并应注明理由；仓库内固定协作者必须声明具体类型或 Protocol，并直接调用其公开 API，不保留静默 fallback。

## 架构约束
- 生图首期链路保持“手动选择 1–20 个连续已提交 turn → 生成并检查/编辑 `VisualBrief` → 异步提交”。来源快照与 SHA-256 指纹用于提交/重试前检测历史变化；图片、Gallery、背景引用不得写入消息正文、message metadata、turn/SSE 或 localStorage。
- 媒体二进制固定写入 `{workspace_root}/assets/images/{sha256}.<ext>`，只接受经魔数确认的 PNG/JPEG/WebP。`rpg_media_blobs` 以 `(workspace_id, sha256)` 去重，但 SHA-256 不是业务 Asset ID；每次成功生成都创建独立 UUID Asset，以便保留不同简报、Provider 和来源语义。
- Media Job 使用数据库持久队列，默认单 worker、无自动重试；重启时保留 `queued`，把遗留 `running/cancelling` 标为 `interrupted`。删除正在作为 Session 背景的 Asset 必须失败；最后一个 Asset 引用删除时才回收 Blob 行和文件。
- `/clear` 同事务清除该 Session 的 Media Job、Gallery 与背景引用，但保留 Workspace Asset/Blob；删除 Session 依靠外键清除 Session 媒体关联，同样保留 Workspace Asset/Blob。Media service 不可用时媒体接口返回独立错误，不能影响聊天加载、输入或 Agent SSE。
- `VisualBriefPlanner` 是可替换契约，v1 使用配置驱动、无外部调用的 Demo planner。未来文本 LLM planner 应通过 `llm_client` 走通用 chat biz 配置且不得硬编码 Provider 黑名单（包括 llama）；本地 llama runtime 只能由 LLM service 持有，Media service 不得直接 new OpenAI/llama 客户端或导入 Agent runtime。
- 记忆检索保持 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三路独立；`HybridRetriever` 只负责组装与融合。
- keyword 配置使用 `keyword_k` / `hybrid_keyword_weight`，不要恢复 `bigram_k` 或 `hybrid_bigram_weight`。
- `memory.raw_md_mode` 语义保持：`disabled` 关闭，`always` 主召回，`fallback_only` 仅在主召回不足或失败时补候选。
- memory rerank 使用统一的 `PointwiseMemoryReranker`，不要恢复旧的 provider-specific reranker/factory。
- Dream 只生成 Session 级、可长期复用的世界内事实；OOC 内容、用户偏好、Provider/系统配置和 scene 等易变当前状态不得进入 Persistent Memory。运行维度固定为 `shallow | deep` × `incremental | full` 四种组合：Shallow 只读取原始 message ID/turn/version/content hash 仍精确匹配的 story memory，以及来源消息仍完整属于原 batch 的 summary；Deep 以当前主消息表中的 IC/GM user/assistant 为事实真源。
- Dream 必须 proposal-first：生成只创建持久 proposal，Play WebUI 仅手动刷新，不轮询；用户可逐项选择并编辑 `text / memory_kind / epistemic_status / salience`，但不可编辑动作目标与 Evidence，最终 Apply 在 SQLite `IMMEDIATE` 外层事务内重新捕获并再次确认 history/source/ledger 指纹后原子提交。同 Session 同时只允许一条 generating；任务不做持久 worker 或自动重试模型任务，进程重启把遗留 generating 标为 `interrupted`，ready/failed 状态可有限重试且耗尽后必须尽力中断该 proposal。新建前必须协调没有本地 task 的 SQL orphan；WebUI 恢复必须携带预期 generating proposal ID，已终态时直接返回旧 proposal，只有同一 ID 仍为 orphan 时才按原 depth/scope 新建替代任务。Dream 同步 SQL/文件工作统一由单线程 repository worker 串行，repository 必须在 worker 内创建、使用和关闭，不得阻塞服务事件循环。
- Dream 的事实 identity/dedupe key 必须由代码按规范化后的 `memory_kind + epistemic_status + text` 生成，不信任模型自由文本；exact dedupe 与 SQL 新记忆使用同一规范。最终 Reduce 候选必须受代码硬上限约束，Map/Reduce/Proposal 共用 `map_concurrency` LLM 并发上限；模型归并不收敛时按显著度、Evidence 与类别多样性确定性选择，不得把无界候选直接送入 proposal，发生实际截断时 Full Deep 禁止基于候选缺席退休事实。
- Persistent Memory 的唯一真源是 `rpg_data` SQL 类型化账本。稳定 Memory ID 指向不可变 revision，Evidence 固定记录主消息 ID/version/content hash，生命周期只允许 `active | retired | superseded`；`(session_id, dedupe_key)` 跨 lifecycle 保持唯一，ADD 再次命中 retired fact 时复用原 Memory ID、追加新 revision/Evidence 并恢复 active，active/superseded 冲突仍拒绝。每个 Session 最多 64 条 active。`rpg_core` 只投影 Evidence 仍有效的 active 当前 revision，不在读取时修改账本；turn plan 与 Context Preview 前必须用 `asyncio.to_thread()` 读取不可变快照，turn 将其写入 `TurnExecutionPlan` 并供门禁和实际 Context 显式共用，Preview 使用独立捕获值，失败时保留旧快照。不要读取或创建旧 `persistent_memory.json`，也不要自动删除用户已有的该文件。
- 上下文主流程保持结构化，最终发送给 LLM 前由 `ContextRenderer` 渲染；调试 markdown/token 概览放在 `ContextInspector`，不要回流到 `RPGContext` 数据模型。`verbose_logging` 开启时应记录 RP Module runtime section 的 metadata 与公开 content；模块内部诊断日志允许记录 sample、权重和来源，但不得把这些内部随机细节写入 LLM Context、工具公开结果或玩家界面。
- SessionRoom context 圆环始终只使用 `context-preview` 的下一轮主 Agent Context 估算；正常 `/turn` 或 `/stream` 完成事件的 provider usage 只展示在对应回复气泡和圆环展开详情中，不得覆盖圆环或参与下一轮门禁。不要新增独立 usage 获取接口、持久化 usage 或写 localStorage；比例、阈值和 K/M 展示由 Play WebUI 计算。
- 主 Agent LLM 选择保持 `config default < story override < session override`，只允许 `agent.main.provider_option_keys` 白名单；Story 详情页配置 story 默认，SessionRoom 配置 session 覆盖，`null` 清除当前层覆盖。生成中切换不取消当前 turn，从下一 turn 生效，不得因切换自动压缩。
- `当前场景` 在数据层仍是必须挂载到 story 的 `status_kind="scene"` 状态表，但在 Agent 编排中是专用实时状态：主 Context 只作为高优先级 user prefix，不进入普通 `STATUS_TABLES`；Outcome/Route 阶段可读取并选择 scene，命中后只获得 scene context 和专用 scene 工具。scene 字段固定 `realtime`，不得配置或进入 `event_driven` / `deferred` / `manual`，也不得使用 `status_table_set_values`。`agent.scene.allow_runtime_key_changes` 默认 `false`：LLM 与普通表一样只能修改已有 key 的 value，不能增删或重命名 key；此时 `scene_attr` 只枚举已有 key，`scene_time` 仅在已有 `时间` key 时注册，永不注册 `scene_del_attr`，空 scene 不暴露 scene 工具。只有显式开启时才保留新增非锁定 key、删除非锁定 key 和 `MAX_ATTRS` 上限行为；管理 API/Data 层手工 CRUD 不受该开关影响。
- RP Modules 是 RP 业务模块占位，不是通用 skill 体系；骰子、战斗、物品等能力应围绕 RP 工具流程和受控状态读写设计。
- RP Module 只动态选择仓库内置 Python 定义，不加载第三方代码。`rpg_rp_module_catalog` 是内置模块目录；Story 挂载决定能力上限，Session 只能在 Story 已挂载模块内覆盖启用状态和稀疏配置。新 Story 自动挂载 catalog 中当前标记为默认的全部模块，未来新增模块只自动进入之后创建的 Story。配置按 `system < story < session` 逐字段合并，Narrative Outcome 的 `weights` 作为不可拆分整组。Agent 必须在 Context 门禁前解析不可变 `RPModuleSelectionSnapshot`，并让门禁、StatusSubAgent 和主 Agent 共用该快照的 turn-local runtime；不要把动态选择写回共享 Registry。
- Narrative Outcome 是当前剧情分支随机机制：主 Agent 与 `StatusSubAgent` 只暴露高层工具 `rp_story_outcome(reason, actor?)`，每 turn 最多暂存一条五级结果且重复调用幂等复用；`reason` 是本次裁定不可缩小的整体目标边界，`success_with_cost` 必须完整达成该目标，代价不得抵消成功。不得把低层 Dice 表达式、DC、权重或随机数重新暴露给 LLM。Dice 只保留 `/roll`、`/check_dc` 与表达式解析调试能力。有效权重按 `config < story < session` 形成 turn 快照，五项必须为 `0..100` 整数且总和严格等于 100。
- `text_output_format` 是默认启用的 fixed layer 输出格式约束，不进入 `RPModuleRegistry`，用 `<rp-narration>` 和 `<rp-character name="...">` 约束 assistant 正文。带标签全文是 assistant `content` 真源，必须原样进入 SSE、历史和数据库；不要把旁白/角色分段写入 message metadata，也不要恢复 `metadata.messageDisplay`。
- `rpg_data` catalog 模型保持：workspace -> stories -> sessions；`rpg_story_characters` / `rpg_story_lorebook_entries` 是 story 挂载表，允许同一角色卡或世界书条目挂载到多个 story，只禁止同一 story 重复挂载。
- Story 主数据中，`summary` 是短摘要，`story_prompt` 是 Story 专属固定系统提示词；会话开局真源是 `rpg_story_openings` 中按顺序保存的 0–3 条稳定 Opening（标题＋正文），旧 `rpg_stories.first_message` 物理列只作为 `0018` 迁移来源，不得恢复为生产读写路径。Opening 正文与 Story Prompt 当前只允许 `{USER_PLAY_ROLE_NAME}` 白名单变量，存储/API 返回原始模板；未知变量必须在 API 和数据层保存边界拒绝。第一条 Opening 是默认项，CLI/Telegram 与未指定 Opening 的调用方使用它；Story Prompt 在 turn snapshot 中渲染一次并供本轮 Context 共用。
- 玩家角色绑定状态只对外暴露 `bound | invalid`。缺失绑定、角色不存在、未挂载、snapshot 损坏或 snapshot mount/story 不匹配都视为 `invalid`；WebUI 进入空 SessionRoom 后使用不可取消的“角色 → 开局”向导，多 Opening 才显示第二步，最终角色与 `story_opening_id` 必须经 Agent `/role_bind <角色序号> [开局序号]` 一次原子提交。Agent 在普通 send/send_stream 进入 LLM 前强校验，invalid 时只返回固定编号角色列表，不写 user history、不调用 LLM。首次成功绑定且 main history 为空时，`SessionRoleService` 追加选中 Opening 的渲染正文到 main 和 backup；普通历史删除、截断或后续角色切换不得重新追加。
- `/clear` 是保留 catalog session 身份与配置的完整游玩数据重置：删除主历史、剧情裁定、story memory、Persistent Memory revision/Evidence、Dream proposal/state、session runtime 目录全部文件和全部 deferred 进度；Story 模板副本删除后按执行时当前挂载重建，`session_native` 表保留 ID、表结构、metadata 与字段策略但所有 value 置空。同名原生表与当前 Story 模板冲突时必须原子失败。保留 append-only 冷备、玩家角色绑定、`story_opening_id`、标题描述、主模型和 RP Module 覆盖；有效绑定会按保存的稳定 Opening ID 读取 Story 最新正文并重新渲染为 turn 1，Opening 已删除则回退当前第一条，无 Opening 则不写开场，后续玩家输入从当前下一 turn 开始。
- 会话删除与 `/clear` 严格区分：删除必须由 Agent service 先阻止同 session 新请求、取消活动/排队 turn 并释放 session scoped 资源，再删除 catalog session、全部级联数据（包括 append-only 冷备）和 runtime 目录。数据库失败时恢复隔离的 runtime 目录；提交后目录清理失败返回 `pending` 并保留为未索引运行目录。Play WebUI 只在会话中心详情和 SessionRoom 设置菜单最后提供入口，两个入口都必须使用前端确认弹窗。
- 玩家角色必须在 Context 门禁前进入不可变 `TurnExecutionSnapshot`，并由门禁、主 Agent、StatusSubAgent 与 Context Preview 共用。fixed layer 的 `[player_character]` 标签块是玩家身份唯一真源；角色卡只在 Context 投影时标注 `PLAYER_CHARACTER` / `NPC`，不得使用或写回角色 metadata 判断身份。角色切换只影响后续 turn，立即刷新 MemorySubAgent 等共享上下文，但不重写已有历史、摘要或记忆。
- `RPGGameAgent` 只作为 composition root + public facade：保留依赖组装、幂等 `initialize()` 与公开 API 委托。FIFO/取消归 `AgentMailbox`，会话操作归 `AgentSessionService`，初始化/reload/switch 归 `AgentRuntimeLifecycle`，模型/Context/工具分别归 `MainModelRuntime`、`AgentContextService`、`AgentToolService`，正文协议适配归 `AgentTurnService`。不要把这些实现重新堆回 `agent.py`。
- session-scoped Context 资源必须使用不可变 `AgentContextResources` 整组替换；reload/switch 后显式重绑 SubAgent context/tool providers、memory stores、compressor、RP registry 与 base tools。不要恢复 `_rpg_ctx` 字典、Agent 上的散落 manager/store 字段，生产代码不得访问 `agent._*`、builder 私有 store 或 SubAgent 私有 provider 列表；跨模块使用公开 `initialize()`、`session_id`、`session_manager`、`reindex_memory()` 或 `AgentCommandTarget`。
- Agent turn 代码保持 `TurnRequest`（调用方原始输入）→ `TurnExecutionSnapshot` / `TurnExecutionPlan`（门禁前不可变选择）→ `TurnRuntime`（事务期可变资源）三段生命周期。不要把 scratch、transaction、manager/provider 或解析后的配置塞回 `TurnRequest`；新增 turn 配置先进入 snapshot，再由 policy 或 `TurnPreparation` 消费。
- `send` / `send_stream` 必须共用 `TurnPreprocessor`、`TurnPlanResolver`、`TurnRuntimeFactory`、`TurnPreparation` 和 `TurnOrchestrator` 的业务 pipeline，只允许 LLM runner 与 `AgentReply`/SSE 输出适配不同；不要复制 preflight、Context/工具构建、commit、discard 或 close 分支。turn 子系统必须依赖显式 service/factory/hook，不得重新引入 `TurnHost` / `TurnPreparationHost` 或回调 `RPGGameAgent` 私有方法。
- turn hooks 只允许固定类型化阶段：`StatusPreflightHook → MemoryRecallHook → runner/commit → PostCommitHooks`。Status preflight 未处理异常终止并 discard，memory recall 失败 warning-and-continue，story-memory/summary post-commit 逐项隔离且不回滚。不要增加事件总线、动态优先级、运行时重排或第三方 hook 注册。
- Agent 普通正文在命令分发和角色校验后先解析 RP Module 不可变快照，再在创建 `AgentTurnTransaction` 前执行主 Context 窗口门禁；门禁只估算当前 Context，不计本次 input，达到 `settings.context_window_reject_threshold_ratio` 时拒绝正文但始终允许斜杠命令。通过门禁后，`send/send_stream` 的 user/assistant message、Narrative Outcome 与 scene/status document 才进入内存 scratch，LLM 完整成功后在短 commit 点统一写 main history、backup history、剧情裁定和状态表；summary compression 和 story memory extraction 仍只作为 commit 后副作用运行，失败只记录 warning。
- `AgentTurnTransaction` / `TurnScratch` 是 turn 写入的唯一事务边界：所有事务性状态先写 scratch；取消、provider/stream ERROR、缺失 DONE 或 commit 失败必须 discard。流式 DONE 只能在 commit 成功后发送并携带最终 usage 与 `committed_turn_id`。
- `StatusSubAgent` 必须由代码固定编排为独立 Outcome 判定 → 状态目标路由 → scene/逐张普通表更新。Outcome 命中时只执行一次 `rp_story_outcome` 并停止路由和预写；未命中时路由只可选择 scene、`realtime` 字段和 `updateRule` 已明确命中的 `event_driven` 字段，随后每次 LLM 调用只能获得一个目标及其 key allowlist。漏判或预裁定失败时，主 Agent 保留明确写出 `rp_story_outcome` 的无序 fixed contract 和补判工具；预裁定成功时不再注入该 fixed section，只以简短无序条目把最终结果和明确的 scene/status 工具边界放入 `RP_MODULES` runtime section，并从主 Agent schema 和可执行 registry 同时移除 outcome 工具。主 Agent 不得改判或重抽，只在结果造成实际、持久、确定的追踪值变化时写状态，允许零状态工具。有状态变化时必须先在无 RP 正文的工具调用轮完成同步，最终正文不得新增尚未同步的可追踪确定事实；不得询问玩家是否需要标记或更新状态。快速状态更新按 scene/单张普通表目标各自使用内存 checkpoint；provider、工具或范围校验失败只恢复当前目标，保留此前成功目标并继续后续目标和主 Agent。checkpoint 创建或恢复失败仍必须终止并 discard 整个 turn；不新增持久化 status journal 或可靠重试队列。retry/edit/truncate 删除消息与裁定并重新抽取，但不回滚已提交状态表。
- 状态字段更新频率只允许 `realtime | event_driven | deferred | manual`：旧字段缺省为 `realtime`；`event_driven` 必须有非空 `updateRule`，由本轮路由判断规则是否命中，不引入事件总线；`deferred` 只适用于 normal 表，由回复交付后的 `StatusSubAgent` 慢归纳按字段进度更新；`manual` 禁止 LLM 写入。deferred 归纳在同 session 下一 mailbox 项前完成，值与进度原子提交，单批失败不推进进度也不回滚已提交 turn。
- 持久化会话消息必须写入正数 `turn_id` 和 `seq_in_turn`；主消息表唯一约束 `(session_id, turn_id, seq_in_turn)`，冷备份表保持 append-only、不做唯一约束。新增写入路径必须让非法 turn metadata 在写入或加载边界失败，不要恢复 summary/story memory/history pagination 的降级分组。
- summary/story memory 的续处理进度只使用 `rpg_session_messages.summary_processed` / `story_memory_processed` 行标记，不恢复 last-turn 游标，不通过截断主历史表示已处理范围。
- 主 Agent Context 的历史投影只以 `summary_processed` 为真源：`true` 的单条消息不进入主 Agent Context，`false` 的消息进入；不要校验 `summary_batch_id`、batch 文件、`overall.md` 或 turn 完整性。Play/Agent history 接口继续返回完整未删除历史，StatusSubAgent/MemorySubAgent 等独立链路不套用该过滤；`context-preview` token 估算必须基于实际渲染的过滤后 messages。
- Agent/Play SSE 业务错误码走 `error_code` / `errorCode` 字段；`content` / `message` 保持底层错误文本，不把错误码前缀写入正文，也不要把业务错误码和 HTTP `statusCode` 混用。
- WebUI 停止生成必须通过 `requestId` 走 Play API `/sessions/{session_id}/stop` 和 Agent service `/chat/stop`；取消成功只丢弃当前 stream turn scratch，不补偿回滚已完成 turn，前端只有收到 `cancelled` 才展示 stopped。
- `rpg_data` 状态表采用 SQLite document 真源：模板表与会话表都在 SQL 行内保存封装后的 `document_json`，`status_kind` 只允许 `scene` / `normal`，不再维护状态表 type 表、workspace-relative 状态表文件路径或 CSV 内容源。`rpg_data` 对外返回 `StatusTableDocument` / `StatusTableRow` 等 dataclass，不暴露原始 JSON 字符串作为正文数据。
- 普通状态表上下文只展示 session 运行时表 ID、表名、作为“用途与更新规则”的 `description`、完整 KV 及字段更新策略；角色绑定表单独按 `characterName` 分组，不向 LLM 展示模板来源或通用挂载范围。普通表统一工具 `status_table_set_values` 只能修改当前 session 表中已有 key 的 value，不能增删改 key；工具必须绑定 turn scratch，同时提供给 `StatusSubAgent` 和主 Agent，并在工具层再次校验表 ID、key allowlist 和允许的更新频率。
- 状态表绑定角色时必须保证角色 name 非空。旧 session 缺少 `characterName` 时由 data context 读取路径优先通过 `characterMountId` 反查，必要时由状态表 `mountId` 回退到 `story_character_mount_id`，成功后回填；反查失败的角色状态表必须记录 warning 并从 LLM 上下文排除，不要使用共享的“未知角色”降级分组。
- 状态表模板通过 `rpg_story_status_tables` 挂载到 story 后才能被 session 感知；该挂载记录可选绑定同一 story 的一个角色挂载 `story_character_mount_id`。一个角色可绑定多张状态表，但一张 story 状态表挂载最多绑定一个角色；不要给 `story_character_mount_id` 增加唯一约束。
- `rpg_story_status_tables.mount_origin` 区分 `system_mount` 与 `story_template`。系统模板只能解除挂载；故事内创建的状态模板可删除挂载及其底层模板，删除前必须确认没有其它 story 仍在使用该模板。创建 session 时由 `CatalogService` 触发复制已挂载模板的 `document_json` 到 `rpg_session_status_tables`，`origin="template_copy"`，并把 story mount/角色绑定信息写入 session 表 metadata；后续模板修改不影响已有 session 副本。会话原生运行时表直接写入 `rpg_session_status_tables`，`origin="session_native"`。
- session 状态表并发写入当前采用 last-write-wins，不使用 `version`/CAS；Agent 提交发现持久化 document 已偏离 scratch 基线时，data 层记录 warning 后继续覆盖。不要把 warning 改成冲突回滚，除非产品重新决定并发策略。
- `rpg_data` bootstrap 只 materialize workspace/story/session 运行目录并初始化缺失的 session 状态表副本；不要在 bootstrap 代码中硬编码 demo 或业务数据。默认不删除不在 SQL 索引中的 workspace/story/session 目录；只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才会执行启动清理，并确保日志能清楚输出删除/跳过结果。
- Play API 会话内接口集中在 `/play-api/v1/sessions/{session_id}/history|history-page|scene|commands|turn|stream|stop|player-character`；Dream proposal/memory 管理集中在同一 session 下的 `/dream/*` 子资源并只代理 Dream service。workspace、characters、lorebook、status-tables、ops 等管理接口也归 Play API；旧 `chat.py`、`scene.py`、`commands.py` router 仅作占位，不要把它们恢复为主入口。`DELETE /play-api/v1/sessions/{session_id}` 只转发给 Agent service 的删除链路，不得在 Play API 进程直接删除 catalog session 或 Agent runtime。

## 测试要求
- 默认测试的所有外部调用使用 mock，避免真实 LLM、Telegram 或网络依赖；唯一例外是同时设置 `RPG_WORLD_PROFILE=test DREAM_LIVE_TEST=1` 并显式选择 `dream_live` marker 的 Dream Provider 验收。
- 新增测试文件命名为 `test_<feature>.py`。
- 修改 Telegram 适配、会话流程或渲染逻辑时，必须补 `channels/tests/test_telegram.py`。
- 修改 API/Play WebUI 管理能力时，补 `play_api/tests/` 契约测试并运行 `cd play_webui && npm run build`。
- 修改核心上下文、summary、session 行为时，补 `rpg_core/tests/`；修改 memory/Dream 领域行为时，补 `rp_memory/tests/`；修改 Dream SQL 账本、服务或代理边界时分别补 `rpg_data/tests/`、`dream_service/tests/`、`play_api/tests/test_dream.py`。
- Dream 默认专项基线为 `uv run python -m pytest rp_memory/tests/test_dream.py rpg_data/tests/test_dream_memory_service.py dream_service/tests play_api/tests/test_dream.py play_api/tests/test_events.py -q`。真实 DeepSeek V4 Flash 验收需要先在独立终端运行 `RPG_WORLD_PROFILE=test uv run python -m run_llm`，再在另一终端显式 opt-in：`RPG_WORLD_PROFILE=test DREAM_LIVE_TEST=1 uv run python -m pytest dream_service/tests/integration -m dream_live -q`；测试结束后关闭 LLM Service，不得把 API key 写入测试、文档或日志。
- 修改主 agent、LLM provider、session manager、context 或相关配置时，默认跑：
  `INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q`。
- 修改 Agent 组合、`rpg_core/agent/turn/`、transaction 或同步/流式编排时，至少先跑：
  `uv run python -m pytest rpg_core/tests/agent/test_agent.py rpg_core/tests/agent/mailbox/test_agent_mailbox.py rpg_core/tests/agent/runtime/test_agent_lifecycle.py rpg_core/tests/agent/runtime/test_main_model_runtime.py rpg_core/tests/agent/runtime/test_agent_context_service.py rpg_core/tests/agent/runtime/test_agent_tool_service.py rpg_core/tests/agent/turn/test_turn_hooks.py rpg_core/tests/agent/turn/test_turn_runtime_factory.py rpg_core/tests/agent/turn/test_turn_orchestration.py rpg_core/tests/agent/turn/test_turn_transaction.py -q`，并补跑 `uv run python -m pytest agent_service/tests -q`。
- 保留 `pytest.ini` 中的 `asyncio_mode = auto`。
- pytest 默认会清理代理环境变量；需要保留代理时显式设置 `PYTEST_KEEP_PROXY=1`。

## 配置与数据
- 配置按进程/模块拆分：`rpg_core/settings.yaml` 管核心业务配置，`agent_service/settings.yaml` 管 Agent 服务监听、客户端和 Derivation 终态 publisher，`channels/settings.yaml` 管 CLI/Telegram 行为，`play_api/settings.yaml` 管 Play API 监听、事件 Hub 与日志，`dream_service/settings.yaml` 管 Dream 监听、客户端、Map/Reduce 和终态 publisher，`rpg_media/settings.yaml` 管简报与图片 Provider，`media_service/settings.yaml` 管 Media 服务、客户端和 worker，`rpg_tts/settings.yaml` 管正文清洗与分段，`tts_service/settings.yaml` 管 TTS 服务、客户端和 worker。Dream 的 64 条 active 是固定数据层不变量，不得通过部署配置提高。
- Play WebUI 通用配置入口是 `play_webui/play_webui.config.json`，前端通过 typed loader 读取；历史分页配置位于 `session.historyPagination`，正文门禁阈值位于 `session.contextUsage.inputBlockThresholdRatio`。Core 兜底阈值独立配置在 `rpg_core/settings.yaml` 的 `agent.context_window_reject_threshold_ratio`；两者合法范围均为 `(0, 1]`、默认均为 `0.9`，WebUI 非法值回退 `0.9`，Core 非法值必须启动失败。
- `llm_service/settings.yaml` 管 LLM 服务监听、Bearer 鉴权和本地 llama runtime；`llm_service/llm.yaml` 只由 LLM Service 读取，管理 Provider、密钥、模型、上下文窗口、speech 音色和超时等 LLM 强相关配置。
- Dream Map/Reduce 分别只通过 `dream.shallow` / `dream.deep` biz key 调用 LLM；允许在本地忽略的 `llm_service/llm.test.yaml` 中把二者覆盖到当前配置的 `deepseek_v4_flash`，业务代码不得读取 Provider 配置或密钥。
- 它们都支持 `base + profiles`；`local` / `test` / `prod` 是固定 profile 名称，同级 `settings.local.yaml` / `llm.local.yaml` 等覆盖文件会自动加载。
- `llm.yaml` 中 `kind: rerank` 的 biz 配置必须显式声明 `rerank_model_type`，当前允许 `qwen3_logit` 和 `chat_pointwise`。
- `session_id` 只能使用英文字母、数字、下划线，规则为 `^[A-Za-z0-9_]+$`。所有 session 创建入口都由 `rpg_data` 生成 ID；用户只允许指定 title。
- 工作区选择不要写回运行时状态。Telegram/CLI 通过 `channels/settings.yaml` 配置 `workspace_id + story_id`，API/WebUI 通过请求参数或 catalog session 反查上下文。
- `rpg_data` 只通过 `rpg_workspaces.root_path` 定位 workspace 根目录；workspace/story/session 运行目录使用 workspace-relative 路径时，经 `rpg_data.settings.resolve_workspace_relative_path()` 解析并校验不逃逸 workspace。

## 提交规范
- 提交信息使用 `feat:`、`fix:`、`refactor:`、`chore:` 等前缀，后接清晰中文说明。
- 一次提交只处理一个逻辑主题。
- 提交前确认没有误纳入 `data/` 运行文件。
- PR 说明应包含影响模块、行为变化、配置变更、测试结果，以及是否影响现有工作区数据结构。
