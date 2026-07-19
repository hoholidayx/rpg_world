# Agentic Memory / Story Memory v2 完整待办

## 目标与边界

- [x] 将目标范式定义为“LLM 像查字典一样逐层查阅记忆”：主 Agent 不直接接收全部历史记忆，由 `MemorySubAgent` 先定位索引、逐步打开实体、线程、事实、Episode 和原始 Evidence，再提交一份带引用的调查结论。
- [x] 将 Story Memory v2 定义为现有 Story Memory 的演进版本，不再建立一套并行、重复的剧情事实系统。
- [x] 保留 `overall.md` 作为累计剧情归纳，负责主线、节奏、人物弧线和故事基调；不把它改造成精确事实数据库，也不把它当作事实 Evidence。
- [x] 使用 SQL 类型化账本作为 Story Memory v2 唯一真源；Markdown 只允许作为可重建、只读的人类排查视图。
- [x] 允许第一版优先保证记忆可追溯性与调查质量，暂不以 token 成本和最少 LLM 调用次数为首要约束。
- [x] 保持 Session/GM 全局记忆视角，不把玩家当前知道的信息和世界真实状态混为同一字段。
- [x] 保持 Scene、状态表、Persistent Memory 与 Story Memory 各自的权威边界，不让 Story Memory head 覆盖实时状态或持久记忆账本。
- [x] 本计划不包含 recall benchmark、LocoMo、GoldSeed、测试数据下载、指标调优或模型横向评测。
- [ ] 为该方案补充一份简短 ADR，记录上述目标、边界和关键取舍，避免实现过程中退回“把全部记忆直接塞入 Context”的旧模式。

## 非目标

- [x] 第一版不做跨 Session、跨 Story 或跨 Workspace 的全局实体自动合并。
- [x] 第一版不允许模型直接执行任意 SQL、读取任意工作区文件或绕过 Session 范围查询记忆。
- [x] 第一版不使用 `overall.md`、批次摘要或模型生成的解释替代原始消息 Evidence。
- [x] 第一版不把一次性已完成事件强行塞入状态线程；只有会演化、会冲突或需要追踪完成状态的记忆才线程化。
- [x] 第一版不做面向玩家的记忆图谱编辑 UI；先提供内部类型化接口、诊断输出和只读视图。
- [x] 第一版不自动破坏性合并同名实体，也不因为别名相似就修改已有 Entity ID。
- [x] 第一版不引入外部 Memory SaaS、独立向量数据库或新的 LLM Provider 直连路径；所有模型调用继续通过 `llm_client` → LLM Service。
- [x] 第一版不因 Story Memory 捕获、整理或召回失败而回滚已成功提交的主剧情 turn。

## 术语统一

- [ ] 在实现文档、类型名和提示词中统一以下术语，禁止同一概念出现多套名称：
  - `MemoryEntry`：一条不可变、可独立理解的剧情事实或主张。
  - `MemoryEntity`：Session 内稳定的角色、物品、地点、组织或其它可索引对象。
  - `MemoryThread`：一组会随剧情演化的 Entry，以及它们当前最佳解释和冲突状态。
  - `MemoryLink`：两个 Entry 之间的支持、替代、冲突、履约等语义关系。
  - `MemoryEvidence`：Entry 对原始已提交消息的精确引用及版本/hash 快照。
  - `MemoryEpisode`：覆盖一段连续剧情范围的事件单元，用于从事实索引回到叙事上下文。
  - `Head`：Thread 当前应优先查阅的一个或多个 Entry；不是对旧 Entry 的覆盖写。
  - `Candidate Head`：尚处于 `provisional` Link 阶段的新候选，不得隐藏已确认 Head。
  - `Effective Status`：根据有效 Evidence、Link 和 Thread 当前状态派生出的查询状态；不修改 Entry 原始字段。
- [ ] 为代码枚举、SQL CHECK、工具 schema、提示词和调试视图建立同一份集中常量来源，避免 magic string 分散。

## 一、先冻结领域模型

### 1. MemoryEntry

- [ ] 将现有 `SessionStoryMemory` 明确演进为不可变 `MemoryEntry`，保留原记录 ID 的稳定性，不做同义事实的全 Session 覆盖更新。
- [ ] 为 Entry 固定最小字段集合：
  - 稳定 `entry_id`、`session_id`。
  - 自然语言优先的 `claim_text`，要求单一、完整、脱离当前对话也可理解。
  - `memory_kind`。
  - `assertion_role`。
  - 原始 `epistemic_status`。
  - `salience`。
  - `capture_source`。
  - `source_turn_start`、`source_turn_end`。
  - 可空 `story_time_text`。
  - `capture_key`。
  - `created_at`。
- [ ] 冻结 `memory_kind` 的受控集合，并为旧值提供一对一迁移规则；第一版至少覆盖：
  - `character`：角色身份、特征或长期信息。
  - `event`：已经发生的一次性事件。
  - `relationship`：关系及其变化。
  - `commitment`：承诺、约定、委托或债务。
  - `goal`：尚未完成的目标或明确计划。
  - `clue`：线索、疑点和待验证信息。
  - `world_fact`：世界规则、地点或组织事实。
  - `state`：物品归属、人物状态、门是否打开等持续状态。
- [ ] 冻结 `assertion_role`：
  - `observation`
  - `speech_act`
  - `intent`
  - `attempt`
  - `outcome`
  - `state_snapshot`
  - `correction`
- [ ] 冻结 Entry 原始 `epistemic_status`，至少兼容现有：
  - `confirmed`
  - `reported`
  - `inferred`
  - `uncertain`
  - `contradicted`
