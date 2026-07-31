# Repository Guidelines

## 产品与模块边界

- Play WebUI 是沉浸式 RP 的唯一 Web 主体验，Telegram 只承担轻量入口、通知和兜底交互；不要恢复 Dashboard API/WebUI，新增体验型能力优先落到 Play WebUI。
- 修改启动流程、渠道生命周期、共享状态或 `AgentManager` 前先阅读 `CLAUDE.md`。各进程使用独立入口：`run_agent.py` 独占 `AgentManager` / `RPGGameAgent`，`run_dream.py` 独占 `rpg_memory.dream` 编排，`run_llm.py` 独占 Provider 密钥、OpenAI/llama client 和本地 llama runtime；Media、TTS、Play API 与渠道只能通过相应服务客户端访问这些能力。Telegram 可在共址进程内通过 `channels.session_reference` 与窄 `rpg_data` 服务只读查询已提交 Session 资料，但不得因此持有上述业务 runtime。Play API/WebUI 保持自己的富交互契约，不复用该轻量渠道查询层。`run_all.py` 只能编排独立子进程，不得持有或合并业务 runtime。
- `play_api/`、`agent_service/`、`dream_service/`、`media_service/`、`tts_service/` 和 `channels/` 是接入/进程边界；`rpg_core/`、`rpg_memory/`、`rpg_media/`、`rpg_tts/` 是无框架业务模块，`memory_retrieval/` 是业务无关的检索基础包。HTTP、SSE、Telegram、CLI 和前端概念不得进入业务模块。
- Play WebUI 访问 Dream、Media、TTS 和 Agent 能力必须经 Play API 代理；Play API 不直接持有 Agent runtime、LLM Provider 或读取媒体二进制工作区文件。独立服务故障不得阻塞基础聊天加载与输入。
- Dream v1 无入站鉴权，只允许监听 localhost/loopback IP，非 loopback 配置必须启动失败。
- `llm_client` 是 loop-owned 纯异步客户端：所有 API 在创建/首次使用它的同一事件循环中 `await`，不得跨线程/loop 复用 `AsyncClient`，不得以 `asyncio.run()`、同步 HTTP 或 sync-to-async 桥接调用；configure/reset/release 必须 await 关闭旧资源。业务代码不得直接创建 OpenAI/llama 客户端或读取 Provider 密钥。
- 本地 llama 保持 LLM Service 进程内、按不可变模型键由 actor 线程串行执行；不要恢复子进程 worker。`request_timeout_ms` 包含排队和执行，无法中断的 native call 超时后自然排空。
- LLM Service `/health` 免 Bearer 鉴权且只表示进程存活/配置已加载；其它业务接口仍鉴权。`RPG_WORLD_LLM_SERVICE_TOKEN` 与 `RPG_WORLD_PLAY_EVENT_TOKEN` 未设置时仅本地开发可回退内置 token 并 warning，生产必须显式覆盖，内部事件 token 不得暴露给 WebUI。
- 会话链路统一使用全局短 `session_id`；创建时绑定 `workspace_id + story_id`，之后由服务端反查上下文。`AgentManager` 只按 `session_id` 缓存 agent；不要恢复三元 locator、`api_key` 缓存键、`cli_direct` 默认 ID 或用户自定义 session ID 创建入口。
- CLI/Telegram 通过 catalog 解析配置的 `workspace_id + story_id + optional session_id + session_title`；turn、命令、Session mutation 与生命周期能力统一走 Agent service。Telegram 的已提交角色、状态、Summary、Story/Persistent Memory 资料只允许经 `channels.session_reference` 的公共 Reader 读取，工作区选择不得写回共享运行时状态。
- `data/` 是运行数据目录，历史、摘要、索引、SQLite WAL/SHM 和导入运行文件默认不纳入提交。

## `rpg_data` 数据层约束

