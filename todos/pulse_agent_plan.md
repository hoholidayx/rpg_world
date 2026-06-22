# RPG Agent Pulse 功能实现计划

## 概述

Pulse 是一套让 RPG 世界在玩家离线或不在 Telegram 前台时仍能“轻量流动”的后台任务机制。它允许用户定义自动任务，根据时间流逝、玩家空闲时长、世界状态或后续条件触发剧情观察、剧情提案、主动提醒，最终可以在受控模式下自动推进低风险世界事件，并通过 Telegram 通知玩家。

第一版目标不是让 AI 替玩家玩游戏，而是让世界在玩家不操作时产生可感知的动态：天气变化、NPC 行动、约定时间临近、线索窗口期、地点状态变化等。玩家角色的重大选择、行动、承诺和命运仍必须由玩家决定。

## 核心目标

- 支持在 `settings.yaml` 中定义 Pulse 自动任务。
- 支持后台 scheduler 在 Telegram 进程中运行，并复用现有 Telegram adapter 主动发送通知。
- 支持基于 interval、idle、daily 的第一批触发器。
- 支持 `notify_only`、`propose`、`advance` 三种执行模式，其中第一版默认 `propose`。
- 支持 quiet hours、cooldown、每日上限、重要性阈值、去重等打扰控制策略。
- 支持把每次 Pulse 执行写入审计日志，避免重启后重复触发或无法追溯。
- 支持通过 Telegram 命令暂停、恢复、查看任务、确认或拒绝剧情提案。
- 所有会写入 RPG 状态或历史的操作必须走 agent/session 的正式入口，不能由 Telegram 或 scheduler 直接改文件。

## 非目标

- 第一版不做完整 cron 表达式解析。
- 第一版不做任意 Python 表达式条件触发。
- 第一版不允许后台任务替玩家角色行动、说话或作出重大选择。
- 第一版不做 WebUI 配置编辑页面，只保留后续扩展点。
- 第一版不做跨进程分布式调度；同一个 Telegram bot 进程内负责自己的 Pulse 任务。
- 第一版不默认启用 `advance` 自动写入模式。

## 产品语义

### Pulse

一次后台自动触发的世界脉冲。它通常包含四个阶段：

1. 触发：scheduler 判断某个 task 到点或满足条件。
2. 观察：executor 收集当前 workspace、session、场景、历史、状态、记忆摘要。
3. 决策：LLM 或规则策略判断是否需要通知、是否生成剧情提案、是否允许自动推进。
4. 执行：写审计记录，必要时调用 agent，最后通过 Telegram 通知用户。

### Pulse Task

用户配置的一条后台自动任务。它定义触发条件、目标 session、执行模式、LLM prompt、通知目标和安全策略。

### Pulse Event

一次 task 实际触发后的审计记录。无论执行结果是 skipped、notified、proposed、advanced 还是 failed，都需要记录。

### Pulse Proposal

`propose` 模式下生成的待确认剧情提案。提案只进入 pending store，不直接写入正式历史。用户通过 `/pulse_accept <proposal_id>` 确认后才会进入正式剧情。

## 用户体验设计

### notify_only 模式

只发送提醒，不写入剧情历史。

示例通知：

```text
🌙 RPG Pulse
距离你上次行动已经过去 6 小时。
当前场景仍停留在雨夜码头。黑色货船预计 30 分钟后离港。
```

适合：约定提醒、现实时间提醒、每日摘要、冷却状态提示。

### propose 模式

生成剧情动向提案，但等待玩家确认。

示例通知：

```text
🌙 RPG Pulse：世界动向提案

你离开码头这段时间，世界可能出现了这些变化：
1. 雨势增强，东侧仓库附近能见度下降。
2. 守夜人发现二号码头的灯光异常。
3. 你的联系人仍未出现，约定时间只剩 20 分钟。

是否将这些变化写入当前剧情？
/pulse_accept p_20260622_001
/pulse_reject p_20260622_001
```

适合：第一版默认模式。它让世界显得活跃，但仍保留玩家确认权。

### advance 模式

自动写入低风险世界变化，然后通知玩家。

示例通知：

```text
🌙 RPG Pulse：世界已自动推进

雨势在午夜前加重。港口东侧临时增加了巡逻，黑色货船提前开始装货。

已写入当前剧情。你可以继续行动，或使用 /pulse_undo 查看后续撤销能力。
```