- [ ] 明确 Entry 一经提交不得修改 `claim_text`、kind、assertion role、原始 epistemic status、来源范围和 Evidence；修正必须创建新 Entry 并建立 Link。
- [ ] 取消“规范化 claim + memory kind 在整个 Session 唯一”的语义去重方式。
- [ ] 将幂等键改为“同一来源快照内的同一捕获结果”维度；推荐由 Session、完整 Evidence manifest、规范化候选语义共同生成 `capture_key`。
- [ ] 确保同一次捕获重试不会重复写 Entry，但相同文字在不同 turn 再次发生时允许形成不同 Entry。
- [ ] 仅保留一个非核心、非查询语义的可选 `attributes_json` 扩展字段；实体、线程、Evidence、Link、Episode、时间、地点、认知视角等字段不得塞回 JSON。

### 2. MemoryEvidence

- [ ] 新增类型化 Evidence 表，不再以 `source_messages_manifest_json` 作为唯一来源表达。
- [ ] 每条 Evidence 至少保存：
  - `entry_id`
  - `message_id`
  - `turn_id`
  - `seq_in_turn`
  - `role`
  - `message_version`
  - `content_hash`
  - `evidence_kind`
  - 可选、受长度限制的 `quote_text`
- [ ] Evidence 的 `message_id` 不使用会随历史删除而级联删除的强外键；历史发生 edit/retry/truncate 后仍保留旧 Evidence 快照用于审计。
- [ ] Evidence resolver 优先精确匹配当前主消息表的 ID/version/hash，必要时再从 append-only 冷备中定位同版本内容。
- [ ] 定义 Evidence 有效性：只有消息 ID、版本、内容 hash 和 turn 元数据均匹配时才是 `valid`。
- [ ] 定义 Entry 派生有效性：
  - 所有必需 Evidence 有效：`valid`。
  - 仍有足够 Evidence、但部分来源失效：`partially_valid`。
  - 已无可验证来源或关键来源失效：`invalid`。
- [ ] Evidence 失效只改变派生投影，不回写或删除历史 Entry。
- [ ] 普通历史 edit/retry/truncate/delete 后触发受影响 Entry、Link、Thread Head、Episode 和索引的增量重算。
- [ ] `/clear` 继续按现有产品语义删除该 Session 的 Story Memory v2 全部账本；Session 删除继续依赖级联清理全部相关表。

### 3. MemoryEntity

- [ ] 新增 Session 级稳定 Entity 目录，Entity 至少包含：
  - 稳定 `entity_id`、`session_id`。
  - `entity_type`：`character | item | location | organization | concept | other`。
  - 当前展示名 `display_name`。
  - 可空 catalog 身份引用。
  - `created_at`。
- [ ] 对已挂载角色优先绑定现有 catalog / story character mount 身份，不为同一挂载角色生成第二个孤立 Entity。
- [ ] 对物品、地点、组织等无 catalog 对象生成 Session 内稳定 Entity ID。
- [ ] 新增 Entry–Entity 关联表，并使用受控 role，例如 `subject | object | participant | location | owner | knower | mentioned`。
- [ ] 将实体名称与别名放入类型化 `EntityName` 关系，不放进 Entry `attributes_json`。
- [ ] catalog 给出的 canonical name 可以无 Evidence；模型发现的别名必须由有效 identity Entry/Evidence 支持。
- [ ] 同名、近似名或别名冲突时保留多个 Entity 候选，通过调查和后续 Evidence 消歧；禁止静默合并 ID。
- [ ] 设计可逆的人工合并/拆分扩展点，但第一版只记录建议，不执行自动破坏性操作。

### 4. 认知视角

- [ ] Entry 的默认视角保持 Session/GM 全局，不默认等同于玩家角色已知。
- [ ] 为需要记录角色认知的 Entry 增加类型化关联：可空 `knower_entity_id` + `knowledge_mode`。
- [ ] 冻结 `knowledge_mode`：`knows | believes | heard | suspects`。
- [ ] `knowledge_mode` 只描述某实体的认知状态；不得取代 Entry 的世界事实 epistemic status。
- [ ] 第一版仅用于召回结果标注和主 Context 提示，不把它实现成玩家权限或信息隐藏系统。

### 5. MemoryThread

- [ ] 新增选择性 Thread；只有以下类别必须线程化：
  - 会改变的状态。
  - 承诺、约定与委托。
  - 未完成目标。
  - 未解线索。
  - 关系变化。
  - 后续可能被修正的事实。
- [ ] 一次性完成、无需后续演化的事件允许保持独立 Entry，不强制创建 Thread。
- [ ] Thread 至少保存：
  - 稳定 `thread_id`、`session_id`。
  - `thread_kind`。
  - 人类可读 `label`。
  - 可空主 Entity。
  - `lifecycle`：`open | resolved | conflicting | archived`。
  - `revision`、创建和更新时间。
- [ ] 新增 Thread–Entry 成员关系，永久保留所有历史成员，禁止用更新 Entry 的方式覆盖历史。
- [ ] 将 Thread Head 设计为独立、可重算的派生投影；Head 变化必须能从 confirmed Link 和有效 Entry 重建。
- [ ] 同一 Thread 允许多个 active confirmed heads，用来表达尚未解决的冲突。
- [ ] Thread 查询必须同时返回：confirmed heads、conflicting heads、provisional candidates、关键历史 Entry 和 lifecycle。

### 6. MemoryLink

- [ ] 新增 Entry 间 Link，统一方向为“较新的 source Entry 以 relation 指向较旧或被解释的 target Entry”。
- [ ] 冻结 Link 类型：
  - `supports`
  - `supersedes`
  - `contradicts`
  - `fulfills`
  - `fails`
  - `cancels`
  - `resolves`