- `rpg_data` 负责数据如何可靠、高效、原子地存取，不应被窄化为简单 CRUD：数据库连接/migration、Peewee record、typed DTO、复杂关联查询、分页/排序、高效 read model、批量写入、CAS/条件更新、数据库级原子操作、序列化、归属与完整性校验都应留在数据层；业务层不得拼装 SQL 语义或制造 N+1/事务竞争。
- `rpg_data` 不得决定产品行为：不做默认选择、调度/抽样、优先级合并、冷却/重试、状态机下一步、生命周期策略、派生/重置/删除保留矩阵、Prompt/模板渲染、玩家文案或跨聚合业务编排。
- `DataServiceGateway` 是合法的数据库生命周期与 Data Service 注册表；composition root 可从中取得具体 service，但业务 service 必须依赖窄 Protocol/Data Service，不得持有整个 Gateway 作为 service locator。`rpg_core` 仅 `agent/agent.py` 与 `context/factory.py` 可以取得 Gateway，并必须立即把具体 service 逐项注入；`run_telegram.py` 是 Session Reference 只读能力的显式进程组装边界。其它 lookup 与整 Gateway 引用由架构测试显式 allowlist，禁止新增。
- `rpg_data` 的公开类型化持久化边界统一使用 Service 语义；Session、Message、Plot、Narrative Outcome、Dream/Memory、Status、Media 与 TTS 等新的大业务聚合入口命名为 `*DataService`，Repository/Peewee 实现只在 `rpg_data` 内部使用。既有简单 Character/Lorebook CRUD 可保留清晰的 `*ReadService` / `*ManagementService`，不为后缀或形式统一机械增加 application/facade/adapter 样板层。
- `SessionReferenceDataService` 只提供完整 Session/Workspace/Story 归属校验、稳定分页、批量关联、已提交 turn annotation 事实和只读存储模型；轻量渠道的玩家可见字段、资源分组及 Outcome/triggered Plot 投影归 `channels.session_reference`，Persistent Memory Evidence 投影归 `rpg_memory`，具体菜单与卡片归各渠道 owner，禁止进入数据层。
- 业务归属固定：Plot Scheduler 与 Narrative Outcome 在 `rpg_core/rp_modules`，Session/角色/Opening/状态/Scene 在 `rpg_core`，Dream/Story Memory/Persistent Memory 在 `rpg_memory`，媒体与语音分别在 `rpg_media`、`rpg_tts`；service composition root 只负责依赖组装和进程适配。
- 需要跨多次数据操作保持原子性时，由 `rpg_data` 提供无业务语义的 transaction/unit-of-work 或调用方指定的 bulk primitive，业务层决定事务内做什么。业务层不得直接使用 Repository/Peewee record，跨层结果使用 typed contract；Session、Memory、Status、Media、TTS 与 Narrative Outcome 存储契约优先从 `rpg_data.model.*` 引用，`rpg_data.models` 仅保留兼容重导出。
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
- `message_mode` 是无配置、提示词由代码内置的可选 RP Module，集中定义 `neutral | ic | ooc | gm`，空值/default 统一归一化为 `neutral`。Workspace 不保存 mode 或 prompt；非 neutral 模式只有模块在 Story/Session 有效启用时才可用，否则必须在 scratch、LLM 和 history 之前以 `message_mode_unavailable` 拒绝。Fixed Layer 在四种模式间必须字节稳定，模式指令只进入 Hot History 后的 RP Module 动态层；OOC 只讨论剧情/设定而不写世界事实，`neutral | ic | gm` 都属于可推进世界 turn。
- Narrative Outcome 只向 LLM 暴露 `rp_story_outcome(reason, actor?)`；每 turn 最多一个五级结果且重复调用幂等复用。不得向 LLM 暴露 Dice 表达式、DC、权重或随机数；Dice 仅保留手动 `/roll`、`/check_dc` 与解析调试。权重五项均为 `0..100` 且总和严格为 100，`success_with_cost` 必须完整达成原目标。Outcome code/sample/来源一致性由 `NarrativeOutcomeLedgerService` 校验，`NarrativeOutcomeDataService` 只追加调用方准备的 typed ledger row。
- Plot Scheduler 是 Story 级 RP Module。自动 selector 不按每个 `neutral | ic | gm` turn 运行：只有上一个成功提交 turn 的 active Scene document 最终发生实际变化，才原子留下供下一次非 OOC turn 消费的一次调度机会；该 turn 在 `StatusPreflight` 后使用最新 scratch Scene 选择最多一个到期大纲节点和一个池事件。只要事件被任意大纲节点引用，就不参与自动 pool lane，不受大纲/节点启用或 Session 覆盖影响；删除全部引用后才恢复池候选，手动标记仍可绕过。当前成功 turn 若又改变 Scene，则留下供再下一轮使用的新机会；OOC、命令、模块禁用、失败或取消不消费也不创建机会。Scene 时间只接受无“第”字的 `Y 年 M 月 D 日 H 时 [M 分]`。手动 `plot_event_mark_next` 不依赖机会并忽略自动规则。可用池按正整数 `selectionWeight` 和稳定 Session/turn seed 加权抽取，不提供有限轮次保底；`random` 池再按事件 `selectionWeight` 抽主候选，若主候选为 soft，则按池 `candidateBatchSize`（默认 3、范围 1–5）加权无放回补齐 soft batch，并仅调用一次 `agent.plot_scheduler` 从中选择至多一个适宜事件。事件权重只控制 batch 召回，不代表最终注入概率。forced 主候选直接注入；`sequential` 池、大纲 priority、手动注入和既有冷却语义不变。
- `PlotPoolSpec.cooldownMinutes` 是默认 `0` 的非负 SceneTime 分钟。自动 pool lane 中任意事件最新一条已提交 `source_kind=pool + selection_origin=scheduler + decision_status=triggered` 决策通过 `container_id` 为当时所属池建立共享冷却锚点；未到期时整池跳过，当前配置立即作用于已有锚点。manual、outline、`deferred`、`error` 都不启动、刷新或清除池级冷却；手动 `plot_event_mark_next` 继续完全绕过并只可能清除目标事件级冷却锚点。
- Plot 的 `deferred | error` 不阻断主 turn，并按完整可推进世界 turn 间隔重试；实际触发项作为当前 user message 的最终运行时 suffix `[engine_plot_directive]` 注入，位于原始输入和普通 user suffix 之后，只含按序事件标题与 directive，不进入 `RP_MODULES` system layer、SSE、历史、Summary、Memory 或 Dream。该 suffix 可覆盖玩家对世界/NPC 结果的冲突要求，但不得覆盖更高层系统契约、已暂存 Outcome 或实际工具边界；非 GM turn 仍不得代替玩家角色发言、行动、决策或描写心理。`triggered` 只表示已选择并注入，不表示语义验收或剧情完成。大纲节点不重复，池事件按稳定 `event_id` 承载触发/延期/事件级冷却身份，移动池不得重置语义；`container_id` 同时是当时来源快照与池级冷却归属锚点。`/clear` 清决策账本但保留 Session 覆盖，派生只复制分支点前 `triggered` 与覆盖。
- Plot WebUI 使用独立 `/plot-scheduling` 页面，不向 SessionRoom 增加 HUD、轮询或前端 LLM 判断。Story 定义卡展示池冷却和大纲绑定，Session 运行态展示池剩余冷却、跳过原因、锚点与完整决策快照。决策历史按自增 `id DESC` + `beforeId` 分页，公开页最大 200，内部可多取一条判断 `hasMore`。
- `当前场景` 仍以 Story 直属的 `status_kind="scene"` SQL document 为定义真源；Session 使用创建/重置时复制的运行时表。在 Agent 中它是专用高优先级 user prefix，不进入普通 `STATUS_TABLES`，也不用普通 `status_table_set_values` / `status_table_edit_fields`。Scene 的非空 `updateRule` 只进入本轮运行时 Context，不写入历史 snapshot。默认只允许 LLM 修改既有 key，只有显式开启 `agent.scene.allow_runtime_key_changes` 才能增删非锁定 key；`runtimeKeyLocked` 只保护 key 结构，不限制 value 更新。
- 状态 document 固定为 `schemaVersion=2`；每行只允许 `key / value / runtimeKeyLocked / updateRule / metadata`。所有 scene/normal 字段的 value 都由 LLM 在当前 turn 根据已确认事实即时判断更新，不存在字段频率、延迟周期、人工只读或隐藏写权限。空 `updateRule` 使用通用“事实已明确且值实际变化”条件，非空规则是额外语义指导，不产生调度、后台任务或数据库级条件。`neutral | ic | gm` 可在已有 normal Session 表内用 `status_table_set_values` 更新已有 value，并用 `status_table_edit_fields` 创建、改名或删除字段；不得 CRUD 整张表，OOC/命令只读。新字段默认未锁、空 `updateRule`、空 `metadata`；LLM 不得改写这些作者策略。`runtimeKeyLocked=true` 只禁止该字段改名/删除，不妨碍 value 更新或同表新增其他字段。
- 状态表 `description` 集中保存整表共同语义、value 格式和即时更新规则；normal 表允许开放字段时还要定义动态 key 的业务域、命名/value 格式及创建、改名、删除条件，无需预定义全部未来字段。row `updateRule` 只写字段专属条件，不预设 value 是数值。状态表保存需要每轮可见和更新的当前状态；Memory 更适合按时间累积的叙事历史，但当前事实、承诺、联系或事件状态仍可设计为状态字段。
- StatusSubAgent 固定执行 Outcome 判定 → 状态目标路由 → scene/逐表即时更新；表目标包含 `keys + structure`，纯创建允许空 keys，结构目标获得完整表快照和结构工具，value-only 目标只获得所选 rows。每次 LLM 调用只获得一个目标、table/key 双重 allowlist 和实际可用 schema。更新按目标使用内存 checkpoint，单目标失败只回滚该目标并继续；checkpoint 创建/恢复失败终止并 discard 整个 turn。retry/edit/truncate 重抽裁定，但不回滚已提交状态表。
- 状态表 SQL 真源是封装后的 `document_json`，`status_kind` 仅 `scene | normal`；Story 直接拥有状态表定义，Session 创建/重置时复制为 `origin="story_copy"`，现有副本不随 Story 定义修改；`session_native` 独立保存。Story 定义删除后既有 Session 副本保留且来源 FK 置空。并发写入保持 last-write-wins，scratch baseline 偏离只 warning，不改为 CAS 冲突。
- 角色绑定状态表按 `characterName` 分组；Story 表通过 nullable `story_character_id` 最多绑定一个同 Story 角色，一名角色可绑定多张表。Session metadata 使用 `storyStatusSource` 保存来源表、角色 ID 和角色名快照；角色名缺失时可从当前 Story 角色关系修复，无法解析则 warning 并从 LLM Context 排除，不使用“未知角色”共享降级组。角色删除后 Story 状态表绑定 FK 置空。

