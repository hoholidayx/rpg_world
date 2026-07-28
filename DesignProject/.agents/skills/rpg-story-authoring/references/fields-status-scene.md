# 状态表与 Scene 字段

> authoringRulesVersion=1.2 · catalogDigest=2b31edf08c2ba281ceb1a8a6fa90937c42b3774f9162a82818d86ebdbc59af52

本文由 RPG World 字段语义单一真源生成；不要手工修改。

## 跨字段原则

### 状态值即时判断

所有状态 value 都在 neutral、ic 或 gm 的当前正文 turn 根据明确事实判断更新。整表共同语义、value 格式和即时更新规则写入 description；row.updateRule 只补充字段专属条件，不预设数值模型。状态表保存需要每轮可见和更新的当前状态；Memory 更适合按时间累积的叙事历史，但当前事实仍可成为状态字段。

运行时影响：StatusSubAgent 在 neutral、ic 或 gm 正文 turn 按目标即时处理状态；OOC 与命令不推进状态事实。

## 字段规则

| 对象 | 路径 | 应填写 | 避免 | 运行时影响 |
| --- | --- | --- | --- | --- |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/key` | 状态字段名；同一表内唯一。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/runtimeKeyLocked` | 只保护 key 不被运行时增删或改名，不锁定 value。 | 不要把它理解为 value 只读。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/updateRule` | 只写该字段专属的额外即时语义条件；整表共同规则写入表 description。不得写频率、延迟、后台调度、人工只读或数据库权限。留空时使用“事实明确且值实际变化”的通用规则。 | 不要重复表 description 的共同规则，也不要预设 value 是数值或写每 N 回合、延迟、定时、manual 或 read-only 规则；不要用无事实变化的 Scene 更新轮询 Plot。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/value` | 当前初始值，以字符串表达；可按表约定表示数值、枚举、列表、简短描述或当前事实状态。运行时可在本 turn 依据已确认事实即时更新。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/characterRef` | 可选的同 Story 角色 stableId，用于角色状态分组。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/description` | 说明该表追踪什么，并集中写整表共同语义、value 格式和即时更新规则；字段专属条件写入 row.updateRule。 | 不要逐字段复制相同规则，也不要把表当作无限追加的历史流水。当前事实、承诺、联系或事件状态可以成为字段；按时间累积的叙事历史更适合 Memory。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/rows` | 该状态表的有序字段定义。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |
| `StatusTableSpec` | `/resources/statusTables/*/statusKind` | scene 表示当前场景；normal 表示普通 Story/角色状态。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；value 可由状态 Agent 在 neutral、ic 或 gm 正文 turn 即时更新。 |

## 自动诊断

| Rule ID | 级别 | 触发含义 | 修正建议 |
| --- | --- | --- | --- |
| `status.update-rule-scheduling` | warning | updateRule 疑似包含频率、延迟、定时或读写权限语义。 | 改写为当前非 OOC 正文 turn 的事实判定条件；删除每 N 回合、延迟、manual/read-only 等内容，也不要用无事实变化的 Scene 写入轮询 Plot。 |
| `status.scene-placeholder-year` | warning | Scene 时间使用了疑似占位年份。 | 若故事已锚定现实年代，使用 2019 年、2020 年等虚拟年份。 |