- [ ] Link 至少保存 source/target Entry、relation、review status、提议来源、置信信息、可选 review Episode、幂等键和创建/复核时间。
- [ ] 冻结 Link 复核状态：`provisional | confirmed | rejected`。
- [ ] Capture 阶段只允许自动创建 `provisional` Link；MemoryEpisode 整理阶段才允许确认或拒绝。
- [ ] `provisional` Link 和 candidate head 必须可查，但不得隐藏、替代或关闭旧 confirmed head。
- [ ] `confirmed supersedes` 才把旧 head 替换为新 head。
- [ ] `confirmed contradicts` 在未解决时保留双方为 active heads，并把 Thread 标为 `conflicting`。
- [ ] `confirmed fulfills` 将承诺与其完成结果关联；只有结果 Evidence 明确时才关闭对应未完成项。
- [ ] `fails` 只表示一次尝试失败，不自动取消目标或承诺。
- [ ] `cancels` 表示明确撤销，`resolves` 表示线索/冲突被解决；两者都必须有直接 Evidence。
- [ ] Link 的 source、target 和 relation 一经建立不得改写；复核只允许合法状态迁移并保留审计信息。

### 7. MemoryEpisode

- [ ] 新增独立 MemoryEpisode 账本，作为“事实索引”和“原始 turn”之间的叙事层。
- [ ] Episode 至少保存：稳定 ID、Session、title、narrative、turn 范围、可选剧情时间/地点、来源指纹、创建时间。
- [ ] 新增 Episode–Entry、Episode–Entity、Episode–Evidence 关联，不用 JSON ID 数组代替关系表。
- [ ] Episode 使用自己的逐消息处理进度，不能复用 `summary_processed` 或 Entry capture 进度。
- [ ] SummaryBatch 与 Episode 范围相同时允许互相引用，并允许后执行者在校验来源指纹后复用 narrative；二者仍保持独立成功、失败和重试语义。
- [ ] Episode 不替代 Entry：具体当前状态、承诺、线索和关系仍落到 Entry/Thread；Episode 只补充“这段剧情如何发生”。
- [ ] Episode 不替代 `overall.md`：前者是可引用的局部事件单元，后者是持续更新的全局叙事归纳。

## 二、冻结权威边界与 Context 规则

- [ ] 为各记忆层写出并测试固定优先级：
  1. 当前 Scene 与 session 状态表：实时、结构化状态真源。
  2. Persistent Memory：经 Dream proposal/apply 确认的长期稳定事实真源。
  3. Story Memory v2 confirmed Thread heads / 独立 Entry：剧情事实和演化轨迹。
  4. MemoryEpisode：局部剧情经过和上下文。
  5. SummaryBatch / `overall.md`：叙事归纳与主线概览。
  6. 原始消息：最终 Evidence 与细节真源。
- [ ] 当 Scene/状态表与 Thread head 不一致时，Context 明确展示“实时状态优先，Story Memory 可能尚未整理”，而不是静默选择旧 head。
- [ ] Persistent Memory 与 Story Memory 命中同一事实时保留来源标识；不由 recall 过程直接改写任何账本。
- [ ] `overall.md` 继续作为主 Context 的摘要层输入，但不得给其内容伪造 Entry/Evidence 引用。
- [ ] 历史 Story Memory Entry 不再全部直接注入 `StoryMemoryLayer`。
- [ ] 主 Context 只允许直接投影：
  - 高显著度、Evidence 有效的 confirmed heads。
  - 未完成承诺、目标和线索。
  - conflicting Thread 的简短警示与 head 引用。
  - 与当前 Scene/状态冲突的陈旧记忆提示。
  - 本轮 `MemorySubAgent` 的类型化调查结论。
- [ ] provisional candidates 默认不作为确定事实直接投影；只有调查结论明确标注“待复核”时才可引用。
- [ ] 为 Context 投影设置确定性排序：权威层级 → 未完成/冲突优先 → salience → 最近有效 turn → 稳定 ID。

## 三、SQL Schema 与迁移

### 1. 表结构

- [ ] 新增下一号 `rpg_data` migration，并采用 SQLite 可回滚的建新表 → 搬迁 → 校验 → 换表流程。
- [ ] 保留 `rpg_session_story_memories` 的业务连续性，将其重构为 Entry 表，避免另建一个并行事实表后双写。
- [ ] 新增或重构以下类型化表：
  - Entry / 现有 Story Memory 主表。
  - Evidence。
  - Entity。
  - EntityName。
  - EntryEntity。
  - Thread。
  - ThreadEntry。
  - MemoryLink。
  - ThreadHead 派生投影。
  - MemoryEpisode。
  - EpisodeEntry / EpisodeEntity / EpisodeEvidence。
  - 必要的 Session ledger revision / projection state。
- [ ] 为所有 Session 子表配置正确外键和 Session 删除级联；Evidence 对消息只保存逻辑引用，不因消息行删除而级联消失。
- [ ] 为枚举、salience、正数 turn、source range、hash 长度、同 Session 引用等条件增加 SQL CHECK 与 service 双重校验。
- [ ] 为常用查询建立组合索引：Session + Entity、Session + Thread lifecycle、Thread + Head、Entry + turn、Evidence + message、Link + review status、Episode + turn range。
- [ ] 删除查询关键字段对 `metadata_json` 的依赖；保留的扩展 JSON 必须验证为 object，且不得参与核心过滤和关联。

### 2. 旧数据迁移

- [ ] 对每条现有 Story Memory 一对一创建 legacy Entry，不因旧 `dedupe_key` 相同或文本相似而二次合并。
- [ ] 使用原 `source_messages_manifest_json` 拆分生成 Evidence 行；解析失败的旧记录保留 Entry，并标记为 legacy/unresolved Evidence，而不是丢弃。
- [ ] 将旧 `entities`、`story_time`、`location` metadata 尽力搬到 Entity/关联列/时间字段；无法可靠解析的内容保留在非核心 legacy attributes 中并记录迁移报告。
- [ ] 将旧 kind/status 按显式映射迁移，不依赖模型重写旧事实。
- [ ] 为旧 Entry 生成只针对该旧记录的稳定 `capture_key`，不得沿用全 Session 语义唯一键。
- [ ] 停止旧 `_upsert_detail()` 对既有事实的原地 text/status/version 更新。
- [ ] 将 `dream_processed` 这类消费者 checkpoint 从 Entry 语义中剥离到独立 Dream manifest/checkpoint；迁移期间提供兼容读取。
- [ ] 迁移后校验每个 Session 的 Entry 数、Evidence 数、孤儿引用、唯一键和 source range，并输出本地迁移摘要。
- [ ] 提供迁移前数据库备份和失败自动回滚路径；禁止在 bootstrap 中静默删除无法迁移的旧记忆。