## Story、Session 与消息

- Catalog 保持 `workspace → stories → sessions`；Character、Lorebook 与 Status 都由 Story 直接拥有，不存在 Workspace 资产库或 Story mount。同名资源可分别存在于不同 Story，但 ID 与 CRUD 必须带 `workspace_id + story_id` 归属校验。`session_id` 规则为 `^[A-Za-z0-9_]+$` 且由系统生成，用户只指定 title。
- Story 的 `summary` 是短摘要，`story_prompt` 是固定提示模板；Opening 真源是 `rpg_story_openings` 中有序的 0–3 条标题＋正文。Story 业务层只允许 `{USER_PLAY_ROLE_NAME}` 模板变量，第一条为缺省 Opening；Story Prompt 每 turn snapshot 只渲染一次。
- 角色卡一级只允许 `name + description`，不恢复 `personality/content`；`description` 只写身份、经历与客观事实，不写会约束玩家扮演的性格、口癖、行为倾向或心理。二级详情的内置客观标签为 `kind:appearance|background|relationship|ability`，演绎标签为 `kind:personality|speech|behavior|psychology`；演绎标签必须自动附加 `scope:npc_portrayal`。
- 玩家角色是 Session 级绑定，对外状态只为 `bound | invalid`。WebUI 空会话使用不可取消的“角色 → 开局”向导，最终通过 Agent `/role_bind <角色序号> [开局序号]` 原子提交；invalid 时普通正文不写历史、不调用 LLM。首次有效绑定且主历史为空时才向 main/backup 追加 Opening，切换角色或普通历史操作不得重放。
- 玩家角色必须进入本轮不可变 snapshot；fixed layer `[player_character]` 是身份唯一真源，角色 metadata 不得承载 PLAYER/NPC 身份。玩家角色的 Fixed Layer 卡片必须排除 `scope:npc_portrayal` 详情；NPC 卡片正常保留，只有当前 GM turn 明确托管时才把被排除的玩家演绎详情动态注入后置 `message_mode` section。切换只影响后续 turn，并刷新共享 Context 资源，不改写历史、摘要或记忆。
- `/clear` 保留 Session 身份/profile、append-only 冷备、角色/Opening、标题、模型和 RP Module 覆盖；清除主历史、Outcome/Plot ledger、Story/Persistent Memory、Dream、Session runtime 和 Session 媒体引用，按当前 Story 状态定义重建 `story_copy` 并清空 native 表值。有效绑定按稳定 Opening ID 重放 turn 1，缺失时回退当前第一条。
- 删除 Session 与 `/clear` 严格区分：Agent service 先隔离 Session、取消 turn、释放资源，再删除 catalog/级联数据、冷备与 runtime；数据库失败恢复隔离目录，提交后目录清理失败返回 `pending`。Play API 只转发删除，WebUI 两个入口都必须确认。
- 持久消息必须有正数 `turn_id`、`seq_in_turn`，主表唯一 `(session_id, turn_id, seq_in_turn)`，冷备 append-only。Summary/Story Memory 进度只使用消息行 `summary_processed` / `story_memory_processed`，不恢复 last-turn 游标；主 Agent Context 仅过滤 `summary_processed=true`，其它历史 API 和 SubAgent 仍读取完整未删除历史。候选分组、保留窗口、编辑重置及 Outcome/Plot 清理矩阵归 `SessionHistory` / `SessionProgress`，`MessageDataService` 不固化这些策略。
- `text_output_format` 是默认 fixed layer 约束，不进入 RP Module；带 `<rp-narration>` / `<rp-character>` 标签的全文是 assistant `content` 真源，原样进入 SSE、历史和数据库，不写解析后的 message metadata。