适合：后续成熟阶段。必须带强策略限制和审计能力。

## 配置设计

Pulse 属于业务自动任务和渠道行为，应放在 `settings.yaml`，不放进 `llm.yaml`。LLM provider 仍通过已有 `llm.yaml` 的 biz key 管理。

建议配置结构：

```yaml
base:
  pulse:
    enabled: true
    tick_seconds: 60
    default_timezone: "Asia/Shanghai"
    store_retention_days: 30

    tasks:
      - id: idle_world_pulse
        enabled: true
        trigger:
          type: idle
          after: "6h"

        target:
          channel: telegram
          bot: main
          chat_id_env: "RPG_WORLD_TELEGRAM_OWNER_CHAT_ID"
          workspace: "data/非公开行程"
          session_id: "telegram_main_default"

        behavior:
          mode: propose
          provider_biz_key: agent.main
          max_context_chars: 12000
          prompt: |
            玩家已经一段时间没有继续 RPG。
            请根据当前场景、历史、状态和记忆，判断世界是否出现值得提醒玩家的轻微变化。
            不要替玩家角色行动，不要解决主要冲突。
            如果没有值得提醒的变化，返回 should_notify=false。

        policy:
          max_runs_per_day: 3
          min_interval_between_runs: "1h"
          min_interval_between_notifications: "3h"
          quiet_hours:
            timezone: "Asia/Shanghai"
            start: "23:30"
            end: "08:30"
          require_importance_score: 0.6
          skip_if_agent_busy: true
          dedupe_window: "12h"

        notify:
          telegram:
            prefix: "🌙 RPG Pulse"
            important_only: true
```

### 字段说明

- `pulse.enabled`：全局开关。
- `pulse.tick_seconds`：scheduler 主循环检查间隔。
- `task.id`：稳定任务 ID，只允许字母、数字、下划线和短横线。
- `trigger.type`：第一版支持 `interval`、`idle`、`daily`。
- `target.channel`：第一版只支持 `telegram`。
- `target.bot`：匹配 Telegram bot 配置中的 `name`。
- `target.chat_id` / `chat_id_env`：通知目标 Telegram chat。
- `target.workspace`：目标 RPG workspace。
- `target.session_id`：目标 session。
- `behavior.mode`：`notify_only`、`propose`、`advance`。
- `behavior.provider_biz_key`：Pulse planner 使用的 LLM biz key，默认 `agent.main`。
- `policy`：打扰控制、安全限制和去重策略。

## 核心模块设计

新增目录：

```text
rpg_world/rpg_core/pulse/
  __init__.py
  config.py
  models.py
  scheduler.py
  trigger.py
  executor.py
  planner.py
  policy.py
  store.py
  activity.py
  notifier.py
```

### models.py

定义核心数据结构：

- `PulseTaskConfig`
- `PulseTriggerConfig`
- `PulseTargetConfig`
- `PulseBehaviorConfig`
- `PulsePolicyConfig`
- `PulseNotifyConfig`
- `PulseTaskState`
- `PulseEvent`
- `PulseProposal`
- `PulseDecision`
- `PulseRunResult`

建议 `PulseDecision` 使用结构化字段：

```python
@dataclass(frozen=True)
class PulseDecision:
    should_notify: bool
    importance_score: float
    summary: str
    proposed_changes: list[str]
    requires_confirmation: bool
    dedupe_key: str = ""
```

### config.py

职责：

- 从 `settings.yaml` 的 `pulse` 节解析配置。
- 做字段类型转换，例如 `6h`、`30m`、`1d`。
- 校验 task id、trigger、target、mode、policy。
- 返回 typed config，不让业务代码直接读 YAML dict。

建议增加 `Settings.pulse_settings` 属性，保持和现有配置访问风格一致。

### scheduler.py

职责：

- 维护后台主循环。
- 周期性检查 enabled tasks。
- 为 due task 调用 executor。
- 控制同一个 task/session 不并发运行。
- 支持 stop event 和 graceful shutdown。

伪代码：

```python
class PulseScheduler:
    async def start(self) -> None:
        while not self._stopped:
            now = self._clock.now()
            for task in self._tasks:
                if self._trigger.is_due(task, now):
                    await self._run_due_task(task, now)
            await asyncio.sleep(self._tick_seconds)

    async def stop(self) -> None:
        self._stopped = True
        await self._drain_running_tasks()
```