### 3. Repository 与 Service

- [ ] 在 `rpg_data.models` 中提供 frozen dataclass / enum，不让 `rp_memory`、`rpg_core` 直接使用 Peewee record 或裸 JSON dict。
- [ ] 拆分清晰的 repository/service API：capture commit、entity resolve、thread/link review、episode commit、evidence validate、recall read model、clear/delete。
- [ ] 所有跨 Entry、Evidence、Entity、Link、Thread Head、消息进度的写入在一个短 SQL 事务内完成。
- [ ] 为每个 Session 保存单调递增 ledger revision；写入和投影快照都返回 revision，供索引和 MemorySubAgent 判断陈旧结果。
- [ ] 为读取接口提供不可变快照对象，禁止调用方依靠 record 懒加载或在事件循环中执行 SQLite 阻塞工作。
- [ ] 继续通过 `asyncio.to_thread()` 运行 Memory 的 SQLite/文件/hash 阻塞工作，并遵守每 Session Memory async lock。

## 四、Entry Capture 流程

### 1. 触发与输入

- [ ] 将 Entry Capture 固定为每个已提交 IC/GM turn 后的 post-commit side effect；主 turn 成功不依赖 Capture 成功。
- [ ] 只读取已经提交、带合法正数 `turn_id/seq_in_turn` 的主消息快照，以及同一 turn 已提交的状态变化和 Narrative Outcome。
- [ ] GM/OOC 指令不能单独变成世界事实；必须以已提交 assistant 叙事结果或结构化状态变化为事实落点。
- [ ] IC 用户输入可以证明 speech act、intent 或 attempt，但不能单独证明行动 outcome。
- [ ] 过滤 system、tool 协议噪声和纯 OOC 内容；保留会改变剧情语义的 GM 指令作为来源上下文，而非完成 Evidence。
- [ ] Capture 输入必须带完整消息 ID/version/hash manifest、角色身份、Scene/状态前后快照和现有相关 Entity/Thread 候选。

### 2. 模型输出契约

- [ ] 将现有 `extract_story_details` schema 改为类型化 Capture proposal，至少返回：
  - Entry claim、kind、assertion role、epistemic status、salience。
  - Evidence message refs。
  - Entity mentions 与建议 role。
  - 可选 Thread 候选。
  - 可选 provisional Link 候选。
  - 可选 story time / knowledge perspective。
- [ ] 提示词明确区分“说了、想做、尝试、成功、失败、状态已改变、后来修正”。
- [ ] 提示词明确要求自然语言 claim 优先，不强迫模型输出 `subject-predicate-object` 三元组。
- [ ] 模型不得提供数据库 ID 以外的任意 SQL 条件；未知 Entity/Thread 使用 proposal，由代码解析和创建。
- [ ] 对模型输出做严格代码校验：枚举、Session 范围、Evidence 属于输入快照、turn 范围、最大条数、最大文本长度、Entity 引用和 Link 方向。
- [ ] 对小模型保留结构化工具调用与受控行式协议的 adapter 扩展点，但两种输出最终必须归一为同一 typed proposal。

### 3. 原子提交与幂等

- [ ] LLM 调用在 SQL 事务外完成；提交前重新校验消息 ID/version/hash 和 ledger revision。
- [ ] 在一个事务内完成 Entry、Evidence、Entity 关联、provisional Link、Thread candidate、Entry capture 消息进度和 ledger revision。
- [ ] 同一 Evidence 快照与候选语义的重复提交命中 `capture_key` 后返回既有 Entry，不新增重复记录。
- [ ] 一批候选中任一项越权或结构非法时明确决定“整批拒绝”或“逐项隔离”；第一版优先整批拒绝，保证进度与事实一致。
- [ ] 提交失败时不推进 `story_memory_processed`，让该 turn 可重试。
- [ ] 提交成功但响应丢失时，重试依靠 `capture_key` 幂等返回同一结果。
- [ ] Capture 连续失败只记录 warning 和可重试状态，不阻塞下一 turn；手动命令可查看失败原因并补跑。

## 五、MemoryEpisode / Consolidation 流程

### 1. 独立进度与分批

- [ ] 新增 Episode/consolidation 专用逐消息 processed 标志或等价类型化进度，不使用 last-turn 游标。
- [ ] 只按完整逻辑 turn 分批，禁止把同一 turn 的 user/assistant/tool 结果拆开。
- [ ] 为单批 turn 数、字符数、Entry 数和 Link 数设置代码硬上限；超大单 turn 返回明确可重试错误。
- [ ] SummaryBatch 与 Episode 可以采用相同的范围选择器，但成功、失败、回滚和 processed 标志完全独立。

### 2. Episode 生成

- [ ] 输入原始 turn、该范围已捕获 Entry、Entity、provisional Link、相邻 Thread heads，以及可复用的同范围 SummaryBatch。
- [ ] 生成局部 Episode narrative，保留传闻、推测、失败尝试、承诺与 outcome 的边界。
- [ ] Episode 必须引用原始 Evidence 和实际 Entry，不允许只保存无来源 prose。
- [ ] 从原始历史发现 Capture 漏项时，允许在同一提交中创建 `capture_source=episode_backfill` 的 Entry，并直接引用原始 Evidence。
- [ ] 对复用 SummaryBatch narrative 的情况校验来源范围与 fingerprint；不匹配则重新生成，不做模糊复用。

### 3. Link 复核与 Head 重算