## Memory 与 Dream

- `memory_retrieval` 只负责业务无关的 chunk、FTS、vector、query plan、Hybrid 融合、rerank、索引协调和存储，不得导入 `rpg_memory`、`rpg_core` 或 `rpg_data`；RP 候选过滤、粒度偏好、上下文查询适配、在线召回编排、Story/Persistent Memory、Dream 与 benchmark 归 `rpg_memory`，依赖方向只能是 `rpg_memory → memory_retrieval`。
- Memory 保持 `SqlVecRetriever`、`KeywordRetriever`、`RawMarkdownRetriever` 三路独立，`HybridRetriever` 只融合。RP 的 `overall.md` 排除和粒度评分通过 `RPRecallCandidatePolicy` 注入，传闻/尝试/承诺语义通过 RP pointwise prompt builder 注入，不得写回通用检索包。配置使用 `keyword_k` / `hybrid_keyword_weight`；`raw_md_mode` 仅 `disabled | always | fallback_only`；rerank 统一使用 `PointwiseMemoryReranker`。
- 每个 Session 的 Memory 操作由同一 async lock 串行，不同 Session 可并发。watchdog 线程只经 `loop.call_soon_threadsafe()` 入队，loop-owned consumer 执行索引与 SQLite 更新，文件/hash/chunk/SQLite 阻塞工作使用 `asyncio.to_thread()`。本地能力初始化不触发远端解析，远端失败保留本地 fallback 并在后续调用重试。
- Dream 只生成 Session 级、长期稳定的世界内事实；OOC、用户偏好、Provider/系统配置和易变 Scene 不进入 Persistent Memory。运行维度固定为 `shallow | deep × incremental | full`，Shallow 只使用来源仍精确有效的 Story Memory/Summary，Deep 以当前主消息表 `neutral | ic | gm` user/assistant 为真源。
- Dream 必须 proposal-first：生成只创建持久 proposal，WebUI 手动刷新且不轮询；用户可编辑 `text / memory_kind / epistemic_status / salience`，不可编辑动作目标与 Evidence。同 Session 最多一条 generating，进程重启将 orphan generating 标为 interrupted，不使用持久 worker 或自动模型重试。
- Dream Proposal/恢复/Apply 与 Persistent Memory 生命周期只归 `rpg_memory.dream`，Story Memory 规范化、exact dedupe、合并、Evidence 和 version 只归 `StoryMemoryApplicationService`；`rpg_data` 仅暴露 `dream_memory` / `story_memory` typed CRUD/CAS/transaction。Apply 由领域层唯一编排 SQLite `IMMEDIATE`，写入前后各重捕获一次来源；第二次确认失败必须回滚 ledger，再独立把仍为 ready 的 Proposal 标为 stale。
- Memory identity 由代码按规范化 `memory_kind + epistemic_status + text` 生成。稳定 Memory ID 指向不可变 revision，Evidence 固定 message ID/version/content hash，生命周期仅 `active | retired | superseded`，每 Session 最多 64 条 active；命中 retired identity 时复用 ID 并新增 revision，active/superseded 冲突拒绝。Persistent Memory 唯一真源是 SQL ledger，Context 只投影 Evidence 仍有效的 active 当前 revision，不读写旧 `persistent_memory.json`。
- Dream Map/Reduce/Proposal 共用有界 LLM 并发与候选硬上限；模型不收敛时确定性裁剪，Full Deep 发生实际截断时不得仅因候选缺席退休事实。Dream repository 在单独 worker 线程内创建/使用/关闭，不能阻塞 service loop。