### trigger.py

第一版 trigger：

#### interval

按照上次运行时间计算：

```yaml
trigger:
  type: interval
  every: "30m"
```

#### idle

基于目标 session 或目标 chat 的最后活跃时间计算：

```yaml
trigger:
  type: idle
  after: "6h"
```

idle 判断需要依赖 `PulseActivityStore`。

#### daily

每天固定本地时间触发：

```yaml
trigger:
  type: daily
  at: "21:00"
  timezone: "Asia/Shanghai"
```

第一版可以不做 missed-run 补偿。进程停机期间错过的 daily 任务不补发，避免重启后刷屏。

### policy.py

职责：

- 判断 quiet hours。
- 判断每日运行上限。
- 判断通知 cooldown。
- 判断 importance threshold。
- 判断 dedupe key 是否重复。
- 判断 agent 是否繁忙时是否跳过。

建议所有 skip 都返回明确 reason，例如：

- `disabled`
- `quiet_hours`
- `daily_limit`
- `cooldown`
- `duplicate`
- `agent_busy`
- `low_importance`

### store.py

持久化路径建议：

```text
<workspace_root>/sessions/<session_id>/pulse/
  task_state.json
  events.jsonl
  proposals.jsonl
  activity.json
```

存储语义：

- `task_state.json`：每个 task 的 last_run、last_notify、failure_count、dedupe cache。
- `events.jsonl`：完整审计日志，append-only。
- `proposals.jsonl`：待确认或已处理的提案。
- `activity.json`：最后活跃时间，可按 channel/chat/session 记录。

写入要求：

- JSONL append 要尽量原子化。
- task state 更新要使用临时文件 + replace。
- store 读失败时不能导致 Telegram 主流程不可用，应记录 warning 并跳过本次 pulse。

### activity.py

记录玩家活跃时间。

第一版建议在 Telegram adapter 收到有效用户消息后记录：

- channel = telegram
- bot name
- chat_id
- user_id
- workspace
- session_id
- last_active_at

这可以先由 Telegram runner 或 adapter 调用 `PulseActivityStore.touch(...)`，后续再抽象为通用 channel activity hook。

### planner.py

负责 LLM 决策。

第一版建议 planner 输出 JSON，executor 严格解析。

Prompt 要求：

- 不替玩家行动。
- 不替玩家说话。
- 不解决关键冲突。
- 不创造与世界书/角色卡冲突的设定。
- 只推进环境、NPC、外部事件、时间流逝。
- 输出 importance_score、should_notify、summary、proposed_changes、requires_confirmation。

JSON 示例：

```json
{
  "should_notify": true,
  "importance_score": 0.72,
  "summary": "雨势增强，码头巡逻增加，联系人仍未出现。",
  "proposed_changes": [
    "雨势增强",
    "二号码头巡逻增加",
    "联系人仍未出现"
  ],
  "requires_confirmation": true,
  "dedupe_key": "dock_rain_patrol_contact_missing"
}
```

解析失败策略：

- `notify_only`：发送一条安全 fallback 或直接 skipped。
- `propose`：不写 proposal，记录 failed event。
- `advance`：必须失败，不允许从非结构化文本自动写入。

### executor.py

执行流程：

1. 加载 task state。
2. policy pre-check。
3. 根据 target 获取 agent。
4. 构建 Pulse 上下文。
5. 调 planner 得到 decision。
6. policy post-check。
7. 按 mode 执行。
8. 通知 Telegram。
9. 写 event 和 state。

#### notify_only 执行

- 不调用 `agent.send()` 写历史。
- 可以调用 planner，也可以纯规则。
- 仅通过 notifier 发送 summary。

#### propose 执行

- planner 生成 proposal。
- proposal 写入 pending store。
- Telegram 通知中包含确认/拒绝命令。
- 不写正式 history。

#### advance 执行

- 只允许在配置显式开启时执行。
- executor 将 pulse 事件包装为特殊输入，调用 agent 正式入口。
- 写入 event，通知用户。

建议后续给 `RPGGameAgent` 增加显式方法：

```python
async def pulse(self, pulse_input: PulseInput) -> PulseAgentResult:
    ...
```

第一版也可以内部复用 `send()`，但 prompt 必须带明确系统边界，并且消息内容应可识别为 Pulse 自动事件。