- [ ] Consolidation 对本 Episode 涉及的 provisional Link 逐条输出 `confirmed | rejected` 及简短理由。
- [ ] 代码再次校验关系语义和 Evidence，不信任模型自由文本决定 Head。
- [ ] 在同一事务内提交 Episode、backfill Entry、Link review、Thread membership、Head 投影、Episode 进度和 ledger revision。
- [ ] 确认 `supersedes/fulfills/cancels/resolves` 后按确定性规则重算 Head/lifecycle。
- [ ] 确认 `contradicts` 后保留冲突双方，Thread 进入 `conflicting`，直到后续 `resolves/supersedes` 有效解决。
- [ ] 当旧 Entry Evidence 失效时，从剩余有效 confirmed Link 图重算 Head；不能简单回退到最大 Entry ID。
- [ ] Consolidation 失败不影响 Entry Capture 结果，也不推进 Episode 进度。

## 六、索引与可重建读模型

- [ ] 定义统一索引文档类型：`entity | thread | entry | episode`，每类都携带稳定 source ID、Session、ledger revision 和可过滤字段。
- [ ] Entity 文档索引 canonical name、有效别名和类型。
- [ ] Thread 文档索引 label、kind、lifecycle、主 Entity、confirmed heads、未完成/冲突标记。
- [ ] Entry 文档索引 claim、kind、assertion role、原始/派生状态、Entity、turn、salience 和 Evidence 有效性。
- [ ] Episode 文档索引 title、narrative、Entity、时间、地点和 turn 范围。
- [ ] 保持 text/keyword/FTS 在没有 embedding 时可独立工作；embedding、rerank 和 planner 都是可选增强，不是账本可用性的前置条件。
- [ ] 向量索引只保存可从 SQL 重建的表示和 source revision，不成为事实真源。
- [ ] 索引更新采用 ledger revision/change feed 或等价增量机制；进程崩溃后允许按 SQL 全量重建。
- [ ] Evidence 失效、Link review、Head 改变和 EntityName 变化都必须使对应索引文档失效或重建。
- [ ] Markdown 只读视图输出到 Session runtime/data 目录并保持 Git 忽略；不得由用户编辑后反写 SQL。
- [ ] 只读视图至少展示 Entity、Thread、confirmed/conflicting/candidate heads、Entry、Link、Episode 和 Evidence refs，便于本地排查。

## 七、三级“查字典”召回协议

### 1. Level 1：Entity / Thread / Entry

- [ ] 提供 Session-scoped `search_memory_index`，支持自然语言 query 和受控 filters，返回短摘要、类型、稳定 ID、分数来源和可继续打开的引用。
- [ ] 提供 `open_entity`，返回 Entity 名称、别名、相关 Thread、近期高价值 Entry 和歧义候选。
- [ ] 提供 `open_thread`，返回 lifecycle、confirmed/conflicting heads、candidate heads、关键 Link 和有界历史成员。
- [ ] 提供 `open_entry`，返回完整 claim、kind、assertion role、epistemic/effective status、Entity、Thread、Link、Episode 和 Evidence refs。
- [ ] 所有列表接口都使用稳定排序、游标/limit 和代码硬上限，避免模型一次展开整个 Session。

### 2. Level 2：Episode

- [ ] 提供 `open_episode`，返回局部叙事、turn 范围、参与 Entity、相关 Entry 和 Evidence refs。
- [ ] 提供按 Entry/Entity/Thread 反查 Episode 的接口，允许模型从事实跳回发生经过。
- [ ] Episode 返回内容必须区分模型 narrative 与原始 Evidence 引用，不把叙事归纳冒充原话。

### 3. Level 3：原始 turn/message

- [ ] 提供 `open_evidence` / `open_turns`，只允许读取当前 Session、且由前两级结果引用的消息。
- [ ] 返回 message ID、turn、role、version、hash 匹配状态和正文；失效 Evidence 明确标红/标记，不静默返回新版本正文。
- [ ] 从原始 turn 发现漏项时，调查结果可以直接引用该原始 Evidence，同时提交一个异步 backfill 请求；本轮回答不必等待 backfill 完成。
- [ ] 禁止 MemorySubAgent 通过模糊范围一次性拉取完整会话历史；每次打开必须基于稳定引用或受控邻近窗口。

### 4. 工具安全与调用轨迹

- [ ] 所有工具由代码绑定当前 `session_id`，schema 不接受模型传 workspace 路径、数据库路径或其它 Session ID。
- [ ] 工具结果使用 frozen dataclass / typed model，不返回约定 key 的任意裸 dict。
- [ ] 给每次调查设置最大工具轮次、最大展开节点、最大原始消息数、超时和取消检查；即使暂不优化 token，也必须防止死循环和无界读取。
- [ ] 记录调查 trace：query、打开过的稳定 ID、工具耗时、索引能力、停止原因和 ledger revision；不把内部 embedding、随机权重或敏感路径写进主 Context。
- [ ] 调查期间 ledger revision 变化时允许完成当前只读快照，但在结果中标记 stale；下一次 recall 使用新 revision。

## 八、MemorySubAgent 调查器

### 1. 类型化输入输出

- [ ] 新增 `MemoryInvestigationRequest`，至少包含玩家本轮输入、turn snapshot、Scene/状态摘要、角色身份、检索意图和 Context 预算。
- [ ] 新增 `MemoryInvestigationResult`，至少包含：
  - `findings`：每项 claim、effective status、confidence、Entry/Thread/Episode/Evidence refs。
  - `open_commitments`、`open_goals`、`open_clues`。
  - `conflicts` 与未解决问题。
  - `unknowns`，避免模型用缺失信息补事实。
  - `inspected_refs`。
  - `ledger_revision`、`stale`、`degraded_capabilities`。
  - 面向主 Context 的受控 projection。
- [ ] Finding 没有有效 Entry/Evidence 或明确标注的 Summary 来源时，不得以 confirmed 事实进入 projection。
- [ ] 将“未找到”与“确认不存在”分开表达。

### 2. 调查循环

