# Repository Guidelines

## 工作边界
- 当前产品路线：WebUI 是沉浸式 RP 主体验，Telegram 是轻量入口、推送通知与兜底交互；短期仍保持 Telegram 稳定性，但新增体验型能力优先沉淀到 WebUI。
- Play WebUI 是唯一 Web 主体验，承担玩家游玩、故事管理、角色/世界设定/状态维护、剧情日志、分支回滚与调试入口；不要恢复 Dashboard API/WebUI。
- 修改启动流程、渠道生命周期、共享状态或 `AgentManager` 前，先阅读 `CLAUDE.md`。
- 根目录聚合 supervisor 入口已移除；各进程必须通过独立入口启动。只有 `run_agent.py` 持有 `AgentManager` / `RPGGameAgent` / `rp_memory` / llama lazy worker，其它进程只能通过 `agent_service.client.AgentClient` 访问 Agent 服务。
- 保持 `play_api/`、`channels/` 为接入层，`rpg_core/` 为无框架核心层；不要把 HTTP、Telegram、CLI 细节侵入核心模块。
- Play WebUI 会话内链路只使用全局短 `session_id` 定位；创建 session 时在 `rpg_data` 绑定 `workspace_id + story_id`，之后由 Play API 反查上下文并调用 Agent 服务。不要恢复前端每次传 `workspace + story_id + session_id` 的三元 locator。
- 玩家扮演角色是 session 级绑定，保存在 `rpg_session_profiles.player_character_id` 和 `player_character_snapshot_json`。WebUI 的选择/切换和 CLI/Telegram 文本渠道都必须统一走 Agent 服务的 `/role_bind <序号>` 命令链路；Play API 只能转发到 Agent service 后刷新 summary，不要直接在 Play API/DataManager 中写绑定。
- CLI / Telegram 也必须通过 `rpg_data` catalog 解析会话：配置使用 `workspace_id + story_id + optional session_id + session_title`；未配置 `session_id` 时由 Agent service 创建系统生成 ID 的 session，配置了则只校验并加载既有 session。不要恢复 `workspace` 字段、`cli_direct` 默认 ID 或用户自定义 session ID 创建入口。
- `AgentManager` 只按全局 `session_id` 缓存 agent；`api_key` 不再作为 Agent service schema、AgentClient 参数或缓存键。LLM key/provider 选择只走 `llm_service` 配置。
- `data/` 是运行数据目录。会话历史、摘要、向量索引、SQLite WAL/SHM 等文件默认不纳入提交。

## 常用命令
- `uv sync`：安装后端依赖。
- `uv run python -m run_agent`：启动 Agent 服务（默认 `http://127.0.0.1:8010/agent/v1`）。
- `uv run python -m run_play_api`：启动 Play API。
- `uv run python -m run_cli`：启动 CLI（通过 Agent 服务交互）。
- `uv run python -m run_telegram`：启动 Telegram（通过 Agent 服务交互）。
- `uv run uvicorn play_api.main:app --reload --reload-dir play_api --reload-dir channels --reload-dir rpg_core --reload-dir rp_memory --reload-dir llm_service --host 127.0.0.1 --port 8000`：直接调试 Play API。
- `uv run python -m channels.cli.repl`：启动独立 CLI。
- `uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests -q`：运行 Python 测试基线。
- `uv run python -m pytest channels/tests/test_telegram.py -q`：专项验证 Telegram。
- `cd play_webui && npm run dev`：启动 Play 前端开发服务器。
- `cd play_webui && npm run build`：构建 Play 前端产物。

## 代码规范
- Python 使用 4 空格缩进，模块/函数用 `snake_case`，类用 `PascalCase`。
- Play WebUI 使用 Next.js App Router + React + TypeScript；React 组件用 `PascalCase.tsx`，hook/composable 用 `useXxx`，前端状态 store 用清晰的 camelCase 命名。
- 新增注释只解释非直观逻辑，避免复述代码。
- 配置访问必须走封装：`settings.memory_settings`、`settings.agent_model`、`channels.config.settings`、`resolve_biz_config()`、`get_runtime_config()` 或 `LLMManager`。
- 业务代码不要直接解析 YAML key，不要直接 new OpenAI/llama 客户端。
- 跨模块重复使用的业务状态值、阶段名和 document 字段名不得散落为 magic string；优先复用集中常量或枚举。跨层返回结果优先使用 dataclass/类型化模型，不用约定字符串 key 的裸 dict 传递。
- `getattr`、反射式能力探测只用于真实动态扩展或外部兼容边界，并应注明理由；仓库内固定协作者必须声明具体类型或 Protocol，并直接调用其公开 API，不保留静默 fallback。

