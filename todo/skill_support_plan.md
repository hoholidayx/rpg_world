# RPG World Agent Skill 支持落地计划

## 1. 背景与目标

当前 `RPGGameAgent` 已具备稳定的主 Agent 编排能力：会话串行队列、RPG 五层上下文构建、状态/记忆子 Agent、工具调用循环、命令分发与流式输出已经形成清晰边界。本计划的目标是在不破坏现有 Telegram 优先体验与上下文缓存策略的前提下，为主 Agent 引入类似主流 Agent/工具生态的 **Skill** 能力：

- Skill 是可被 Agent 按需启用的能力包，包含元数据、摘要、详细说明、可选资源、可选工具或工作流。
- Skill 支持 **渐进式披露（progressive disclosure）**：常驻上下文只暴露轻量索引与摘要；只有当当前任务匹配某个 Skill 时，才加载并注入该 Skill 的详细内容。
- 第一阶段先实现基础 Skill：可发现、可配置、可注入、可测试。
- 第二阶段优化 Skill：引入摘要匹配、按需展开、预算控制、缓存与观测能力。

## 2. 现有架构评审

### 2.1 主 Agent 编排链路

`RPGGameAgent` 是主入口，生命周期大致为：

1. 构造时记录 session/workspace/model 参数，并同步 `_refresh_rpg_context()` 构建 RPG context managers/stores。
2. `_ensure_initialized()` 懒初始化 system prompt、session history、MemoryManager、LLM provider、StatusSubAgent、MemorySubAgent、SummaryCompressor、CommandDispatcher 与 ToolRegistry。
3. `send()` / `send_stream()` 将用户输入放入队列，由 `_queue_consumer()` 串行处理。
4. `_send_impl()` / `_send_stream_impl()` 在单轮内依次完成命令分发、状态预更新、历史追加、记忆召回、剧情记忆抽取、自动压缩、上下文构建、工具 schema 获取、LLM tool loop 执行、历史落盘。

这条链路适合接入 Skill，因为 Skill 的选择与注入发生在 **用户输入已知、上下文构建之前**；Skill 工具注册则应发生在 `_setup_tool_registry()` 或 Skill 激活后增量注册阶段。

### 2.2 五层上下文构建链路

`RPGContextBuilder.build()` 目前将输入拆成固定层、常驻记忆、摘要、热历史、剧情记忆、召回记忆、状态表与用户消息等模块。其注释明确强调稳定内容靠前、动态内容靠后，以提升 prefix cache 命中率。

Skill 的上下文注入应遵循同一原则：

- Skill 索引/摘要是低频变化内容，可放在固定层附近，或作为独立 system 模块位于 fixed layer 之后。
- 已激活 Skill 的详细说明与使用约束是按轮动态变化内容，应该放在用户输入之前、状态/召回之后或紧邻用户消息之前，避免无关 Skill 污染长期 prefix。
- 若某个 Skill 在同一会话多轮连续激活，可利用会话级缓存与短 TTL，减少重复加载和 token 抖动。

### 2.3 工具系统链路

现有工具系统由 `BaseTool`、`ToolRegistry` 与 `run_chat_loop()` 组成：

- `_setup_tool_registry()` 注册内置文件工具、SceneTracker 工具与额外工具。
- `ToolRegistry.get_openai_schemas()` 每轮向 provider 暴露完整 tool schemas。
- `run_chat_loop()` 根据模型返回的 `tool_calls` 执行 registry 中的工具，并把 assistant/tool messages 追加到工作上下文。

Skill 可以有两种工具接入方式：

1. **第一阶段推荐：Skill 仅提供说明与工作流，不直接注册工具。** 复用现有文件工具和场景工具，降低风险。
2. **第二阶段扩展：Skill 可声明工具依赖或自带工具 provider。** 激活 Skill 后只暴露相关工具 schema，避免所有 Skill 工具常驻模型工具列表。

### 2.4 命令与可观测链路

`CommandDispatcher` 适合作为 Skill 管理的人工入口，例如：

- `/skills`：列出可用 Skill 摘要与启用状态。
- `/skill <name>`：查看 Skill 详情。
- `/skill enable|disable <name>`：会话级启停 Skill。
- `/skill reload`：重新扫描 Skill 目录。
- `/context`：未来可以展示本轮匹配到的 Skill 与 token 占用。

第一阶段可先实现只读命令，第二阶段再增加匹配解释、命中分数与调试输出。

## 3. 设计原则