- [ ] 先用当前输入、Scene、状态和实体名做 Level 1 检索，再由 MemorySubAgent 决定打开哪些结果。
- [ ] 对当前状态、最新事实、物品归属、承诺完成、目标进展和线索解决问题，优先打开对应 Thread，而不是只按文本相似度取 Entry。
- [ ] 当 Thread 存在冲突、Head Evidence 不足或问题询问“为什么/怎么发生”时再打开 Episode。
- [ ] 只有需要核对原话、行动 outcome、时间顺序或 Evidence 有效性时才打开原始 turn。
- [ ] MemorySubAgent 必须在输出前执行一次自检：结论是否有引用、是否混淆 intent/attempt/outcome、是否把 reported 当 confirmed、是否遗漏 conflicting head。
- [ ] 停止条件使用“已经足够回答请求 / 需要更多 Evidence / 信息确实未知”，不能以工具调用次数耗尽后编造结论。

### 3. 提示词

- [ ] 为 RP 优化调查提示词，明确：
  - 尊重玩家角色主权。
  - 台词不等于事实。
  - 意图和尝试不等于 outcome。
  - 当前 Scene/状态表高于记忆推断。
  - 承诺必须区分未完成、已完成、失败、取消。
  - 物品必须区分曾经持有和当前持有。
  - 冲突信息不得被单一相似结果静默覆盖。
  - 原始 Evidence 优先于 Episode，Episode 优先于 overall prose。
- [ ] 不强制调查模型一次输出复杂大 JSON；工具参数和最终结果可分别使用受控结构，底层 adapter 负责兼容小模型的逐条结果协议。
- [ ] 提示词不得泄露工作区绝对路径、数据库实现、embedding 分数细节或内部索引维护指令。

### 4. 能力降级

- [ ] LLM Service / MemorySubAgent 不可用时，主 Agent 保留确定性的 Context projection + keyword/FTS fallback，并明确记录调查未执行。
- [ ] embedding 不可用时跳过向量候选，继续 Entity/Thread 精确查询和 keyword/FTS。
- [ ] rerank 不可用时使用稳定融合排序，不把整个 recall 判为失败。
- [ ] planner 不可用或格式异常时使用原始 query + Entity/Thread 规则展开；只把 planner 能力标为 degraded。
- [ ] 任一工具调用失败时保留已验证 findings，并将失败步骤写入诊断；不得把未验证候选升级成事实。
- [ ] 调查取消立即停止后续 LLM/工具调用，不修改任何记忆账本。

## 九、主 Agent 与 Context 集成

- [ ] 将 Memory recall 保持在现有 `MemoryRecallHook` warning-and-continue 边界内，不新增可动态重排的 hook。
- [ ] 在 Context 门禁前捕获本轮不可变 Memory ledger/read-model snapshot，并让门禁估算与实际 Context 使用同一份 projection。
- [ ] 将现有 `StoryMemoryStore.get_all()` → 全量 `StoryMemoryLayer` 改为类型化、高价值的确定性 projection。
- [ ] 将本轮 `MemoryInvestigationResult` 作为独立 RP Memory section 渲染，不把 trace 和内部工具细节拼入正文。
- [ ] Context renderer 清楚区分：
  - `CURRENT_STATE`
  - `PERSISTENT_MEMORY`
  - `STORY_MEMORY_HEADS`
  - `UNRESOLVED_THREADS`
  - `MEMORY_INVESTIGATION`
  - `OVERALL_SUMMARY`
- [ ] conflicting Thread 必须显式列出冲突观点及稳定引用，不让主 Agent自行把其中一项当真相。
- [ ] Context projection 失败时保留上一份完整、不可变快照或安全空投影；不能返回半写入的数据结构。
- [ ] reload/switch session 时通过 `AgentContextResources` 整组重绑 Story Memory v2 store、recall tools 和 projection provider，不访问 Agent/SubAgent 私有字段。

## 十、Dream / Persistent Memory 兼容

- [ ] 更新 Dream source snapshot，使其读取有效、confirmed 的 Story Memory v2 Entry/Thread/Episode typed view，而不是依赖旧裸行和 `dream_processed` 布尔值。
- [ ] Shallow Dream 只接受 Evidence 仍按 ID/version/hash 精确匹配的 Entry/Episode。
- [ ] Dream source identity 纳入 Entry ID、不可变字段、Evidence fingerprint 和相关 confirmed Link/head revision。
- [ ] 未复核 provisional Entry relation、冲突未解决 head、Evidence invalid Entry 默认不晋升为 Persistent Memory。
- [ ] Dream 仍保持 proposal-first，Story Memory v2 recall 或整理流程不得直接写 Persistent Memory。
- [ ] Dream Apply 后不反向篡改 Story Memory Entry；如需表达长期事实已归纳，使用独立 consumer manifest/checkpoint。
- [ ] 更新 Dream source 失效、proposal stale、clear/session delete 和恢复测试。

## 十一、并发、取消与恢复

- [ ] 每个 Session 的 Capture、Consolidation、索引变更和 recall snapshot 继续受同一 Memory async lock 协调；不同 Session 可并发。
- [ ] LLM I/O 在 lock/SQL 事务外执行，只在快照捕获和短提交点持锁；提交前做 Evidence 与 revision 复核。
- [ ] watchdog 线程只入队 source/revision ID，实际去重、索引、embedding 和 SQL 更新由 loop-owned consumer 执行。
- [ ] Capture/Consolidation 原生任务可响应取消；取消发生在提交前则不推进进度，提交成功后不做补偿删除。
- [ ] 进程重启后通过逐消息进度和 SQL ledger revision 继续未完成批次，不依赖进程内游标。
- [ ] 索引 revision 落后时自动补建；索引损坏不影响 SQL typed reads 和 Thread 精确查询。
- [ ] 为连续失败提供有界重试和人工补跑入口，不加入无界后台自旋。

## 十二、可观测性与本地排查

