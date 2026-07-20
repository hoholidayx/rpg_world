# `rpg_data` Dream / Persistent Memory / Story Memory 边界重构落地计划

> 本文是 P2 实施记录。长期有效的架构约束以 [`docs/rpg-data-architecture.md`](../docs/rpg-data-architecture.md) 为准。

## 0. 状态、顺序与范围

- [x] P2 已完成实现与验证；本文件是 [`rpg_data_service_boundary_refactor_plan.md`](./rpg_data_service_boundary_refactor_plan.md) 的已落地模块记录。
- [x] 前置整改 Plot Schedule 已提交：`ae37bf4`。
- [x] 前置整改 Session 生命周期、角色绑定与开局已提交：`25b6f30`。
- [x] 本模块完成时曾把状态表与 Scene 列为下一项；P2 后架构复核已将 P3 改为暂停，不在本轮实施。

本轮把 Dream Proposal、Persistent Memory 账本和现有 Story Memory 视为一个耦合业务域处理：Dream 的 Shallow 来源直接消费 Story Memory，Apply 又会更新 Story Memory 的 Dream checkpoint，因此不能只迁移其中一半后长期保留双重业务入口。

本轮是边界重构，不是 [`agentic_memory_story_memory_v2_plan.md`](./agentic_memory_story_memory_v2_plan.md) 的功能实现。除非拆层发现现有约束无法表达，否则不新增 migration，不改变 Story Memory 数据模型、去重语义、Dream HTTP API、Play API、通知事件、Context 输出或 WebUI。

## 1. 目标与非目标

### 1.1 目标

- [x] `rp_memory.dream` 成为 Proposal 状态机、来源身份、Apply/Restore 策略和 Persistent Memory 生命周期的唯一业务 owner。
- [x] `rp_memory` 的 Story Memory application service 成为候选规范化、语义去重、Evidence 选择、合并和版本推进的唯一业务 owner。
- [x] `rpg_data` 只保留 proposal/item/evidence/state/memory/revision/story-memory 行的 typed CRUD、条件更新、显式批量写入、只读投影和事务边界。
- [x] `dream_service` 只保留 HTTP/process composition、单线程 repository worker、LLM task 生命周期、通知发布和领域错误到 transport 的映射。
- [x] 主 Agent Persistent Memory Context 继续只投影 Evidence 有效的 active 当前 revision，并保留旧快照 fallback。
- [x] 所有跨层协作者使用具体类型或 Protocol；不新增 `Any`、反射式 fallback、裸字符串状态机或约定字符串 key 的裸 dict 结果。

### 1.2 非目标

- [x] 不实现 MemoryEntry、Entity、Thread、Link、Episode 或新的 Story Memory v2 表。
- [x] 不改变当前 `(session_id, dedupe_key)` 唯一约束、Story Memory exact-upsert 行为或 Persistent Memory revision 模型。
- [x] 不改变 `shallow | deep` × `incremental | full` 的选择和 Map/Reduce/Proposal LLM 流程。
- [x] 不改变 Dream proposal-first、人工编辑/选择后 Apply 的产品流程。
- [x] 不把 Dream 任务改成持久 worker，不增加自动模型重试、轮询、outbox 或通知补发。
- [x] 不让 `rp_memory`、`dream_service` 或 `rpg_data` 直接持有 LLM Provider；模型调用继续只经 `llm_client`。
- [x] 不顺带整改 Summary、Message、Session Reset、Media、TTS 或 Story Memory v2 的其它架构债务。

## 2. 当前越界审计

### 2.1 `rpg_data/services/dream_memory.py`

当前约 1950 行的 service 同时承担数据访问和以下业务规则：

- Proposal 创建前比较 history fingerprint、决定同 Session 只能存在一个 generating，并把数据冲突翻译成 Dream 业务冲突。
- 决定 `generating -> ready | failed | interrupted`、`ready -> applied | rejected | stale`，以及各终态时间和错误码。
- 规范化 ADD / REVISE / SUPERSEDE / RETIRE，决定 Evidence 必需性、目标 revision、dedupe identity 和可编辑字段。
- 限制 proposal item 数、单项 Evidence 数、文本长度、salience，并校验 selected item 的目标和新 identity 唯一性。
- Apply 时判断 history/source/ledger/Story Memory 是否 stale，验证 Evidence，投影 active 数量并执行四种动作。
- 决定 retired ADD 命中时复用 Memory ID 并追加 revision，active/superseded 冲突时拒绝。
- 决定 restore 只允许 retired、必须 Evidence 有效、不能超过 active 上限，并推进 ledger revision。
- 计算 history/Story Memory fingerprint，判断 Evidence 有效性，选择 Context 可见的 active memory 并按 kind 排序。
- 在 Apply 成功后推进 manifest、ledger revision、Story Memory `dream_processed` 和 Proposal 终态。