1. **不破坏现有上下文缓存策略**：Skill 摘要和详情分层注入，避免全量 Skill 常驻。
2. **配置访问走封装**：新增 `settings.skill_settings` 或等价 typed accessor，不在业务模块硬编码 YAML key 路径。
3. **文件格式简单可迁移**：优先使用目录 + `SKILL.md` + front matter 或 `skill.yaml`，后续可扩展 assets/references/scripts。
4. **默认安全**：Skill 只能读取 workspace/package 内允许目录；执行型能力必须显式开启。
5. **Telegram 优先无感**：聊天入口不需要额外操作即可受益，命令输出需适合 Telegram 分块与 Markdown 渲染。
6. **测试优先覆盖纯核心层**：Skill 发现、匹配、注入、预算裁剪优先做单元测试，避免真实 LLM 调用。

## 4. 建议目录与数据模型

### 4.1 Skill 存储目录

建议支持两个来源，按优先级合并：

```text
rpg_world/skills/                 # 随代码提交的内置 Skill
rpg_world/data/<workspace>/skills/ # 工作区自定义 Skill，可被运营/用户编辑
```

单个 Skill 目录示例：

```text
skills/
  story_architect/
    SKILL.md
    references/
      pacing.md
    assets/
      beat_sheet.md
```

### 4.2 `SKILL.md` 建议格式

```markdown
---
name: story_architect
title: 剧情结构设计
summary: 帮助规划章节节奏、冲突升级、伏笔回收与剧情节点。
version: 1
enabled: true
triggers:
  keywords: [剧情, 章节, 伏笔, 节奏, 冲突]
  intent: [plan_story, revise_plot]
budget_tokens: 1200
---

# 剧情结构设计

## 何时使用
...

## 工作流
...

## 输出格式
...
```

### 4.3 核心数据类

建议新增模块 `rpg_core/skills/`：

```text
rpg_core/skills/
  __init__.py
  models.py       # SkillManifest, SkillSummary, LoadedSkill, SkillMatch
  loader.py       # SkillLoader: 扫描、解析、校验、缓存
  matcher.py      # SkillMatcher: 基础关键词匹配 -> LLM/embedding 匹配扩展
  manager.py      # SkillManager: 对 Agent 暴露统一 API
  renderer.py     # Skill 上下文渲染与 token 预算裁剪
```

关键模型：

- `SkillManifest`：name/title/summary/enabled/triggers/budget/source_path/version。
- `SkillSummary`：常驻索引用的轻量对象，只包含 name/title/summary/triggers 摘要。
- `LoadedSkill`：完整 Skill 内容与引用资源，仅在命中后加载。
- `SkillMatch`：skill name、score、reason、matched keywords、是否强制启用。
- `SkillRenderResult`：注入文本、token 估算、被裁剪片段、命中解释。

## 5. 第一阶段：基础 Skill 实现

### 5.1 阶段目标

实现最小可用 Skill 能力：

- 启动时扫描 Skill 目录。
- 解析 Skill manifest 与正文。
- 支持配置总开关、目录、每轮最多激活数量、token 预算。
- 基于关键词/显式命令进行简单匹配。
- 将命中的 Skill 详情注入主 Agent 上下文。
- 提供命令查看 Skill 列表与详情。
- 提供核心单元测试。

### 5.2 具体任务拆分

#### 任务 1：配置与默认值

- 在 `settings.yaml` 增加 `skills` 配置块：
  - `enabled: true`
  - `builtin_dir: skills`
  - `workspace_dir: skills`
  - `max_active_per_turn: 2`
  - `max_summary_tokens: 800`
  - `max_detail_tokens: 1600`
  - `match_mode: keyword`
- 在 Settings 封装中增加 `skill_settings` accessor。
- 明确配置合并规则：工作区 Skill 与内置 Skill 同名时，工作区覆盖内置。

#### 任务 2：Skill Loader

- 新增 `SkillLoader`：
  - 扫描配置目录下一级子目录。
  - 读取 `SKILL.md`。
  - 解析 YAML front matter；无 front matter 时允许从一级标题和首段推断 title/summary，但标记 warning。
  - 校验 `name` 只能使用 `[A-Za-z0-9_-]+`，避免路径穿越和命令歧义。
  - 缓存 mtime/hash，支持 reload。
- 单元测试覆盖：合法 Skill、缺字段、重复 name、禁用 Skill、工作区覆盖。

#### 任务 3：Skill Manager

- 新增 `SkillManager`：
  - `list_summaries()` 返回可用 Skill 摘要。
  - `get_skill(name)` 按需加载完整内容。
  - `match(user_input, history=None)` 返回 `SkillMatch` 列表。
  - `render(matches, token_counter)` 返回可注入上下文。
