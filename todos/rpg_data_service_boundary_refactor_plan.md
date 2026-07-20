# `rpg_data` Service 业务逻辑拆层整改计划

> 本文是实施顺序与完成记录。长期有效的架构约束以 [`docs/rpg-data-architecture.md`](../docs/rpg-data-architecture.md) 为准。

## 0. 状态与目标

- [x] 首个已完成整改项：Plot Schedule
- [x] 已完成整改项：Session 生命周期、角色绑定与开局
- [x] 已完成整改项：Dream / Persistent Memory / Story Memory
- [x] 已完成阶段性架构收口：Gateway 注册表、聚合 Data Service、窄 Port、类型归属与静态守卫
- [ ] **暂停项：状态表与 Scene（P3，本轮不实施）**
- [ ] 后续整改项：Media 与 TTS
- [ ] 后续整改项：Story Catalog、Composer 与 RP Module 配置
- [ ] 后续整改项：消息、历史和通用账本收尾

本计划用于把 `rpg_data` 收敛为无框架、无业务决策的数据访问模块。整改后，`rpg_data` 负责数据库 DTO、序列化、复杂查询/read model、CRUD、分页、批量、CAS、数据完整性和数据库级原子持久化；业务规则、状态机、默认策略、跨聚合用例和玩家文案必须由对应领域模块或应用编排层持有。

Plot Schedule、Session P1 与 Dream/P2 已按整改执行顺序完成，本轮目标改为复核这些提交并收紧依赖，不继续启动状态表与 Scene P3。这里描述的始终只是架构债务的实施顺序，不代表任何 RP Module 运行时优先级、模块排序、候选仲裁权重或剧情调度优先级。P3 只有在后续明确恢复时才实施，避免为了形式统一继续制造样板层。

## 1. 统一边界

### 1.1 `rpg_data` 允许保留

- Peewee record、migration、数据库 DTO/dataclass 和稳定的存储枚举值。
- 单表或复杂关联表的创建、读取、更新、删除、分页、排序和高效只读投影/read model。
- ID、workspace/story/session 归属、外键、唯一约束、非空、数值范围、JSON/SceneTime 可序列化等数据边界校验。
- 乐观/CAS/条件更新、队列 claim、批量写入、数据库级原子操作、事务和数据库错误到通用数据错误的转换。
- 调用方已经明确给出记录、过滤条件和目标值后的批量插入、复制、删除或状态写入。
- 不改变业务含义的格式规范化，例如字符串去除首尾空白、稳定 JSON 编解码。

### 1.2 必须迁出

- “何时允许执行”“下一状态是什么”“默认选择什么”“失败后如何回退”等产品规则。
- 根据当前故事、回合、角色、记忆或任务状态选择要写入、继承、重试、清理的数据。
- 调度、抽样、优先级合并、冷却、顺序推进、生命周期和派生策略。
- Prompt、模板渲染、玩家提示、命令序号解释和任何渠道/UI 文案。
- Session reset/delete/derive 等跨聚合业务用例及文件系统补偿流程。
- Dream、状态表、媒体、TTS 等领域对象的语义校验和状态机。

### 1.3 目标依赖方向

```text
Play API / Agent service / Domain worker
                |
                v
rpg_core / rp_memory / rpg_media / rpg_tts
                |
                v
 rpg_data aggregate Data Service + query/CAS/transaction
                |
                v
             SQLite
```

- `rpg_data` 不得反向导入 `rpg_core`、`rp_memory`、`rpg_media`、`rpg_tts`、`play_api` 或渠道模块。
- `DataServiceGateway` 保留为数据库生命周期与 Data Service 注册表；composition root 从中取得具体 service 后逐项注入，业务 service 不得持有整个 Gateway。
- 业务层可以依赖 `rpg_data` 的 typed contract 和窄 Data Service/Protocol，但不得直接使用 Repository 或 Peewee record。
- 公开持久化边界统一使用 Service 语义，新的大业务聚合入口命名为 `*DataService`；Repository 只在 `rpg_data` 内部使用，不为简单 CRUD 机械保留无边界价值的 facade/adapter 转发层，也不强制重命名清晰的既有 `*ReadService` / `*ManagementService`。
- 需要跨多次 CRUD 保持原子性时，由 `rpg_data` 提供无业务语义的 transaction/unit-of-work 边界；业务层负责决定事务内执行哪些动作。
- 数据层异常只表达 not found、integrity、conflict、conditional update failed 等数据事实；HTTP error code、玩家文案和领域错误由上层映射。