## 架构约束
- 记忆检索保持 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三路独立；`HybridRetriever` 只负责组装与融合。
- keyword 配置使用 `keyword_k` / `hybrid_keyword_weight`，不要恢复 `bigram_k` 或 `hybrid_bigram_weight`。
- `memory.raw_md_mode` 语义保持：`disabled` 关闭，`always` 主召回，`fallback_only` 仅在主召回不足或失败时补候选。
- memory rerank 使用统一的 `PointwiseMemoryReranker`，不要恢复旧的 provider-specific reranker/factory。
- 上下文主流程保持结构化，最终发送给 LLM 前由 `ContextRenderer` 渲染；调试 markdown/token 概览放在 `ContextInspector`，不要回流到 `RPGContext` 数据模型。`verbose_logging` 开启时应记录 RP Module runtime section 的 metadata 与公开 content；模块内部诊断日志允许记录 sample、权重和来源，但不得把这些内部随机细节写入 LLM Context、工具公开结果或玩家界面。
- SessionRoom context 圆环始终只使用 `context-preview` 的下一轮主 Agent Context 估算；正常 `/turn` 或 `/stream` 完成事件的 provider usage 只展示在对应回复气泡和圆环展开详情中，不得覆盖圆环或参与下一轮门禁。不要新增独立 usage 获取接口、持久化 usage 或写 localStorage；比例、阈值和 K/M 展示由 Play WebUI 计算。
- 主 Agent LLM 选择保持 `config default < story override < session override`，只允许 `agent.main.provider_option_keys` 白名单；Story 详情页配置 story 默认，SessionRoom 配置 session 覆盖，`null` 清除当前层覆盖。生成中切换不取消当前 turn，从下一 turn 生效，不得因切换自动压缩。
- `当前场景` 在数据层仍是必须挂载到 story 的 `status_kind="scene"` 状态表，但在 Agent 编排中是专用实时状态：主 Context 只作为高优先级 user prefix，不进入普通 `STATUS_TABLES`；Outcome/Route 阶段可读取并选择 scene，命中后只获得 scene context 和专用 scene 工具。scene 字段固定 `realtime`，不得配置或进入 `event_driven` / `deferred` / `manual`，也不得使用 `status_table_set_values`。`agent.scene.allow_runtime_key_changes` 默认 `false`：LLM 与普通表一样只能修改已有 key 的 value，不能增删或重命名 key；此时 `scene_attr` 只枚举已有 key，`scene_time` 仅在已有 `时间` key 时注册，永不注册 `scene_del_attr`，空 scene 不暴露 scene 工具。只有显式开启时才保留新增非锁定 key、删除非锁定 key 和 `MAX_ATTRS` 上限行为；管理 API/Data 层手工 CRUD 不受该开关影响。
- RP Modules 是 RP 业务模块占位，不是通用 skill 体系；骰子、战斗、物品等能力应围绕 RP 工具流程和受控状态读写设计。
- RP Module 只动态选择仓库内置 Python 定义，不加载第三方代码。`rpg_rp_module_catalog` 是内置模块目录；Story 挂载决定能力上限，Session 只能在 Story 已挂载模块内覆盖启用状态和稀疏配置。新 Story 自动挂载 catalog 中当前标记为默认的全部模块，未来新增模块只自动进入之后创建的 Story。配置按 `system < story < session` 逐字段合并，Narrative Outcome 的 `weights` 作为不可拆分整组。Agent 必须在 Context 门禁前解析不可变 `RPModuleSelectionSnapshot`，并让门禁、StatusSubAgent 和主 Agent 共用该快照的 turn-local runtime；不要把动态选择写回共享 Registry。
- Narrative Outcome 是当前剧情分支随机机制：主 Agent 与 `StatusSubAgent` 只暴露高层工具 `rp_story_outcome(reason, actor?)`，每 turn 最多暂存一条五级结果且重复调用幂等复用；`reason` 是本次裁定不可缩小的整体目标边界，`success_with_cost` 必须完整达成该目标，代价不得抵消成功。不得把低层 Dice 表达式、DC、权重或随机数重新暴露给 LLM。Dice 只保留 `/roll`、`/check_dc` 与表达式解析调试能力。有效权重按 `config < story < session` 形成 turn 快照，五项必须为 `0..100` 整数且总和严格等于 100。
- `text_output_format` 是默认启用的 fixed layer 输出格式约束，不进入 `RPModuleRegistry`，用 `<rp-narration>` 和 `<rp-character name="...">` 约束 assistant 正文。带标签全文是 assistant `content` 真源，必须原样进入 SSE、历史和数据库；不要把旁白/角色分段写入 message metadata，也不要恢复 `metadata.messageDisplay`。
- `rpg_data` catalog 模型保持：workspace -> stories -> sessions；`rpg_story_characters` / `rpg_story_lorebook_entries` 是 story 挂载表，允许同一角色卡或世界书条目挂载到多个 story，只禁止同一 story 重复挂载。
- Story 主数据字段保持：`summary` 是短摘要，`first_message` 是会话开场首条消息模板，`story_prompt` 是 story 专属固定系统提示词。两类模板当前只允许 `{USER_PLAY_ROLE_NAME}` 白名单变量，存储/API 返回原始模板；未知变量必须在 API 和数据层保存边界拒绝。首消息只在首次成功绑定且 main history 为空时按绑定角色渲染并写入 main/backup，Story Prompt 在 turn snapshot 中渲染一次并供本轮 Context 共用。
- 玩家角色绑定状态只对外暴露 `bound | invalid`。缺失绑定、角色不存在、未挂载、snapshot 损坏或 snapshot mount/story 不匹配都视为 `invalid`；WebUI 进入 SessionRoom 后用不可取消弹窗补选，Agent 在普通 send/send_stream 进入 LLM 前强校验，invalid 时只返回固定编号角色列表，不写 user history、不调用 LLM。首次成功绑定且 main history 为空时，`SessionRoleService` 追加渲染后的 story `first_message` 到 main 和 backup，后续切换或清空历史都不得重新追加。
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
- Play API 会话内接口集中在 `/play-api/v1/sessions/{session_id}/history|history-page|scene|commands|turn|stream|stop|player-character`；workspace、characters、lorebook、status-tables、ops 等管理接口也归 Play API；旧 `chat.py`、`scene.py`、`commands.py` router 仅作占位，不要把它们恢复为主入口。