这些内容全部迁入 `rp_memory.dream`；数据层只执行调用方明确给出的行读写和条件更新。

### 2.2 `rpg_data/services/story_memory.py`

当前 service 越界承担：

- Story Memory kind/status/salience/source range/default 值的语义校验。
- 基于 kind + text 生成 dedupe key，并按 exact key 决定创建或合并。
- 合并时选择最大 salience、Evidence 存在时替换 source range、无 Evidence 时扩展 source range。
- 合并 metadata、OR `dream_processed`、计算 semantic signature 并决定是否推进 version。
- 从消息批次选择 Evidence、校验 IC/GM user/assistant、替换旧 Evidence，并与 `story_memory_processed` 原子提交。
- 把持久 DTO 转成 Context dict。

上述规则迁入 `rp_memory` Story Memory application/policy；数据层保留分页、按条件查询、显式 create/update、Evidence replace、message progress 更新和事务。

### 2.3 `rpg_data/services/dream_source_identity.py`

该文件是纯业务来源身份算法：决定哪些角色/mode 可以作为 Evidence、哪些失效 Evidence 被忽略，以及如何生成 Story Memory derived-source fingerprint。整体迁入 `rp_memory/dream/source_identity.py`，删除 `rpg_data` 入口。

### 2.4 其它需要同步收口的调用方

- `dream_service/repository.py`：目前直接组合数据 service、业务错误和 `database.atomic("IMMEDIATE")`；目标是薄适配器，不再直接使用 Peewee database。
- `dream_service/runtime.py`：保留 task/cancel/retry/notification 机制，但恢复分支和状态判断改用 `rp_memory.dream` 的 typed recovery policy。
- `dream_service/main.py`：改为映射 `rp_memory.dream.errors`，公开 HTTP 状态和 error code 不变。
- `rp_memory/persist_memory.py`：改读领域 Context projection，不再直接让 `rpg_data` 决定 Evidence/active/排序策略。
- `rp_memory/story_memory.py`：保留 `StoryMemoryStore` 兼容表面，但委托新的 application service，不再把 dict 直接传入 data service。
- `play_api/backends/data_manager.py`：Story Memory 分页经领域 read facade；返回结构不变。
- `rpg_core/session/reset.py`：仍由 Session Reset 决定清理矩阵，只调用 business-neutral 的 Dream/Story Memory session-row clear primitive。

## 3. 必须冻结的兼容行为

### 3.1 Proposal 生命周期

| 当前状态 | 允许迁移 | 触发者 |
| --- | --- | --- |
| `generating` | `ready` | 模型生成成功且 items 合法 |
| `generating` | `failed` | 生成或模型契约失败 |
| `generating` | `interrupted` | 进程启动/停止、恢复 orphan 或终态持久化兜底 |
| `ready` | `applied` | 两次来源确认和全部 Apply 门禁通过 |
| `ready` | `rejected` | 用户明确拒绝 |
| `ready` | `stale` | history/source/ledger/Story Memory/Evidence/目标 revision 已变化 |
| 任一终态 | 无 | 终态不可再次迁移 |

- [x] SQL partial unique index 继续作为“每 Session 最多一个 generating”的最终防线。
- [x] Core policy 先判断合法迁移，数据层用 expected status/version 条件更新防并发覆盖。
- [x] `ready | failed | interrupted` 成功落库后仍由 Dream service 发布 best-effort 通知；通知失败不得改变终态。

### 3.2 Persistent Memory 动作语义