- 第一阶段 matcher 使用确定性规则：关键词命中、name/title 显式提及、命令强制启用。
- 暂不做 embedding/LLM 判断，避免引入额外 provider 成本。

#### 任务 4：Agent 接入

- 在 `_refresh_rpg_context()` 或 `_ensure_initialized()` 中创建并持有 `self._skill_manager`。
- 在 `_send_impl()` 与 `_send_stream_impl()` 中，在 `_build_transformed_context()` 之前执行 Skill 匹配。
- 修改 `_build_transformed_context()` 支持接收 `active_skills` 或在 Agent 内拼接 Skill system message。
- 推荐第一阶段采用 **Agent 内追加 system message**：
  - 保持 `RPGContextBuilder` 变更较小。
  - 在 `ctx.to_message_objects()` 后、最终 user message 前插入 `Skill` system message。
  - 后续第二阶段再将 Skill 纳入 `RPGContext` 结构化 layer。
- 注意 send 与 send_stream 必须共用同一选择逻辑，避免行为分叉。

#### 任务 5：命令接入

- 在 `CommandDispatcher` 注册 Skill 相关命令：
  - `/skills`：列出 name/title/summary/enabled。
  - `/skill <name>`：展示完整 Skill 或详情摘要。
  - `/skill reload`：重新扫描目录。
- 输出格式需兼容 Telegram Markdown，避免过长；长详情可截断并提示文件路径。

#### 任务 6：测试

- 新增 `rpg_core/tests/test_skills.py`：覆盖 loader/manager/matcher/renderer。
- 新增 Agent 级轻量测试：mock provider，验证命中 Skill 时 messages 中出现 Skill system message；未命中时不注入详情。
- 新增命令测试：验证 `/skills`、`/skill <name>`、`/skill reload`。

### 5.3 第一阶段验收标准

- 配置关闭 `skills.enabled=false` 时，Agent 行为与当前一致。
- 至少一个示例 Skill 能被扫描、匹配、注入。
- 未匹配 Skill 的完整正文不会出现在 LLM messages 中。
- send 与 send_stream 的 Skill 注入结果一致。
- 单元测试不依赖真实 LLM、网络或 Telegram。

## 6. 第二阶段：渐进式披露与优化

### 6.1 阶段目标

将基础 Skill 升级为可扩展的渐进式披露体系：

- 常驻上下文只包含 Skill 索引摘要，而不是所有 Skill 正文。
- 每轮先用摘要和用户输入做匹配，再按需加载详情。
- 支持多级展开：摘要 → 详情 → references/assets 局部片段。
- 支持 token 预算、优先级、缓存、命中解释与观测。
- 可参考主流 Agent 做法：先暴露 capability card/manifest，再由 Agent 或运行时根据任务加载完整说明和资源。

### 6.2 渐进式披露设计

#### 层级 0：Skill Registry Index（轻量常驻）

只包含每个 Skill 的：

- name
- title
- summary
- triggers 简表
- 何时使用的一句话

该索引用于帮助模型知道“有哪些能力可以请求”，但不包含完整工作流。预算建议 500-1000 tokens，并按启用 Skill 数量裁剪。

#### 层级 1：Active Skill Detail（按轮注入）

当运行时 matcher 判断某个 Skill 与当前输入相关时，加载：

- 完整 `SKILL.md` 主体。
- 关键约束与工作流。
- 输出格式。

每轮最多激活 1-3 个 Skill，总预算由 `max_detail_tokens` 控制。

#### 层级 2：Skill References（工具式按需读取）

对于 references/assets/scripts，不直接注入上下文，而是提供只读工具或命令：

- `list_skill_resources(skill_name)`
- `read_skill_resource(skill_name, path)`

只有当模型明确需要细节时才读取。这样大型参考文档不会进入常驻上下文。

### 6.3 匹配策略演进

#### 方案 A：确定性 matcher 增强

- keywords/title/name 匹配。
- 最近 N 轮用户输入拼接匹配。
- Skill cooldown，避免连续误触发。
- 用户显式提及 Skill name 时提升分数。

优点：稳定、可测试、低成本。缺点：语义泛化弱。

#### 方案 B：LLM 小模型路由

新增 `AGENT_SKILL_ROUTER_BIZ_KEY`：

- 输入：用户当前请求、Skill 摘要列表、最近一小段历史。
- 输出：JSON 数组 `{name, score, reason}`。
- 使用便宜模型或主 provider 的低 token 配置。
- 失败时 fallback 到确定性 matcher。

优点：语义识别强。缺点：增加一次调用延迟和成本，需要严格 JSON 解析与测试 mock。

#### 方案 C：Embedding / 向量匹配