- [ ] 为 Capture、Episode、Link review、Head recompute、index sync 和 investigation 使用独立 `source`/阶段名。
- [ ] 日志至少记录 Session、turn/range、ledger revision、候选/落库数量、跳过原因、错误码和耗时。
- [ ] verbose logging 可记录公开 claim sample 与稳定 ID，但不记录 Provider 密钥、内部 token、工作区敏感路径或完整未截断历史。
- [ ] 提供只读诊断命令或内部 API，查看某 Entry 的 Evidence 有效性、某 Thread 的 Head 推导过程、某索引文档 revision 和某次调查 trace。
- [ ] 诊断结果明确标记当前启用的 text/keyword/vector/rerank/planner 能力及降级原因；该信息只用于排查，不进入玩家正文。
- [ ] 大型 trace、索引 dump 和完整历史视图只保存在 Git 已忽略的 `data/` runtime 目录。

## 十三、分阶段实施顺序

### Phase 0：规格冻结

- [ ] 完成 ADR、术语表、枚举表、Link 方向、Head 状态机和权威层级评审。
- [ ] 画出当前 Story Memory → v2 表和 API 的一对一迁移清单。
- [ ] 明确所有受影响路径：`rpg_data`、`rp_memory`、`MemorySubAgent`、Context、post-commit hooks、Dream、session reset/delete、derivation、配置和测试。
- [ ] 确认旧数据迁移、失败回滚和 feature flag/cutover 方案后再写 migration。

### Phase 1：SQL 账本与 typed service

- [ ] 添加 migration、record、frozen model、repository 和 service。
- [ ] 完成 Entry 不可变、Evidence、Entity、Thread、Link、Head、Episode 的代码级不变量。
- [ ] 完成 legacy 数据迁移与兼容只读 adapter。
- [ ] 完成 clear、session delete、history mutation reconciliation。

### Phase 2：逐 turn Entry Capture

- [ ] 改造 MemorySubAgent Capture schema 和 RP prompt。
- [ ] 接入 post-commit hook、消息快照复核、原子写入和幂等。
- [ ] 先切换写路径，旧 Context 读取仍可通过兼容 projection 工作；禁止双写两套事实。
- [ ] 确认稳定后移除旧 `_upsert_detail` 语义覆盖逻辑。

### Phase 3：Episode、Link review 与 Thread Head

- [ ] 实现独立 Episode progress 和分批。
- [ ] 实现 backfill Entry、两阶段 Link、Head 重算和冲突保留。
- [ ] 实现 SummaryBatch 同范围引用/复用，但保持独立失败语义。
- [ ] 接通历史变更后的 Evidence/relation/head reconciliation。

### Phase 4：索引与分级读取工具

- [ ] 构建 Entity/Thread/Entry/Episode 可重建索引文档。
- [ ] 实现四类索引的增量 revision 同步和全量重建。
- [ ] 实现 Level 1/2/3 typed tools、Session 绑定、分页、限制、取消和 trace。
- [ ] 验证无 embedding/rerank/planner 时仍能完成确定性查阅。

### Phase 5：Agentic Memory 调查循环

- [ ] 实现 `MemoryInvestigationRequest/Result`。
- [ ] 实现 MemorySubAgent 逐层打开、证据自检、停止条件和降级路径。
- [ ] 将调查结论接入 `MemoryRecallHook` 与主 Context renderer。
- [ ] 确保调查只读，不在 recall 事务中直接修正账本；漏项只登记异步 backfill。

### Phase 6：Context 切换与 Dream 兼容

- [ ] 将主 Context 从全量 Story Memory 切换到 heads/unresolved/investigation projection。
- [ ] 完成 Context 门禁、preview、reload/switch 和失败快照语义。
- [ ] 更新 Dream source/checkpoint/fingerprint 并移除 `dream_processed` 旧耦合。
- [ ] 删除旧 JSON metadata 查询、旧 source manifest JSON 和旧全量注入兼容代码。

### Phase 7：文档与清理

- [ ] 更新架构文档、运行数据说明、Context 文档和开发调试说明。
- [ ] 更新 `AGENTS.md` 中 Story Memory、MemorySubAgent、Summary 和 Dream 的最终不变量。
- [ ] 补充本地只读 Markdown 视图说明，并确认其路径被 Git 忽略。
- [ ] 删除已无调用方的旧模型、service 方法、提示词和配置键。

## 十四、测试待办

### Domain / SQL 单元测试

- [ ] Entry 写入后不可修改；修正只能创建新 Entry + Link。
- [ ] 同 Evidence 同语义重试幂等；不同 Evidence 的相同 claim 不被吞掉。
- [ ] Evidence manifest 精确校验 ID/version/hash/turn/seq，非法跨 Session 引用失败。
- [ ] Entity catalog 绑定、别名 Evidence、同名不自动合并。
- [ ] knowledge mode 与 epistemic status 独立。
- [ ] provisional Link 不改变 Head。
- [ ] confirmed supersedes 正确换 Head。
- [ ] confirmed contradicts 保留多个 Head 并进入 conflicting。
- [ ] fulfills/cancels/resolves 关闭正确 Thread；fails 不错误关闭目标。
- [ ] Entry Evidence 失效后 Head 确定性回退或进入无有效 Head 状态。
- [ ] Episode 与 SummaryBatch 进度独立，任一失败不推进另一方。
- [ ] migration 保留旧 Entry 数量、文本、turn 范围和可解析 Evidence。

### Capture 集成测试

- [ ] IC 用户说“我要打开门”只生成 intent/attempt，不生成已打开 outcome。
- [ ] assistant 明确叙述成功且状态提交后才生成 outcome/state Entry。
- [ ] 角色承诺、履约、失败尝试、取消承诺分别形成正确 Entry/Link。
- [ ] 物品曾经持有、转交、丢失后，当前 Head 指向最新有效状态，历史仍可查。
- [ ] GM/OOC 指令不单独污染世界事实。
- [ ] LLM 失败、格式错误、事务失败、取消和响应丢失均保留可重试进度。
- [ ] post-commit Story Memory 失败不回滚主剧情 turn。