## 测试要求
- 所有外部调用使用 mock，避免真实 LLM、Telegram 或网络依赖。
- 新增测试文件命名为 `test_<feature>.py`。
- 修改 Telegram 适配、会话流程或渲染逻辑时，必须补 `channels/tests/test_telegram.py`。
- 修改 API/Play WebUI 管理能力时，补 `play_api/tests/` 契约测试。
- 修改核心上下文、summary、session 行为时，补 `rpg_core/tests/`；修改 memory 行为时，补 `rp_memory/tests/`。
- 修改主 agent、LLM provider、session manager、context 或相关配置时，默认跑：
  `INTEGRATION_TEST=1 uv run python -m pytest rpg_core/tests/integration -q`。
- 修改 Agent 组合、`rpg_core/agent/turn/`、transaction 或同步/流式编排时，至少先跑：
  `uv run python -m pytest rpg_core/tests/test_agent.py rpg_core/tests/test_agent_mailbox.py rpg_core/tests/test_agent_lifecycle.py rpg_core/tests/test_main_model_runtime.py rpg_core/tests/test_agent_context_service.py rpg_core/tests/test_agent_tool_service.py rpg_core/tests/test_turn_hooks.py rpg_core/tests/test_turn_runtime_factory.py rpg_core/tests/test_turn_orchestration.py rpg_core/tests/test_turn_transaction.py -q`，并补跑 `uv run python -m pytest agent_service/tests -q`。
- 保留 `pytest.ini` 中的 `asyncio_mode = auto`。
- pytest 默认会清理代理环境变量；需要保留代理时显式设置 `PYTEST_KEEP_PROXY=1`。

## 配置与数据
- 配置按进程/模块拆分：`rpg_core/settings.yaml` 管核心业务配置，`agent_service/settings.yaml` 管 Agent 服务监听与客户端默认值，`channels/settings.yaml` 管 CLI/Telegram 行为，`play_api/settings.yaml` 管 Play API 监听与日志。
- Play WebUI 通用配置入口是 `play_webui/play_webui.config.json`，前端通过 typed loader 读取；历史分页配置位于 `session.historyPagination`，正文门禁阈值位于 `session.contextUsage.inputBlockThresholdRatio`。Core 兜底阈值独立配置在 `rpg_core/settings.yaml` 的 `agent.context_window_reject_threshold_ratio`；两者合法范围均为 `(0, 1]`、默认均为 `0.9`，WebUI 非法值回退 `0.9`，Core 非法值必须启动失败。
- `llm_service/llm.yaml` 管 LLM provider、模型、上下文窗口和超时等 LLM 强相关配置。
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