## Telegram 集成设计

新增：

```text
rpg_world/channels/telegram/pulse.py
```

内容：

- `TelegramPulseNotifier`
- `build_pulse_scheduler_for_bot(...)`
- Telegram command helper，可选

### TelegramPulseNotifier

职责：

- 接收 `chat_id` 和文本。
- 调用现有 adapter 的 `send_text()`。
- 不处理 LLM、不处理 task policy。

伪代码：

```python
class TelegramPulseNotifier:
    def __init__(self, adapter: TelegramAdapter) -> None:
        self._adapter = adapter

    async def notify(self, chat_id: str, text: str) -> None:
        await self._adapter.send_text(chat_id, text)
```

### runner 接入

修改 `rpg_world/channels/telegram/runner.py`：

- `_BotRuntime` 增加 `pulse_task` 字段。
- 每个 enabled bot 启动 adapter 后，按 bot 过滤 pulse tasks。
- 如果有匹配任务，创建 scheduler task。
- shutdown 时先 stop scheduler，再 stop adapter。

注意：Pulse scheduler 应跟 Telegram bot 同进程，因为通知需要复用 adapter 发送消息。

## Agent 集成设计

### 第一版最小接入

第一版不改 `RPGGameAgent` 主流程，只在 propose 模式中读取上下文并生成提案。需要一个“只读上下文构建”入口，优先复用已有 context inspection 能力。

### 第二版正式接入

新增 `RPGGameAgent.pulse(...)`，让自动推进有独立入口。

建议语义：

- `pulse(..., mode="propose")`：只生成 proposal，不改 history。
- `pulse(..., mode="advance")`：走正式 turn 写入，但 role 或 metadata 标记为 pulse。
- 所有 pulse 执行都进入 agent 队列，避免和用户消息并发。

### 队列与并发

需要避免玩家消息和 Pulse 同时执行导致 session 状态竞争。

建议：

- `propose` 可以在 agent 空闲时运行。
- `advance` 必须进入 agent 队列。
- policy 支持 `skip_if_agent_busy`。
- 后续可增加低优先级队列，但第一版可以先跳过 busy agent。

## 命令设计

新增命令：

- `/pulse`：展示当前 session 的 Pulse 状态、最近 event、pending proposal。
- `/pulse_on`：开启当前 session 的 Pulse。
- `/pulse_off`：暂停当前 session 的 Pulse。
- `/pulse_pause <duration>`：暂停一段时间，例如 `/pulse_pause 24h`。
- `/pulse_tasks`：列出配置中的 Pulse tasks。
- `/pulse_accept <proposal_id>`：确认提案并写入剧情。
- `/pulse_reject <proposal_id>`：拒绝提案。
- `/pulse_run <task_id>`：手动触发某个 task，便于调试。

命令必须接入核心 command dispatcher。Telegram 只负责转发命令，不直接修改 Pulse store 或 session。

## Telegram 交互增强

第一版可以先用纯文本命令确认。

后续可以增加 inline keyboard：

- ✅ 写入剧情
- ❌ 忽略提案
- ⏸ 暂停 24 小时

Callback data 不应直接承载完整 proposal id，而应使用短 token 映射到 core pending proposal，避免 Telegram callback 长度限制和泄露内部路径。

## 安全边界

Pulse prompt 必须包含以下硬约束：

- 你不是玩家角色。
- 你不能替玩家行动。
- 你不能替玩家说话。
- 你不能替玩家作出承诺、战斗、交易、告白、杀戮、逃跑等重大选择。
- 你不能跳过关键冲突。
- 你不能永久改变玩家角色状态。
- 你不能创造与世界书、角色卡、已发生历史冲突的设定。
- 你可以推进时间、环境、NPC 外部行动、公共事件和线索窗口。

`advance` 模式还需要额外限制：

- 只能写入低风险变化。
- 必须输出变更摘要。
- 必须记录 event id。
- 必须可审计。

## 审计与可观测性

每次 Pulse event 至少记录：

- `event_id`
- `task_id`
- `workspace`
- `session_id`
- `channel`
- `chat_id`
- `trigger_type`
- `trigger_reason`
- `mode`
- `started_at`
- `finished_at`
- `status`
- `skip_reason`
- `importance_score`
- `dedupe_key`
- `proposal_id`
- `notified`
- `model`
- `usage`
- `error`

