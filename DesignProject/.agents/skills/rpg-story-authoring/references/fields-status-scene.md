# 状态表与 Scene 字段

> authoringRulesVersion=1.5 · catalogDigest=da18005df6206dc24ecd2e38e0db4a22ebfb644eaf898a651b70d17d2005db35

本文由 RPG World 字段语义单一真源生成；不要手工修改。

## 跨字段原则

### 状态值即时判断

所有状态 value 都在 neutral、ic 或 gm 的当前正文 turn 根据明确事实判断更新。整表共同语义、value 格式和即时更新规则写入 description；row.updateRule 只补充字段专属条件，不预设数值模型。状态表保存需要每轮可见和更新的当前状态；Memory 更适合按时间累积的叙事历史，但当前事实仍可成为状态字段。

运行时影响：StatusSubAgent 在 neutral、ic 或 gm 正文 turn 按目标即时处理状态；OOC 与命令不推进状态事实。

### 普通状态表允许字段级运行时 CRUD

neutral、ic 或 gm 正文 turn 可在已有 normal Session 状态表内按明确事实创建、读取、更新、改名和删除字段，但不能创建、删除或重命名整张表。读取来自每轮完整状态 Context；结构变化只用于当前事实模型，不把状态表变成历史流水。OOC 与命令只读。

运行时影响：已有字段 value 使用 status_table_set_values；字段新增、改名或删除使用 status_table_edit_fields，并与消息一起在 turn 事务中提交。runtimeKeyLocked=true 只禁止该字段改名和删除，不限制 value 更新或同表新增其他字段。Scene 不继承 normal 权限，仍遵循 agent.scene.allow_runtime_key_changes。

## 字段规则

| 对象 | 路径 | 应填写 | 避免 | 运行时影响 |
| --- | --- | --- | --- | --- |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/key` | 状态字段名；同一表内唯一。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/runtimeKeyLocked` | 为 true 时只保护该字段不被运行时删除或重命名；仍允许更新 value，也不妨碍同表新增其他未锁字段。 | 不要把它理解为 value 只读，也不要理解成禁止同表新增其他字段。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/updateRule` | 只写该字段专属的额外即时语义条件；整表共同规则写入表 description。不得写频率、延迟、后台调度、人工只读或数据库权限。留空时使用“事实明确且值实际变化”的通用规则。 | 不要重复表 description 的共同规则，也不要预设 value 是数值或写每 N 回合、延迟、定时、manual 或 read-only 规则；不要用无事实变化的 Scene 更新轮询 Plot。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusRowSpec` | `/resources/statusTables/*/rows/*/value` | 当前初始值，以字符串表达；可按表约定表示数值、枚举、列表、简短描述或当前事实状态。运行时可在本 turn 依据已确认事实即时更新。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/characterRef` | 可选的同 Story 角色 stableId，用于角色状态分组。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/description` | 说明该表追踪什么，并集中写整表共同语义、value 格式和即时更新规则；字段专属条件写入 row.updateRule。normal 表若存在无法预先穷举的字段，还应说明动态 key 的业务域、命名与 value 格式，以及创建、改名和删除条件；无需预定义全部未来字段。 | 不要逐字段复制相同规则，也不要把表当作无限追加的历史流水。当前事实、承诺、联系或事件状态可以成为字段；按时间累积的叙事历史更适合 Memory。normal 表需要动态字段时，不要省略可创建字段的领域、格式与删除边界。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/metadata` | 仅放没有正式字段承载的中立扩展数据。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/name` | 面向作者和管理界面的名称。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/rows` | 该状态表的有序字段定义。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/sortOrder` | 稳定显示顺序；数值越小越靠前。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/stableId` | 跨 revision、分包和运行时绑定保持稳定的文本 ID。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |
| `StatusTableSpec` | `/resources/statusTables/*/statusKind` | scene 表示当前场景；normal 表示普通 Story/角色状态。 | 不要把其他正式字段的职责塞入此字段，也不要保存聊天原文。 | 创建 Session 时复制；neutral、ic 或 gm 正文 turn 可即时更新 value。已有 normal Session 表还允许字段级创建、读取、更新、改名和删除；Scene 的结构权限继续由专用 Scene 配置控制。 |

## 自动诊断

| Rule ID | 级别 | 触发含义 | 修正建议 |
| --- | --- | --- | --- |
| `status.update-rule-scheduling` | warning | updateRule 疑似包含频率、延迟、定时或读写权限语义。 | 改写为当前非 OOC 正文 turn 的事实判定条件；删除每 N 回合、延迟、manual/read-only 等内容，也不要用无事实变化的 Scene 写入轮询 Plot。 |
| `status.scene-placeholder-year` | warning | Scene 时间使用了疑似占位年份。 | 若故事已锚定现实年代，使用 2019 年、2020 年等虚拟年份。 |