## 2. 当前首个整改项：Plot Schedule

### 2.1 整改前越界

整改前的 `rpg_data/services/plot_scheduling.py` 同时包含 CRUD 与剧情调度业务：

- 自动分配或重置事件、节点 `position`。
- `allow_repeat` 与 `repeat_cooldown_minutes` 的组合规则。
- 大纲节点按位置排列后，时间必须非递减。
- 重排必须提交当前容器的完整 ID 集合。
- 每个 turn 最多两条调度决策、每种 `source_kind` 最多一条。
- Session 派生要求同 Story，并只复制 `triggered` 决策。
- 删除池、事件时直接抛出剧情定义语义错误。

Plot Repository 原先的 triggered-only 专用复制方法也固化了“派生只继承已触发事件”的业务选择。

### 2.2 目标拆分

- [x] 在 `rpg_core/rp_modules/plot_scheduler` 增加定义管理 application service，统一承接 Pool/Event/Outline/Node 的创建、更新、移动、重排和删除规则。
- [x] 将重复事件配置、时间线非递减、完整重排、默认 position 和删除占用语义迁入该 application service。
- [x] 将 turn 决策批次约束迁入 Plot Scheduler 的 typed policy/model；commit 前由核心层验证，数据层只写入已经准备好的 ledger rows。
- [x] 保持现有 `PlotScheduleSelector`、soft suitability judge 和 runtime 注入逻辑在 `rpg_core`，不把它们下沉到数据层。
- [x] 把现有数据 service 收敛为 Plot definition/read model、Session override 和 decision ledger 的聚合 Data Service；方法名避免携带 `triggered-only`、`derive`、`retry` 等业务意图。
- [x] Repository 提供调用方指定过滤条件的决策查询/复制或 typed bulk insert，不再自行决定复制哪一种状态。
- [x] Play API 的 Plot Schedule 管理路由改调核心 application service；请求/响应 schema 和现有 HTTP 路径保持不变。
- [x] Agent snapshot resolver 继续通过只读 facade 一次取得 Story schedule、Session override 和 ledger；读取接口不得执行调度选择或修正数据。

### 2.3 原子性与调用链

- [x] 定义创建、更新和重排在同一 transaction 内重新读取相关容器，先由核心规则校验，再执行 CRUD，避免校验与写入分离。
- [x] 外键 RESTRICT、唯一键和 CHECK 仍作为最终数据防线；数据层将异常转换为通用 integrity/conflict，核心层再映射成 Plot 领域错误。
- [x] Session derivation 由核心派生用例明确选择 `triggered` 决策和截止 turn，数据层只复制调用方明确给出的记录/条件。
- [x] Session reset 由核心 reset 用例明确调用 decision-ledger clear；`rpg_data` 不自行决定 `/clear` 的保留和删除集合。
- [x] retry/edit/truncate 仍由 Session history 业务流程决定删除范围，ledger 只提供 `delete_for_turn`、`delete_from_turn`、`retain_turns` 等数据操作。

### 2.4 Plot Schedule 测试迁移

- [x] `rpg_core` 单元测试覆盖重复配置、默认位置、跨池移动、完整重排和大纲时间顺序。
- [x] `rpg_core` 单元测试覆盖每 turn 两条 lane 上限、同 lane 去重以及派生只选择已触发决策。
- [x] `rpg_data` 测试只覆盖 CRUD、归属、序列化、分页、外键/唯一约束、批量写入和事务回滚。
- [x] Play API 合约测试确认所有既有路由、响应字段、错误状态和 Session override 行为不变。
- [x] Agent 测试确认强制/软调度、随机/顺序事件池、冷却和动态层注入结果不变。

### 2.5 当前整改项完成标准

- [x] `rpg_data/services/plot_scheduling.py` 中不存在调度策略、继承策略或玩家/HTTP 语义。
- [x] Plot repository 不再按硬编码业务状态复制记录。
- [x] Plot 管理 API 和 Agent runtime 只通过核心 Plot Scheduler 业务入口作出决定。
- [x] Plot 数据写入仍与 turn message、状态表和 Narrative Outcome 共用原有短事务提交边界。
- [x] 相关文档明确 Plot Scheduler 的业务 owner 是 `rpg_core/rp_modules/plot_scheduler`，`rpg_data` 只是数据 owner。

## 3. P1：Session 生命周期、角色绑定与开局

### 3.1 角色绑定与 Opening