日志级别建议：

- due task：info
- skipped by policy：debug 或 info
- notification failed：warning
- planner parse failed：warning
- advance failed：error

## 测试计划

### 配置测试

- 缺少 `pulse` 配置时默认 disabled。
- task id 非法时报错。
- interval / idle / daily trigger 解析正确。
- duration 字符串 `30m`、`6h`、`1d` 解析正确。
- unknown mode 报错。
- Telegram target 缺 chat_id 和 chat_id_env 时报错。

### Trigger 测试

- interval 到点触发，未到点不触发。
- idle 基于 last_active_at 触发。
- daily 在指定 timezone 和时间触发。
- 进程重启后根据 store 中 last_run 避免重复触发。

### Policy 测试

- quiet hours 内跳过。
- daily limit 达到后跳过。
- notification cooldown 内跳过。
- importance score 低于阈值跳过。
- dedupe key 在窗口内重复时跳过。
- agent busy 且 `skip_if_agent_busy=true` 时跳过。

### Store 测试

- event JSONL append 成功。
- task state 原子更新。
- proposals 可创建、确认、拒绝、过期。
- 损坏 state 文件时安全失败，不影响主 Telegram 进程。

### Planner 测试

- 合法 JSON decision 能解析。
- 非法 JSON 会失败且不写 proposal。
- missing required fields 会失败。
- importance_score 会 clamp 或校验在 0~1。
- prompt 包含禁止替玩家行动的约束。

### Executor 测试

- notify_only 只通知，不写 proposal，不写 history。
- propose 写 proposal 并通知。
- propose 在 low importance 下不通知。
- advance 默认 disabled 或需要显式开启。
- Telegram 发送失败时 event 记录 failed_notify。

### Telegram 测试

- runner 会为匹配 bot 的 pulse task 启动 scheduler。
- runner shutdown 会停止 scheduler。
- notifier 调用 adapter.send_text。
- `/pulse_on`、`/pulse_off`、`/pulse_tasks`、`/pulse_accept`、`/pulse_reject` 被正常分发。
- inline keyboard 后续实现时，callback 能转成核心命令。

### Agent 集成测试

- Pulse 执行不会绕过 agent 队列。
- session 未变时不会重复重建 MemoryManager。
- propose 不修改 history。
- accept 后通过正式入口写入 history。
- 玩家消息与 pulse 同时到来时不会破坏 session 状态。

## 实现顺序

### 阶段 1：配置与纯调度骨架

1. 新增 `rpg_core/pulse/models.py`。
2. 新增 `rpg_core/pulse/config.py`。
3. 在 settings 中增加 `pulse_settings` typed accessor。
4. 新增 duration parser。
5. 新增 `PulseScheduler` 空执行器版本。
6. 补配置和 scheduler 单元测试。

验收标准：

- 可以从配置读出 enabled tasks。
- scheduler 可以判断 due task，并调用 fake executor。
- 不接 Telegram，不调用 LLM。

### 阶段 2：Store、Policy、Trigger

1. 新增 `PulseStore`。
2. 新增 `PulsePolicy`。
3. 实现 interval、idle、daily trigger。
4. 新增 activity store。
5. 补 store、policy、trigger 测试。

验收标准：

- 重启不会重复触发 interval task。
- idle 能根据 last_active_at 判断。
- quiet hours、cooldown、daily limit 生效。

### 阶段 3：Telegram notify-only

1. 新增 `channels/telegram/pulse.py`。
2. 修改 Telegram runner，按 bot 启动 scheduler。
3. 实现 `TelegramPulseNotifier`。
4. 实现固定文本 notify_only task。
5. 补 Telegram runner 生命周期测试。

验收标准：

- Telegram bot 启动后 pulse scheduler 同进程运行。
- 到点后能主动向配置的 chat_id 发消息。
- 关闭 Telegram runner 时 scheduler 被优雅停止。

### 阶段 4：LLM propose

1. 新增 `PulsePlanner`。
2. 设计 Pulse JSON prompt。
3. 解析 `PulseDecision`。
4. 实现 proposal store。
5. 实现 `/pulse_accept`、`/pulse_reject`。
6. propose 通知中带 proposal id。

验收标准：