| 动作 | 固定语义 |
| --- | --- |
| ADD | 无 target，必须有 Fact/Evidence；新 identity 创建新 Memory；命中 retired identity 时复用原 Memory ID、追加 revision 并恢复 active |
| REVISE | target 必须 active 且 base revision 匹配；追加不可变 revision，Memory ID 和原 dedupe key 不变 |
| SUPERSEDE | target 必须 active；创建新 identity/Memory/revision，把旧 Memory 标为 superseded 并记录新 ID |
| RETIRE | target 必须 active；不要求新增 Evidence，只把 lifecycle 改为 retired |

- [x] 每个 selected proposal 最多对一个 target 执行一个动作。
- [x] ADD/SUPERSEDE 的新 dedupe key 在 proposal 内唯一，并服从 Session 跨 lifecycle 唯一约束。
- [x] active/superseded identity 冲突继续拒绝；只有 ADD 命中 retired 才允许 revive。
- [x] Apply/Restore 后 active 数不得超过 64；上限由领域配置/常量决定，SQL 只保证行完整性。
- [x] 每次成功 Apply 或 Restore 只推进一次 Session ledger revision。

### 3.3 Evidence、来源与 Context

- [x] Evidence 必须精确匹配当前主消息的 Session、message ID、turn、version、content hash，并且角色为 user/assistant、mode 为 IC/GM。
- [x] Shallow 只使用仍有有效 Evidence 的 Story Memory，以及来源消息仍完整属于原 batch 的 Summary；Deep 仍以当前主消息表中的 IC/GM user/assistant 为事实真源。
- [x] Shallow/Deep 与 incremental/full 的 manifests 继续相互独立；checkpoint 变化本身不改变 derived-source fingerprint。
- [x] source fingerprint 继续覆盖 Story Memory、Summary Batch 和玩家角色 fingerprint，角色切换后旧 Proposal 必须失效。
- [x] Apply 前继续检查 proposal 捕获的 history/source/ledger/Story Memory identity。
- [x] Context 只返回 lifecycle=active、current revision 存在、Evidence 非空且全部有效的 Memory。
- [x] Context 排序保持当前 kind 顺序后按稳定 Memory ID；读取失败继续由 `PersistentMemoryStore` 返回旧快照。

### 3.4 Story Memory exact-upsert

- [x] 保持现有 kind + 规范化 text 的 exact dedupe identity，不引入 Story Memory v2 的 capture key。
- [x] 新 key 创建新行；旧 key 命中时按现有规则合并 text/kind/status、最大 salience、metadata 和 Dream checkpoint。
- [x] 带 Evidence 的 capture 使用当前 Evidence 的精确 turn range并替换旧 Evidence；不带 Evidence 的管理写入扩展旧 source range。
- [x] 只有 semantic signature 发生变化才推进 Story Memory version；单独改变 `dream_processed` 不改变 Dream derived-source identity。
- [x] fact/Evidence/message `story_memory_processed` 必须在同一事务内成功或回滚。

## 4. 目标依赖与代码布局

```text
Dream HTTP / DreamTaskManager / Agent / Play API
                         |
                         v
        rp_memory.dream + StoryMemoryApplicationService
             |                    |
             | typed policies     | typed capture/merge plan
             v                    v
      DreamMemoryDataService  StoryMemoryDataService
                         |
                         v
                rpg_data repositories / SQLite
```

### 4.1 `rp_memory` 目标文件

- [x] `rp_memory/dream/types.py`
  - 增加 `DreamProposalStatus`、`PersistentMemoryLifecycle`、`DreamFailureCode`、Memory kind/status 枚举和 Apply command/result 类型。
  - 继续保留现有 depth/scope/action/source/selection/generation 类型。
- [x] `rp_memory/dream/errors.py`
  - 承接 conflict、invalid-state、stale、Evidence invalid、active-limit、conditional-write conflict 等领域错误。
- [x] `rp_memory/dream/source_identity.py`
  - 接管 Story Memory Evidence identity、history/source fingerprint 和 Evidence match 的纯函数。
- [x] `rp_memory/dream/proposal.py`
  - 负责状态迁移、item normalize/patch、target/new-key 唯一性和 recovery decision。
- [x] `rp_memory/dream/ledger.py`
  - 负责 Evidence validity 与 Context projection；四类动作、active 数投影和 revive/restore 由 application service 统一编排。
- [x] `rp_memory/dream/application.py`
  - 组合 proposal、ledger、source provider 与数据端口，提供 Dream service 使用的同步 application facade，并唯一持有 Apply 的 IMMEDIATE 编排。