## Media、TTS 与后台事件

- 生图保持“手动选择 1–20 个连续已提交 turn → 检查/编辑 `VisualBrief` → 异步提交”；来源快照/指纹在提交和重试前校验历史变化。`userPrompt` 只由用户填写，Planner 必须留空；非空内容裁剪后固定作为最终 Provider prompt 的末尾最高语义优先级区块，只能覆盖冲突的画面语义，不得绕过 Provider 安全规则或画幅、尺寸等硬参数。终态 Job 支持原样直接重抽/重试和载入完整 Brief 编辑后重抽/重试；编辑入口不得重新调用 Planner，两者均继承直接来源 Job 的 Provider、turn 范围、来源指纹和 generation params。VisualBrief/userPrompt 只随 Job/Asset 保存；图片、Gallery、背景引用不得写入消息正文、metadata、turn/SSE 或 localStorage。
- 图片二进制存入 `{workspace_root}/assets/images/{sha256}.<ext>`，只接受魔数确认的 PNG/JPEG/WebP；Blob 按 `(workspace_id, sha256)` 去重，但每次成功生成独立 UUID Asset。Media Job 使用持久单 worker 队列、无自动重试；重启保留 queued 并中断遗留 active job。正在作为背景的 Asset 不可删除，最后一个引用删除后才回收 Blob 与文件。
- Media 来源范围、VisualBrief 来源确认、Library metadata、删除门禁、背景选择/评估和 worker 恢复策略归 `MediaApplicationService`；worker 只依赖该业务入口。`MediaDataService` 仅执行 typed CRUD/read model、CAS claim、引用查询、条件转换和调用方准备的原子 completion。
- TTS 只按已提交 assistant `message_id` 派生，正文清洗、分段、指纹和 MP3 缓存归 `rpg_tts`；语音不得进入 Agent turn、正文 SSE、message metadata 或 localStorage，OpenAI Speech 仍通过 LLM Service。
- TTS 消息资格、cache 命中、retry/失效和 worker 中断策略归 `TTSApplicationService`；worker 只依赖该业务入口。`TTSDataService` 仅执行 source read model、typed CRUD、条件 claim/transition、引用查询和调用方准备的原子 completion。
- Dream 与 Derivation 终态通知独立于正文 SSE：领域 worker 在 `ready | failed | interrupted` 落库后通过 typed NotificationSink 通知，publisher 只在 service composition root 注入，发布失败只 warning。Play API 独占单进程 best-effort 事件 Hub，GET job/proposal 仍是真源；WebUI 根 Providers 只建一条 EventSource，通知 UI 不自动轮询、跳转、回写任务或持久化。