- Pulse 可以生成待确认剧情提案。
- 未确认前不写入正式 history。
- accept 后才写入。
- reject 后 proposal 标记为 rejected。

### 阶段 5：Agent pulse 正式入口

1. 给 `RPGGameAgent` 增加 `pulse()` 或等价低优先级队列入口。
2. 给 pulse 写入加 metadata 或可识别前缀。
3. accept/advance 复用正式 session append 和自动压缩链路。
4. 补 agent 集成测试。

验收标准：

- Pulse 写入不会绕过 session manager。
- 自动推进内容能被后续 context、summary、memory 正常看到。
- 玩家消息和 pulse 不会并发破坏状态。

### 阶段 6：advance 模式

1. 增加显式配置开关 `allow_advance: true`。
2. 增加 advance prompt 更严格约束。
3. 增加 event audit 和可选 undo 预留字段。
4. 增加高风险内容拦截策略。

验收标准：

- 默认不启用 advance。
- 开启后只能自动写入低风险外部事件。
- 所有自动写入都有 event id 和审计记录。

## 文件变更清单建议

第一批可能涉及：

```text
rpg_world/rpg_core/pulse/__init__.py
rpg_world/rpg_core/pulse/models.py
rpg_world/rpg_core/pulse/config.py
rpg_world/rpg_core/pulse/scheduler.py
rpg_world/rpg_core/pulse/trigger.py
rpg_world/rpg_core/pulse/policy.py
rpg_world/rpg_core/pulse/store.py
rpg_world/rpg_core/pulse/activity.py
rpg_world/rpg_core/settings.py
rpg_world/settings.yaml
rpg_world/channels/telegram/pulse.py
rpg_world/channels/telegram/runner.py
rpg_world/rpg_core/agent/command.py
rpg_world/rpg_core/agent/agent.py
rpg_world/rpg_core/tests/test_pulse_config.py
rpg_world/rpg_core/tests/test_pulse_scheduler.py
rpg_world/rpg_core/tests/test_pulse_store.py
rpg_world/rpg_core/tests/test_pulse_executor.py
rpg_world/channels/tests/test_telegram_pulse.py
```

## 迁移与默认行为

- 默认 `pulse.enabled=false`，避免部署后突然发通知。
- 示例配置可以放在 `settings.local.example.yaml`。
- 如果没有 Telegram chat_id，task 应 disabled 或启动时报清晰错误。
- 如果 Telegram bot 未启用，对应 task 应 skipped，不影响其他 bot。
- 如果 LLM provider 不可用，propose / advance task 记录 failed event，不影响普通聊天。

## 风险与缓解

### 风险：自动剧情破坏玩家 agency

缓解：第一版默认 propose；advance 必须显式开启；prompt 严禁替玩家行动。

### 风险：通知轰炸

缓解：quiet hours、cooldown、daily limit、importance threshold、dedupe key。

### 风险：状态竞争

缓解：Pulse 写入走 agent 队列；busy 时跳过或延迟。

### 风险：重启重复通知

缓解：task_state 记录 last_run / last_notify / dedupe cache。

### 风险：Telegram 发送失败阻塞 scheduler

缓解：复用 adapter 超时机制；失败写 event；scheduler 继续后续 task。

### 风险：配置泄露 chat_id 或 token

缓解：支持 `chat_id_env`；bot token 仍沿用现有 token_env 机制。

## 推荐第一版 MVP

MVP 只做以下内容：

1. `pulse.enabled` 和 task 配置解析。
2. interval + idle trigger。
3. store 记录 last_run 和 events。
4. Telegram notify-only 主动发送固定模板消息。
5. `/pulse_on`、`/pulse_off`、`/pulse_tasks`。
6. quiet hours + cooldown。

MVP 不做：

- LLM planner。
- propose。
- advance。
- inline keyboard。
- condition trigger。

MVP 通过后，再进入 propose 阶段。

## 最终体验愿景

当玩家离开 Telegram 后，RPG 世界不会完全静止。系统会在合适时间检查世界状态，并只在确实有值得玩家知道的变化时轻量提醒：某个 NPC 等得不耐烦、雨夜码头的船即将离港、宴会开始进入第二幕、追兵搜索范围扩大、约定期限临近。

玩家仍然掌握主角的行动权。Pulse 只是让世界继续呼吸，并在关键时刻把“世界正在变化”这件事带回玩家的注意力中。