- [x] `rp_memory/story_memory_service.py`
  - 定义 typed candidate/write/result，负责 capture、exact-upsert merge、Evidence 和 Context projection。
- [x] `rp_memory/story_memory.py`
  - 保留现有 `StoryMemoryStore` 导入路径，改为委托 `StoryMemoryApplicationService`。

现有 `engine.py`、`source.py`、`model.py` 的 LLM 选择与 Map/Reduce 逻辑不在本次重写范围；只统一它们使用的 enum/常量来源。

### 4.2 `rpg_data` 目标文件

- [x] `rpg_data/repositories/dream_memory_repo.py`：proposal/item/evidence/state/memory/revision 的 record CRUD 和条件更新。
- [x] `rpg_data/repositories/story_memory_repo.py`：Story Memory/Evidence 的行 CRUD、分页和批量读取。
- [x] `rpg_data/services/dream_memory.py` 收缩并改名为 `DreamMemoryDataService`。
- [x] `rpg_data/services/story_memory.py` 收缩并改名为 `StoryMemoryDataService`。
- [x] `DataServiceGateway` 暴露明确的 `dream_memory`、`story_memory`，迁移完成后删除旧业务语义属性或兼容 alias。
- [x] 增加 business-neutral 的 typed transaction mode，例如 `DataTransactionMode.DEFERRED | IMMEDIATE`；生产调用方不得再直接访问 `gateway.database.atomic("IMMEDIATE")`。

数据层允许保留：

- record 到 frozen data DTO 的转换和 JSON 编解码。
- Session/Proposal/Memory/Story Memory 归属、正数 ID、SHA-256 长度、外键和唯一约束检查。
- 调用方指定 expected status/version/lifecycle 后的条件更新。
- 调用方给出完整 insert/update/delete payload 后的短事务或 bulk primitive。
- proposal/item/evidence、memory/revision/evidence、state/manifest 和分页 read model。

数据层不得保留：

- 合法状态迁移表、错误码选择、默认失败原因。
- action、revive、supersede、retire、restore 或 active-limit 语义。
- dedupe identity 生成、Evidence 是否足以成为事实、source fingerprint 和 Context 可见性。
- Story Memory 合并、salience 选择、metadata 合并、source range 策略和 version 推进决策。

## 5. 类型化边界设计

### 5.1 领域类型

- [x] `DreamProposalStatus`、`DreamProposalAction`、`PersistentMemoryLifecycle` 全部使用 `StrEnum`，业务代码不比较裸字符串。
- [x] `DreamFact` 使用 typed kind/status，identity 永远由 `dream_fact_identity_key()` 生成，不信任模型或 API 的 dedupe key。
- [x] Apply sequencing 只存在于 `DreamApplicationService`，按 typed memory/revision/state/proposal DTO 调用 data port；数据层只把 action 当作持久字段读写，不解释 action 或包含动作分支。
- [x] `StoryMemoryCandidate`、`StoryMemoryContextItem` 与内部 parsed candidate 使用 frozen dataclass，最终持久值使用 typed row DTO；application service 不返回约定字符串 key 的裸 dict。
- [x] JSON/HTTP/LLM 边界可以接收 `Mapping[str, object]`，进入领域服务后必须立即解析成 typed value。

### 5.2 数据 DTO 与条件写入

- [x] `rpg_data.models` 只保留持久化 read/write DTO；移除 `SessionStoryMemory.to_context_dict()`、`PersistentMemoryBundle.fact` 等业务投影 helper。
- [x] Proposal transition 接口至少接收 `proposal_id + expected_status + expected_version + explicit update`，返回更新后的 DTO 或 conditional-write-failed。
- [x] Memory update 接口接收全局稳定 `memory_id + expected_version + explicit fields`；领域层在同一 IMMEDIATE 事务内验证 Session、lifecycle 和 current revision。
- [x] Story Memory update 由 Core 给出最终字段、最终 version 和 Evidence replacement；data service 不再自行 merge。
- [x] 数据异常只表达 not-found、integrity/conflict/conditional-update-failed；Dream 错误由 `rp_memory.dream` 映射。

### 5.3 固定协作者 Protocol