## 配置、测试与提交

- 配置按进程/模块拆分并通过 typed accessor 读取；业务代码不得直接解析 YAML key。只有 LLM Service 读取 `llm_service/llm.yaml`；Play WebUI 通过 typed loader 读取 `play_webui/play_webui.config.json`。Workspace 相对路径必须经 `rpg_data.settings.resolve_workspace_relative_path()` 校验不逃逸根目录。
- 跨模块状态值、阶段名和 document 字段名使用集中常量/枚举；固定协作者使用明确类型或 Protocol，不用 `getattr` 和静默 fallback 掩盖接口错误。
- `rpg_data` bootstrap 不硬编码 demo 数据；默认保留 SQL 未索引的 workspace/story/session 目录，只有显式设置 `RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS=true` 才允许清理并记录结果。
- 当前数据库是硬切 Schema：`rpg_data/migrations` 只允许 `0001_initial.sql`、`0002_demo.sql`、`0003_pagination_demo.sql`。Migration ledger 包含其它版本、同版本文件名或 checksum 不一致时必须启动失败；不提供旧数据库升级或旧导入格式兼容。
- 常用入口：`uv sync`；`uv run python -m run_all`；单进程使用对应 `run_agent|run_llm|run_dream|run_media|run_tts|run_play_api|run_cli|run_telegram` 模块；前端使用 `cd play_webui && npm run dev|build`。
- Python 基线：`uv run python -m pytest channels/tests rpg_core/tests rpg_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests rpg_media/tests media_service/tests rpg_tts/tests tts_service/tests dream_service/tests -q`。外部调用默认 mock；真实 Provider 验收必须显式 opt-in，密钥不得进入测试、文档或日志。
- 测试跟随业务 owner：Agent/Context/Session/Plot/Status 改动补 `rpg_core/tests`，Memory/Dream 规则补 `rpg_memory/tests`，数据 CRUD/migration 补 `rpg_data/tests`，服务/代理边界补对应 service 与 Play API 合约测试；Play WebUI 管理能力改动必须运行构建。保留 `pytest.ini` 的 `asyncio_mode = auto`。
- 提交信息使用 `feat:`、`fix:`、`refactor:`、`chore:` 等前缀；一次提交只处理一个逻辑主题。提交前排除 `data/` 运行文件；PR 说明包含影响模块、行为/配置/数据结构变化和测试结果。