- 对 Skill summary、triggers、正文摘要建立轻量索引。
- 用户输入 embedding 后召回 TopK。
- 再用规则或 LLM rerank。

优点：适合大量 Skill。缺点：需要索引生命周期与 embedding provider。

建议第二阶段按 A → B → C 递进，不要一次性引入复杂检索。

### 6.4 上下文注入位置优化

建议将 Skill 纳入 `RPGContext` 结构：

```text
[0] fixed layer
[1] skill registry summary          # 低频变化，轻量
[2] persistent memory
[3] summary
[4..N] hot history
[N+1] story memory
[N+2] recalled memory
[N+3] status tables
[N+4] active skill details          # 按轮动态
[N+5] user message
```

这样可以：

- 在 `get_context_info()` / `/context` 中展示 Skill layer token。
- 保持 prefix cache 友好：摘要层相对稳定，详情层靠后。
- 让测试直接断言 RPGContext layer。

### 6.5 工具 Schema 渐进式披露

第二阶段可把工具列表也做按需披露：

- 默认只暴露通用工具与 Skill 资源发现工具。
- Skill 激活后暴露该 Skill 声明依赖的工具。
- 对同名工具做命名空间约束，如 `skill_story_architect_read_reference` 或统一资源工具参数中包含 `skill_name`。
- `ToolRegistry` 可增加 `get_openai_schemas(active_skill_names=None)`，按标签过滤 schema。

这能降低工具 schema token，并减少模型误调用无关工具。

### 6.6 可观测与调试

新增本轮 Skill 诊断信息：

- 匹配到哪些 Skill。
- 命中分数和原因。
- 注入 token 数。
- 哪些内容因预算被裁剪。
- Skill loader warning。

落点：

- `TurnStats` 扩展 `skill_matches` 字段，或 AgentReply 增加 `skill_records`。
- CLI/Telegram 可在 verbose/debug 命令下展示。
- `/context` 输出增加 Skill layer。

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| Skill 正文过大导致上下文膨胀 | LLM 成本上升、回复变慢 | 默认 token 预算、详情裁剪、references 工具式读取 |
| 误匹配 Skill 干扰主 RPG 回复 | 角色扮演质量下降 | 匹配阈值、最多激活数量、命中解释、用户可禁用 |
| 与现有记忆/状态层顺序冲突 | prefix cache 命中率下降 | 摘要层靠前且稳定，详情层靠后且按轮注入 |
| Skill 文件可执行内容带来安全问题 | 文件/命令风险 | 第一阶段不支持脚本执行；第二阶段执行型能力显式白名单 |
| send 与 send_stream 行为不一致 | 渠道体验分裂 | 抽取公共 `_select_active_skills()` 与 `_build_messages_with_skills()` |
| 工作区覆盖规则不清晰 | 调试困难 | loader 输出 source_path 与 override warning |

## 8. 推荐实施顺序

### 第一阶段里程碑

1. `rpg_core/skills/models.py` 与 `loader.py`。
2. `SkillManager` 的 list/get/match/render。
3. `settings.yaml` 与 Settings accessor。
4. Agent 非流式接入。
5. Agent 流式接入并抽公共方法。
6. `/skills` 与 `/skill` 命令。
7. 测试与示例 Skill。

### 第二阶段里程碑

1. Skill registry summary layer。
2. RPGContext 结构化 Skill layer 与 `/context` 展示。
3. matcher 增强：历史窗口、cooldown、阈值、解释。
4. 可选 LLM router biz key 与 JSON 输出解析。
5. Skill resource 工具。
6. Tool schema 按 Skill 激活过滤。
7. 观测字段与 Telegram/CLI debug 输出。

## 9. 建议优先实现的示例 Skill

为了验证 RPG 场景价值，建议内置 3 个轻量 Skill：

1. `story_architect`：剧情规划、章节节奏、伏笔回收。
2. `character_voice`：角色口吻一致性、对白风格检查。
3. `world_lore_guard`：世界观一致性、设定冲突检查。

这些 Skill 都只需要提示词工作流，不需要新工具，适合第一阶段验证。

## 10. 最终验收清单

- [ ] Skill 可通过内置目录和工作区目录发现。
- [ ] 常驻上下文不包含所有 Skill 正文。
- [ ] 命中 Skill 时才加载详情。
- [ ] 未命中 Skill 时上下文 token 增量可控。
- [ ] Skill 详情注入对 send/send_stream 一致。
- [ ] `/skills`、`/skill <name>`、`/skill reload` 可用。
- [ ] `get_context_info()` 能展示 Skill token 占用（第二阶段）。
- [ ] 测试覆盖 loader、matcher、renderer、Agent 注入与命令。