- [x] `DreamDataPort`：Dream CRUD、条件更新和事务内显式写入。
- [x] `StoryMemoryDataPort`：Story Memory/message Evidence 读写和 capture progress。
- [x] `DreamSourceSnapshotProvider`：在 repository worker 所在线程捕获消息、Story Memory、Summary、玩家角色和 ledger 快照。
- [x] application service 直接调用 Protocol 方法；不得使用 `getattr`、`hasattr`、回调私有方法或静默 capability fallback。

## 6. Story Memory 拆层流程

### 6.1 Capture / add

1. [x] Application service 先把 extractor/API 输入解析为 `StoryMemoryCandidate`，完成 kind/status/text/salience/metadata/source range 校验。
2. [x] 进入同一个 data transaction 后读取调用方给出的 source message IDs，生成不可变 Evidence，并确认全部属于当前 Session 与当前 capture batch。
3. [x] 根据 Evidence 精确修正 source range，按当前 exact identity 查询既有 Story Memory。
4. [x] Core 生成最终 typed row values；合并规则严格保持第 3.4 节行为。
5. [x] Data service 执行明确的 row create/update 和 Evidence replace。
6. [x] 同一事务最后按调用方给出的 message IDs 标记 `story_memory_processed`；任一步失败全部回滚。

### 6.2 Replace / management write

- [x] `set_details` 在清空前先完整解析全部候选，任一非法时不改变旧数据。
- [x] Core 决定 replace-all；data service 接收准备好的 rows/evidence 并原子替换。
- [x] Play API 的只读分页仍由 SQL 完成过滤/排序/统计，kind 等业务枚举由领域 facade 验证。
- [x] Context dict/metadata 解码移到 `StoryMemoryStore` 或领域 projection。

### 6.3 Dream checkpoint

- [x] `dream_processed` 仍是当前 schema 的消费者 checkpoint，不参与 Story Memory source identity。
- [x] Dream Apply 由领域 application service 明确给出需要推进的 Story Memory IDs；data service 只执行带 Session 归属条件的批量更新。
- [x] 单独 checkpoint 更新不推进 Story Memory version。

## 7. Dream Proposal 与 Persistent Memory 拆层流程

### 7.1 Proposal 创建与生成终态

1. [x] Source provider 捕获不可变 `DreamSourceSnapshot`，`DreamEngine.prepare()` 选择来源。
2. [x] Proposal service 校验 depth/scope/fingerprint/manifest 与 proposal ID，生成 typed create command。
3. [x] Data service 插入 generating row；partial unique 冲突返回通用 data conflict，Core 映射为 `DreamProposalConflictError`。
4. [x] 模型生成在事务外执行。
5. [x] ready/failed/interrupted 由 Core 校验 expected generating 后生成完整 item/terminal update，data service 条件提交。

### 7.2 用户编辑与拒绝

- [x] Patch 只允许 `selected/text/memory_kind/epistemic_status/salience`；Evidence、action、target 和动作目标不可编辑。
- [x] ADD/SUPERSEDE 内容变化后由 Core 重算 identity。
- [x] Patch 全批 item ID 唯一，且必须属于该 ready proposal。
- [x] Core 在写入前重新验证 selected target/new identity 唯一性；data service 只保存最终 item 字段。
- [x] Reject 只允许 ready -> rejected，并使用 expected status/version 条件更新。

### 7.3 Apply 的 IMMEDIATE 原子流程

Apply 必须由 `rp_memory.dream.application` 唯一编排：

1. [x] 进入 `DataTransactionMode.IMMEDIATE`，读取 ready Proposal、selected items、当前 ledger/state 和来源数据。
2. [x] 在事务内执行第一次完整重捕获，比较 proposal 保存的 history fingerprint、derived source fingerprint、ledger revision 和 Story Memory source identity。
3. [x] 验证每条非 RETIRE Evidence、target Session/lifecycle/base revision、selected target 唯一性、新 identity 唯一性和 active 上限。
4. [x] Core application service 唯一持有 action 分支，并依次用 typed CRUD/CAS 执行 inserts、revisions、conditional updates、state/manifest、Story Memory checkpoint 和 proposal applied update；Data service 不解释 action。
5. [x] 在提交前执行第二次来源重捕获，确认 history/source 未在 Apply 窗口内变化；ledger revision 由同一事务中的 state CAS 保护。
6. [x] 第二次确认失败时回滚整次成功写入；随后用独立条件事务把仍为 ready 的 Proposal 标为 stale。
7. [x] 第一次门禁已失败时，在同一 IMMEDIATE 事务内只提交 stale 终态，不写 ledger；退出事务后抛出稳定领域错误。
8. [x] 任何 LLM、HTTP、通知或文件写入不得发生在 Apply 数据事务中；Summary 文件只读快照由第二次 fingerprint 捕获保护。