### Consolidation / Evidence 回归测试

- [ ] Episode 能发现 Capture 漏项并以原始消息创建 backfill Entry。
- [ ] Link review rejected 后旧 Head 不变，候选不再参与投影。
- [ ] edit/retry/truncate/delete 使旧 Evidence 失效并重算相关 Thread。
- [ ] append-only backup 可用于核对旧 Evidence，但失效旧事实不重新进入当前 projection。
- [ ] `/clear` 清除 v2 账本与进度；Session delete 清除全部级联行。
- [ ] Dream shallow/deep source 只接受其各自允许且 Evidence 有效的记录。

### Agentic Recall 集成测试

- [ ] Entity → Thread → Entry 能回答“某物现在在哪里”，并引用最新 confirmed Head。
- [ ] Thread → Episode → Evidence 能回答“这个承诺何时、如何完成”。
- [ ] 冲突 Thread 返回双方和未解决状态，不选择相似度较高的一方冒充真相。
- [ ] reported/inferred/uncertain 不被调查报告升级为 confirmed。
- [ ] 原始历史存在漏项时，本轮可引用 Evidence 回答，并生成后续 backfill 请求。
- [ ] embedding/rerank/planner 分别不可用时走对应降级路径，调查仍可返回可验证结果。
- [ ] 工具无法跨 Session、无法打开未经引用的大范围原始历史、无法无界分页。
- [ ] ledger revision 中途变化时结果标记 stale，且不会混合两个 revision 的对象。

### Context / Agent 回归测试

- [ ] 主 Context 不再包含全部历史 Story Memory Entry。
- [ ] confirmed heads、未完成项、冲突提示和调查结论按固定顺序渲染。
- [ ] Scene/状态表与 Story Memory 不一致时以实时真源为准并显示陈旧提示。
- [ ] Context preview 与实际 turn 共用同一 Memory snapshot。
- [ ] recall 失败 warning-and-continue，send/send_stream 仍共用既有 turn pipeline。
- [ ] reload/switch 后新 Session 的 store/tool/provider 全部正确重绑且不泄漏旧 Session 数据。
- [ ] 现有 summary compression、overall 更新、Persistent Memory、Dream、history CRUD 和 session derivation 行为无非预期回归。

## 十五、验收标准

- [ ] 任意进入主 Context 的 Story Memory 确定事实都能追溯到稳定 Entry ID 和至少一条当前有效 Evidence，或被明确标注为 Summary/推断。
- [ ] 查询最新事实、物品当前状态、承诺与完成、目标进展、线索解决时，系统优先基于 Thread head 和 Link 语义，而不是只依赖文本相似度。
- [ ] intent、attempt、speech act、outcome 和 state snapshot 在存储与召回中不再混淆。
- [ ] 新事实不会覆盖旧 Entry；时间演化、修正和冲突均通过 Link/Thread 可完整回放。
- [ ] 冲突未解决时保留多个 active heads，provisional candidate 不隐藏 confirmed head。
- [ ] `overall.md` 仍提供连贯剧情主线，但不承担精确事实或 Evidence 职责。
- [ ] SummaryBatch、MemoryEpisode、Story Memory Entry 和 Persistent Memory 各有独立真源、进度和失败语义。
- [ ] SQL 是唯一账本真源；删除全部本地 FTS/vector/Markdown 投影后可以从 SQL 完整重建。
- [ ] 没有 embedding、rerank 或 planner 时，Entity/Thread/Entry/Evidence 的基础查阅仍可用，并清楚说明能力降级。
- [ ] Story Memory 捕获、整理、召回或索引异常不会破坏主 turn 的事务边界，也不会产生跨 Session 读取。
- [ ] 旧 Session 迁移后不丢失现有 Story Memory，且没有因旧 dedupe 规则继续发生覆盖更新。

## 十六、风险与缓解待办

- [ ] 风险：模型错误识别 outcome；通过 assertion role、assistant/状态 Evidence 门禁和 Episode 二次复核缓解。
- [ ] 风险：Entity 碎片化；通过 catalog 绑定、EntityName 索引、歧义候选和可逆人工合并扩展点缓解。
- [ ] 风险：Link 错误导致当前 Head 错误；通过 provisional → confirmed 两阶段、确定性 Head 规则和可重算投影缓解。
- [ ] 风险：Entry/Episode/Link 长期增长；先保留完整账本，查询使用有界索引和分页，后续再做归档而非删除 Evidence。
- [ ] 风险：历史编辑导致大量衍生内容陈旧；通过 Evidence 精确匹配、受影响图增量重算和索引 revision 缓解。
- [ ] 风险：MemorySubAgent 工具循环失控；通过调用轮次、节点、消息数、超时和取消硬上限缓解。
- [ ] 风险：小模型无法稳定输出复杂结构；通过小步工具协议、逐条输出 adapter 和代码归一化缓解。
- [ ] 风险：迁移同时影响 Dream/Context/derivation；通过兼容 typed view、分阶段 cutover 和禁止双写缓解。

## 十七、明确延后

- [ ] 延后跨 Session / 跨 Story 的人物、地点、物品统一身份图谱。
- [ ] 延后自动执行 Entity merge/split 和面向用户的图谱编辑器。
- [ ] 延后把 `knowledge_mode` 扩展为严格的信息可见性/权限系统。
- [ ] 延后自动遗忘、压缩或删除历史 Entry/Evidence 的策略。
- [ ] 延后 token 成本、缓存策略、工具轮次最优化和模型路由精调。
- [ ] 延后 benchmark、第三方数据集、召回分数门槛和 A/B 指标；待语义账本与查询协议稳定后另立计划。
- [ ] 延后接入 mem0、LanceDB 或其它成熟方案；若未来引入，只允许作为可替换索引/检索适配层，不取代本方案的 SQL 权威账本和 RP 语义模型。

