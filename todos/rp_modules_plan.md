# RP Modules：Narrative Outcome 与 Dice

## 当前定位

RP Modules 是围绕 RP 业务语义的玩法机制层，不是通用 Skill 系统。当前实现分成两层：

- `narrative_outcome`：面向自然剧情的五级随机裁定，是主 Agent 唯一使用的随机剧情工具。
- `dice`：底层随机、表达式解析和手动调试入口，不向主 LLM 暴露工具。

Scene Runtime、状态表、角色卡、世界书和文本输出格式仍是各自独立的核心能力，不并入 RP Module。

## Narrative Outcome

### 主 LLM 契约

主 LLM 只看到：

```text
rp_story_outcome(reason, actor?)
```

`reason` 描述一个尚未确定的外部实质变数，`actor` 仅在行动者明确时提供。工具 schema 不包含 Dice 表达式、DC、修正值、难度、权重或随机数。

每轮叙事前，主 Agent 必须结合用户完整语义、当前场景与状态判断是否存在外部实质变数：

- 同一行动或场景决策存在两个以上合理结果。
- 结果尚未由上下文唯一确定。
- 结果受未知信息、能力、阻力、风险、时机、环境条件或 NPC/世界反应影响。
- 不同结果会实质改变剧情走向、获得的信息、风险或代价。

满足这些条件时，即使没有骰子关键词，也在描述结果前调用一次工具。明确要求掷骰、检定、碰碰运气或随机决定时，本轮 runtime section 会进一步强制调用。

以下情况不裁定：

- 玩家角色的内心、台词、选择或其它角色主权内容。
- 上下文已经确定的结果。
- 无有效阻力、无实质后果的日常动作。
- 纯表达或不会改变剧情的信息重复确认。

### 五档结果

| code | 展示名 | 系统默认 | 叙事约束 |
|---|---|---:|---|
| `critical_success` | 大成功 | 5% | 超额达成，并获得额外机会、信息或优势 |
| `success` | 成功 | 25% | 达成目标，不附加重大代价 |
| `success_with_cost` | 成功但有代价 | 40% | 达成目标，同时引入相称代价或复杂化 |
| `setback` | 失败但推进 | 25% | 未达成目标，但提供新信息、替代路径或下一步行动 |
| `critical_failure` | 重大失败 | 5% | 引入严重后果，但不自动死亡、硬停局或永久剥夺玩家角色主权 |

抽样使用有效五档权重的 `1..100` 累计区间。工具只返回 `outcomeCode`、中文标签、叙事指导、`reason` 和可选 `actor`；内部 sample 与权重不进入 LLM 或玩家界面。

### Turn 生命周期

每个自动剧情 turn 最多一条裁定：

1. `AgentTurnTransaction.begin()` 创建 `TurnScratch`。
2. 编排层在 Context 门禁前解析不可变 module snapshot，`NarrativeOutcomeModule.bind_turn()` 只接收该快照中的有效权重，不再读取数据库。
3. 第一次工具调用抽取并暂存结果；同 turn 后续调用复用该结果。
4. 主回复完整成功后，消息、裁定和状态表在同一个短 `database.atomic()` 中提交。
5. 取消、provider 错误或 commit 失败丢弃 scratch，不保留裁定。

retry/edit 使用既有 truncate 流程。删除旧 turn 时同步删除该 turn 及之后的裁定；重新生成会重新抽取。clear、用户消息内容编辑和单条历史删除也会清理关联裁定。

### 配置与覆盖

canonical 配置：

```yaml
rp_modules:
  enabled: true
  modules:
    narrative_outcome:
      enabled: true
      auto_adjudication_enabled: true
      default_weights:
        critical_success: 5
        success: 25
        success_with_cost: 40
        setback: 25
        critical_failure: 5
    dice:
      enabled: true
      default_dc: 12
      max_dice_count: 100
      max_die_sides: 1000
```

模块配置优先级为 `config < story < session`，普通字段逐字段继承，`weights` 作为完整五项的原子字段。五项必须是 `0..100` 整数，总和严格等于 `100`。

旧 `dice.allow_auto_checks` 已移除；自动剧情裁定只使用 `narrative_outcome.auto_adjudication_enabled`。

### 持久化与 API

迁移 `0005_rp_modules.sql` 增加：

- `rpg_rp_module_catalog`
- `rpg_story_rp_modules`
- `rpg_session_rp_module_overrides`
- `rpg_session_narrative_outcomes`，唯一约束 `(session_id, turn_id)`

旧 Story/Session Narrative Outcome 权重列不保留；选择由不可变 module snapshot 负责。

Play API：

- `GET /play-api/v1/rp-modules/catalog`
- `GET/PATCH /play-api/v1/workspaces/{workspace_id}/stories/{story_id}/rp-modules[/{module_name}]`
- `GET/PATCH/DELETE /play-api/v1/sessions/{session_id}/rp-modules[/{module_name}]`
- `history` / `history-page` 的每个 `PlayTurn` 带 nullable `outcome`

响应包含模块定义、系统配置、Story 挂载/配置、Session 覆盖、有效配置与字段来源。

### Play WebUI

- Story 编辑页直接编辑五项整数比例；总和不是 100 时禁止保存，可恢复系统默认。
- Session 设置菜单打开独立覆盖弹窗；启用覆盖时复制当前有效比例，可清除覆盖并继承 Story。
- 流式 `rp_story_outcome` 结果渲染为专用剧情裁定卡，只显示等级、原因和 actor。
- 卡片不受“展示工具”开关影响。
- 刷新和分页从持久化 `PlayTurn.outcome` 恢复，并按数值 `turnId` 与本地流式卡去重。
- 时间线固定排序：用户行动 → 剧情裁定卡 → 主 Agent 叙事。

## Dice

Dice 继续支持：

- 表达式：`d20`、`1d20`、`2d6+3`、`4d6-2`、`1d100`
- `/roll <expr> [reason]`
- `/check_dc <expr> [dc=<n>] [reason]`

`default_dc` 仅服务手动 `/check_dc`；省略 `dc` 时使用配置值。`max_dice_count` 和 `max_die_sides` 是输入安全限制。

`DiceRollTool` 与 `DiceCheckDCTool` 作为底层可测试能力保留，但 `DiceModule.get_tools()` 返回空列表，因此主 Agent schema 不会出现 `rp_dice_roll` 或 `rp_dice_check_dc`。

手动 Dice 不写 Narrative Outcome 表，不写普通状态表，不修改 Scene Runtime，也不做 JSONL 审计。

## 验收边界

- 抽样测试覆盖五档累计区间、零权重、边界值、默认分布和注入 RNG。
- 模块测试覆盖同 turn 幂等与工具返回不泄露 sample/weights。
- 数据测试覆盖权重校验、三级优先级、清除覆盖、typed JSON 和唯一 turn。
- Agent 集成测试覆盖唯一主 LLM 工具、结果回灌、成功提交、取消丢弃、commit 回滚与 truncate 后重抽。
- API 契约覆盖 Story/Session GET/PATCH、422、继承来源和 history-page outcome。
- WebUI 以生产构建验证比例编辑、继承弹窗、流式/持久化卡片类型链路。