### 7.4 Restore 与 Context projection

- [x] Restore 由 Core 验证 Session 归属、retired、当前 revision Evidence 有效和 active 上限，再条件更新为 active 并推进一次 ledger revision。
- [x] Data service 提供 active rows、current revisions、Evidence 和当前消息批量 read；Core 决定 Evidence validity、过滤和排序。
- [x] `PersistentMemoryStore` 只消费领域 `PersistentMemoryProjection`，继续在 `asyncio.to_thread()` 中读取并维护 stale fallback。

### 7.5 Orphan 恢复

- [x] `rp_memory.dream.recovery` 输出 typed decision：返回旧终态、拒绝已有本地任务、interrupt 指定 orphan、或创建替代 proposal。
- [x] 恢复请求必须携带预期 generating proposal ID；已终态直接返回旧 Proposal。
- [x] 只有同一 ID 仍为 SQL orphan 时才 interrupt，并按旧 depth/scope 创建替代任务。
- [x] `DreamTaskManager` 继续负责本地 task cancel/drain、持久化重试时间和通知，不自行发明状态迁移。
- [x] startup/shutdown 的 generating 批量 interrupt 使用 Core 准备的终态值和错误码，data service 只做条件批量更新并返回实际命中的 rows。

## 8. 分阶段实施顺序

### 阶段 A：行为锁定与类型准备

- [x] 将原数据层 Dream 业务用例按行为清单分类迁到 `rp_memory/tests`，并补齐状态迁移、条件更新冲突和第二次来源确认 characterization test。
- [x] 在 `rp_memory.dream.types/errors` 增加状态、生命周期、错误码和 command/result 类型，替换跨模块裸字符串。
- [x] 增加 typed transaction mode 和 data conditional-write 通用错误。
- [x] 迁移 `dream_source_identity.py` 的纯函数，双路径测试结果完全一致后删除旧文件。

### 阶段 B：Story Memory 先行拆层

- [x] 建立 `StoryMemoryDataService` CRUD/transaction primitives 和 repository。
- [x] 建立 `StoryMemoryApplicationService`，迁移 normalize、dedupe、merge、Evidence、version 和 progress 原子策略。
- [x] 迁移 `StoryMemoryStore`、Play API 分页、Dream snapshot、Session Reset 和测试调用方。
- [x] 删除 data service 中的 dict coercion、semantic signature、metadata merge、Evidence 选择和 Context projection。

### 阶段 C：Dream/Persistent 数据层收缩

- [x] 把 record 查询和写入拆到 Dream repository，返回 frozen data DTO。
- [x] 增加 proposal/item/state/memory/revision/evidence 的显式 create/update/delete/CAS 方法。
- [x] 增加批量消息/Story Memory/ledger snapshot read，消除 N+1 Evidence 查询。
- [x] 保留 SQL schema、partial unique、FK/CHECK/UNIQUE 与级联行为不变。

### 阶段 D：Proposal/Ledger application service

- [x] 迁移 proposal 生命周期、item normalize/patch、action policy、active limit、restore 和 Context projection 到 `rp_memory.dream`。
- [x] 让 `RPGDataDreamRepository` 只负责 source adapter 和 Dream service view 映射。
- [x] 把 Apply 改为第 7.3 节的唯一 IMMEDIATE 流程，删除 forced-stale fingerprint hack 和直接 database 访问。

### 阶段 E：恢复、调用方和旧入口清理

- [x] `DreamTaskManager` 使用 typed status/recovery policy；通知时机和重试参数保持不变。
- [x] `dream_service/main.py` 映射领域错误，HTTP status/error code 不变。
- [x] `PersistentMemoryStore`、Agent integration、Play/Dream tests 切到新业务入口。
- [x] `DataServiceGateway` 删除旧 `dream` / `story_memory` 业务入口和 data-layer Dream 业务错误导出。
- [x] 删除 data 层业务测试兼容入口，不保留静默 alias 或双写真源。