- [x] 将绑定有效性、首次绑定、后续切换、Opening 默认项/回退、模板渲染和首消息写入策略迁到 `rpg_core` 的 Session role 领域服务。
- [x] 将 `/role_bind` 序号解析和中文提示移入 Agent command/渠道展示层。
- [x] `rpg_data` 只提供角色挂载查询、Session profile CRUD、Opening CRUD，以及调用方准备好内容后的原子 profile/message 写入。
- [x] 保留“角色与 Story/Session 归属”“Opening ID 存在”等数据完整性校验，不在数据层决定是否属于首次绑定。

### 3.2 Session 创建、派生、重置和删除

- [x] Story/Session 创建时自动挂载哪些 RP Module、复制哪些状态模板，改由 Catalog application service 决定；`rpg_data` 只执行创建和批量复制。
- [x] 将 derivation job 状态机、完整 turn 判定、继承项目、目标标题、目标生命周期推进迁入 `rpg_core.session.derivation`，Agent runtime 只负责目标运行态准备。
- [x] 将 `/clear` 的清理/保留矩阵、状态模板重建和 Opening 重放迁入 Session reset application service。
- [x] 将删除资格、活动任务门禁、runtime 目录隔离/恢复和 pending cleanup 迁入 Agent Session 删除用例。
- [x] 数据层保留 job/session 条件更新、级联删除、批量复制、批量清理和通用事务能力。
- [x] 迁移保持 mailbox 隔离、取消顺序、SQL 原子性及 runtime 目录补偿语义。

## 4. P2：Dream、Persistent Memory 与 Story Memory

详细落地方案见 [`rpg_data_dream_memory_boundary_refactor_plan.md`](./rpg_data_dream_memory_boundary_refactor_plan.md)。本阶段只做现有 Dream / Persistent Memory / Story Memory 的业务归属拆层，不实施 Story Memory v2 新模型或数据库迁移。

- [x] 将 Dream Proposal 状态机、ADD/REVISE/SUPERSEDE/RETIRE、dedupe identity、Evidence 有效性、active 上限、过期检查和恢复规则迁回 `rp_memory.dream`。
- [x] `rpg_data` 只保留 proposal/item/memory/revision/evidence/state ledger 的 typed CRUD、条件更新、事务和只读投影。
- [x] 将 Story Memory 的语义合并规则（salience、source range、metadata、Evidence 替换、version 变化条件）迁到 `rp_memory`；数据层只执行明确的 upsert payload。
- [x] Dream Apply 仍由领域层完成两次指纹确认，并在一个 SQLite `IMMEDIATE` 事务中调用数据 primitives 原子落库。
- [x] 保持 `rpg_data` 不导入 Dream worker、LLM client、NotificationSink 或 WebUI 语义。

## 4.1 P2 后架构收口

- [x] 保留 `DataServiceGateway` 注册表，并将 Session 角色、派生、删除三个薄数据入口聚合为 `SessionDataService`。
- [x] Session、Plot、Dream/Story Memory application service 改为显式窄 Protocol，不再接收 Gateway 或自行调用全局 getter。
- [x] Agent、Dream worker、Context factory 与服务入口负责从 Gateway 取得具体 Data Service 并组装依赖。
- [x] Session 与 Memory 存储契约迁到 `rpg_data.model.session` / `rpg_data.model.memory`，`rpg_data.models` 暂作兼容重导出；Status/Media/TTS 类型留待对应业务整改。
- [x] 增加静态架构测试：禁止 `rpg_data` 反向导入业务模块、Repository/Record 外泄、近期 application service 依赖 Gateway，以及 Gateway lookup allowlist 增长。
- [x] 明确复杂查询、分页、批量、CAS、数据库原子操作和高效 read model 留在数据层，不以缩短文件或消灭全部 service 为整改目标。

## 5. P3：状态表与 Scene（暂停）

- [ ] 将模板复制策略、Session native 表保留/清空策略、名称冲突规则和 deferred 更新推进迁入 `rpg_core/status`。
- [ ] 将 scene 的专用规则、字段频率许可、runtime key 变化和 LLM 可写范围继续保留在 `rpg_core/scene`、StatusSubAgent 和工具层。
- [ ] `rpg_data` 只提供 template/mount/session document CRUD、字段策略存储、调用方准备好 document 后的保存以及 deferred progress ledger CRUD。
- [ ] `list_context_tables` 中角色分组、缺失角色回填和 Context 排除策略拆成数据读取投影与核心 Context policy，避免数据层决定 LLM 能看到什么。
- [ ] 保持 last-write-wins 及偏离 scratch baseline 时 warning 的现有并发语义。

## 6. P4：Media 与 TTS

### 6.1 Media