### 阶段 F：文档、静态 review 与独立提交

- [x] 更新 `AGENTS.md`：Dream/Story Memory owner、IMMEDIATE Apply、typed data boundary、禁止 data 层状态机与 merge policy。
- [x] 更新 `CLAUDE.md`、`README.md` 和主整改 TODO；只有实现和验证完成后才勾选 P2。
- [x] 静态搜索 `Any`、业务 magic string、固定协作者 `getattr/hasattr`、`gateway.database`、旧 service/error/import。
- [x] P2 作为独立 commit 提交，不混入状态表、Media/TTS 或用户已有工作区改动。

## 9. 测试迁移与验证矩阵

### 9.1 `rp_memory` 业务测试

- [x] Proposal 合法/非法状态迁移、终态不可变、条件写冲突映射。
- [x] ADD/REVISE/SUPERSEDE/RETIRE、retired revive、跨 lifecycle identity 冲突。
- [x] selected target/new-key 唯一性、active=64 边界、Restore 门禁。
- [x] history/source/ledger/Story Memory/Evidence/target revision 各类 stale。
- [x] Apply 第一次失败只写 stale；第二次来源确认失败回滚 ledger 后写 stale。
- [x] Context 只投影 Evidence 有效的 active current revision，排序稳定。
- [x] Story Memory exact-upsert、Evidence replacement、metadata/salience/source range/version/checkpoint 语义。
- [x] Story Memory fact/Evidence/progress 同事务回滚。
- [x] orphan recovery 的“终态返回旧值”和“同 ID orphan 才替代”。

### 9.2 `rpg_data` 数据测试

- [x] proposal/item/evidence/state CRUD、分页/排序、record 到 DTO 转换。
- [x] generating partial unique、Memory dedupe unique、revision/evidence unique 和 FK/CHECK。
- [x] Proposal expected status/version 与 memory/state expected version 条件更新只命中预期 row。
- [x] 显式 Story Memory create/update/Evidence replace/progress bulk write。
- [x] DEFERRED/IMMEDIATE transaction rollback 与同线程连接归属。
- [x] `/clear` 所需 Session rows 清理、Session delete 级联和 append-only Evidence 语义。
- [x] 数据测试不得断言 action、active-limit、恢复、状态机、merge 或 Context policy。

### 9.3 合约与基线

- [x] `dream_service/tests`：repository worker 串行、proposal recovery、通知和 HTTP error mapping。
- [x] `play_api/tests`：Dream proposal/memory 与 Story Memory 分页响应完全不变。
- [x] `rpg_core/tests`：post-commit Story Memory、Context Preview/Persistent projection、`/clear` 和 Session 删除不退化。
- [x] 完整 Python 基线：

```bash
uv run python -m pytest channels/tests rpg_core/tests rp_memory/tests llm_service/tests play_api/tests agent_service/tests rpg_data/tests rpg_media/tests media_service/tests rpg_tts/tests tts_service/tests dream_service/tests -q
```

- [x] 静态检查：`compileall`、`git diff --check`、旧入口/反向 import/`Any`/反射/magic string 搜索。

## 10. 完成标准

- [x] `rpg_data/services/dream_memory.py` 不再包含 Proposal 状态机、动作分支、active limit、Evidence validity、fingerprint、Context 排序或 Restore 资格。
- [x] `rpg_data/services/story_memory.py` 不再包含候选默认值、dedupe 生成、merge、Evidence 选择、semantic version 或 Context dict。
- [x] `rpg_data/services/dream_source_identity.py` 已删除，唯一实现位于 `rp_memory.dream`。
- [x] Dream service 和其它生产调用方不直接访问 `gateway.database` 或 Peewee record。
- [x] Apply 只有一个 `rp_memory.dream` 业务入口，并保持 IMMEDIATE、两次来源确认、原子 ledger/proposal/checkpoint 写入。
- [x] Story Memory capture 只有一个 `rp_memory` 业务入口，并保持 fact/Evidence/progress 原子提交。
- [x] 数据层只暴露 typed CRUD/CAS/transaction；领域层不接触 Peewee record。
- [x] HTTP、SSE、通知、SQL schema、WebUI、Context 内容和现有测试可观察行为不变。
- [x] 主整改计划勾选 P2；后续架构收口已将“状态表与 Scene”改为暂停项。