- [ ] 将来源 turn 连续性、VisualBrief 来源策略、Library metadata 默认值、Asset 删除门禁、背景选择/评估规则迁入 `rpg_media` 与 `media_service` worker。
- [ ] `rpg_data` 只保留 job/blob/asset/gallery/background/evaluation 的 CRUD、CAS claim、去重约束和调用方指定的原子 completion payload。
- [ ] 文件魔数校验、SHA-256、文件落盘和 orphan 清理继续由 Media 领域/服务负责，不进入通用数据层。

### 6.2 TTS

- [ ] 将“只允许已提交 assistant message”、正文清洗、fingerprint、分段、cache 命中和 retry 资格迁入 `rpg_tts`/`tts_service`。
- [ ] `rpg_data` 只保留 job/cache/blob/part CRUD、条件 claim、引用查询和调用方准备好结果后的原子写入。
- [ ] worker shutdown 时选择哪些状态需要 interrupted 由 TTS application service 决定，数据层执行指定的条件批量更新。

## 7. P5：Story Catalog、Composer 与 RP Module 配置

- [x] 将 Story Prompt/Opening 模板白名单、Opening 上限与默认 Opening 规则迁入 Story/Session 领域服务；数据层保留 schema 约束和原始模板 CRUD。
- [x] 将新 Story 默认挂载 RP Module、自动挂载叙事风格和新 Session 初始化状态表的行为迁出 `CatalogService`。
- [ ] 将叙事风格的 `story base < session override` 解析迁入 Session Composer 核心逻辑；数据层只管理 style、mount、base 标记和 override 记录。
- [ ] 将 RP Module 的 `system < story < session` 配置合并、整组字段和有效启用状态解析保持在 `rpg_core/rp_modules`；数据层只管理 catalog/mount/override CRUD。
- [ ] Character 与 Lorebook management 当前以归属校验和 CRUD 为主，优先保持稳定；只迁出后续发现的 Context 选择、默认挂载或展示策略，不为拆层而重写正常 CRUD。

## 8. P6：消息、历史与通用账本收尾

- [ ] 审查 Message/Backup/Story Memory/Narrative Outcome service，区分数据查询分组与 summary、memory、retry、truncate 的业务选择。
- [ ] Message service 保留按 turn/page/processed flag 的查询和批量标记；由 Summary、Memory、Session history 业务层决定候选范围和处理时机。
- [ ] Narrative Outcome ledger 只校验持久字段和唯一 turn，Outcome code、sample、权重来源等规则由 RP Module policy 验证。
- [ ] 清理 `rpg_data` 中面向 HTTP/玩家的错误码和文本，统一由调用方做领域错误与 transport 映射。
- [ ] 为 `rpg_data` 增加依赖边界静态测试，并在 code review checklist 中加入“数据层不得决定业务动作”检查项。

## 9. 每个业务域的实施模板

后续每个优先级都按以下顺序执行，避免边迁边新增第二套真源：

1. [ ] 写出当前业务规则和调用方清单，锁定兼容行为。
2. [ ] 在对应领域包建立 typed policy/application service，并先用现有数据 service 作为适配器。
3. [ ] 把调用方切到新业务入口，确保 API/SSE/worker 合约不变。
4. [ ] 将 `rpg_data` service 收敛为无业务决策的聚合 Data Service，保留必要的复杂查询/read model、CAS、transaction 和 bulk primitive。
5. [ ] 把业务测试迁到领域包，把持久化测试留在 `rpg_data/tests`。
6. [ ] 静态搜索旧方法和越界 import，删除完成迁移的兼容入口。
7. [ ] 更新 `AGENTS.md`、`CLAUDE.md`、`README.md` 中对应业务 owner 和数据边界。

## 10. 全局验收

- [ ] `rpg_data/services` 中没有 Prompt、玩家提示、渠道命令或 HTTP 语义。
- [ ] `rpg_data` 不负责选择默认剧情、角色、Opening、风格、记忆动作、状态迁移或重试策略。
- [ ] 所有跨聚合业务用例在对应核心/领域模块中可被独立单元测试。
- [ ] 所有数据写入仍使用 typed DTO，不把 Peewee record 暴露到业务层。
- [ ] 原有事务、CAS、外键、唯一约束、clear/delete/derive 原子性与失败补偿不退化。
- [ ] Play WebUI、Telegram、CLI、Agent、Dream、Media 和 TTS 的公开协议不因内部拆层改变。
- [ ] 每完成一个业务域即单独提交，不把多个高风险运行链路合并在同一重构提交中。
