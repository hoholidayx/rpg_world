# Play WebUI 稳定性优先的 5 天迭代计划

更新时间：2026-07-29

状态：Day 1 已完成，Day 2 待执行

执行投入：单一 Codex Sol Max 主执行通道

交付目标：第 5 天达到内部灰度标准

## 1. 目标与优先级

本轮只加固现有 `SessionRoom` 主体验，不开发独立沉浸式路由。优先级固定为：

1. 聊天、流式生成、停止和历史恢复稳定。
2. Media、TTS、Dream、Plot 等可选能力故障不阻塞基础游玩。
3. 桌面体验优先，同时保证手机可完成核心操作。
4. 建立可重复的前端自动化门禁。
5. 在不牺牲正确性的前提下改善首屏性能和核心交互。

时间不足时，依次放弃视觉润色、首屏体积优化和非核心组件测试；聊天正确性、故障
隔离和自动门禁不可削减。

## 2. 已知基线

- 基线分支与提交：`main` / `d52a6f5`。
- `play_webui` 生产构建通过。
- 在完成 Next 类型生成后，`tsc --noEmit` 通过。
- 当前 `lint` 使用已废弃的 `next lint`，会进入交互式配置，不能进入 CI。
- 当前没有 Play WebUI 自动化测试文件或测试命令。
- `/session/[sessionId]` 当前构建结果约为 `250 kB First Load JS`，是最重路由。
- `SessionRoom.tsx`、`SessionTimeline.tsx` 和
  `useSessionStreamTurn.ts` 均为约 800–900 行的高风险热点。
- `todos/architecture_hardening/phase_2_strict_contracts_and_ci.md` 中的
  Play WebUI CI 工作包尚未完成；本轮吸收该工作包，但不夹带其它后端工作包。

## 3. 范围与红线

### 本轮包含

- SessionRoom 核心聊天状态机和恢复路径。
- 可选服务的局部 loading/error/retry 与故障隔离。
- 桌面核心体验、390 px 手机可达性和基础无障碍。
- ESLint、类型检查、前端测试、生产构建和 CI。
- 非核心工作台按需查询、按需加载。

### 本轮不包含

- 独立沉浸式页面、Sprite、动态行动建议和 Status semantic。
- 新的后端模型、数据库 Schema 或迁移。
- HTTP、SSE、消息、Session 或持久化公开契约变更。
- SessionRoom 大爆炸重写或仅为缩短文件进行的机械拆分。
- 新的全局状态库、服务端轮询、错误内容持久化或 localStorage 状态恢复。

必须保持：

- 只有服务端确认 `cancelled` 时才展示 stopped。
- ERROR、缺失 DONE、网络中断或取消不得伪装为成功提交。
- Context 达门禁阈值时阻止普通正文，但斜杠命令始终可执行。
- Media、TTS 和 Dream 不得进入 Agent turn、消息正文、metadata 或 localStorage。

## 4. 每日执行计划

### Day 1：可靠基线与自动门禁

任务：

- [x] 将 `lint` 从 `next lint` 迁移到 ESLint CLI，并增加匹配当前 Next.js 的
  flat config。
- [x] 增加 `test` 命令，采用 Vitest、React Testing Library 和 jsdom。
- [x] 增加 `typecheck` 命令：先执行 `next typegen`，再执行 `tsc --noEmit`，
  保证干净 checkout 可运行。
- [x] 增加聚合 `check` 命令，固定执行
  `lint → test → typecheck → build`。
- [x] 新增独立 Play WebUI CI job：
  `npm ci → lint → test → typecheck → build`。
- [x] 首批测试覆盖 SSE 解析、stream reducer、Context 输入门禁和历史消息映射。
- [x] 记录干净环境下的门禁结果与 Session 路由构建体积。

验收：

- [x] 所有命令非交互执行。
- [x] 不依赖既有 `.next`、本地 `.env`、Provider 密钥或已安装依赖。
- [x] 本地与 CI 使用相同命令且可重复通过。

### Day 2：核心聊天状态机

任务：

- [ ] 收敛发送、流式、停止、取消、ERROR、DONE 和组件卸载的状态转换。
- [ ] 保证同一 Session 同时只有一个活动请求，重复点击不会重复发送。
- [ ] 防止停止竞态、切换 Session 后旧请求回写，以及 local stream message
  与持久历史重复。
- [ ] DONE 后才刷新已提交历史和 Context preview。
- [ ] 刷新失败时保留已显示回复，提供明确重试，且不清空未提交草稿。
- [ ] 增加正常完成、Provider ERROR、停止成功、停止 stale/not-running、
  网络中断和 Session 切换测试。

验收：

- [ ] 每个流式请求最终只收敛到一个明确终态。
- [ ] ERROR、断流和取消不产生成功 UI 或虚构 committed turn。
- [ ] composer 在所有失败路径上都能恢复可用。
- [ ] 人工连续执行 20 个 turn，包含停止、retry、edit 和命令，不出现重复消息、
  消息丢失或永久锁定。

### Day 3：故障隔离与恢复体验

任务：

- [ ] 将 Media、TTS、Dream、Plot/Story 工作台错误限制在各自容器内。
- [ ] 仅在用户打开对应工作台时启用非核心查询。
- [ ] 对重型工作台组件使用动态加载，不进入 Session 核心首屏包。
- [ ] 为核心 Session、角色绑定和历史错误提供页面级恢复入口。
- [ ] 为局部服务错误提供独立 retry，不要求刷新整页。
- [ ] 统一错误层级：
  - 页面阻断：Session、角色或历史不可用。
  - 局部错误：Media、TTS、Dream、Plot 等能力不可用。
  - 短暂反馈：可恢复操作使用 toast。
- [ ] 增加可选服务不可用、恢复和重复重试测试。

验收：

- [ ] 分别关闭 Media、TTS、Dream 服务时，历史、发送和停止仍正常。
- [ ] 服务恢复后可在原页面重试局部能力。
- [ ] 局部失败不污染正文、消息 metadata 或持久状态。

### Day 4：桌面体验、手机可达性与性能

任务：

- [ ] 优化 Timeline、Composer、Context 指示器和工作台抽屉的布局稳定性。
- [ ] 避免流式内容增长导致操作区跳动或用户阅读位置被强制改变。
- [ ] 在 `390×844` 下完成角色绑定、输入、发送、停止、返回最新消息和关闭工作台。
- [ ] 处理手机软键盘遮挡、底部安全区和触控目标尺寸。
- [ ] 补齐核心对话框、错误恢复和停止后的可预测焦点行为。
- [ ] 确保隐藏区域不可被键盘访问。
- [ ] 验证 200% 字号、长文本、超长单词和 reduced motion。
- [ ] 比较构建产物，确保 Session First Load JS 不高于 `250 kB`，并确认非核心
  工作台已拆出首屏 chunk。

验收：

- [ ] `1440×900`、`2560×1440`、`390×844` 三个视口人工脚本通过。
- [ ] 无横向溢出、关键操作不可达、软键盘遮挡 composer 或未捕获控制台错误。
- [ ] 性能优化不改变查询、消息或流式语义。

### Day 5：回归与内部灰度

任务：

- [ ] 运行完整 Play WebUI 门禁和受影响的 Play API 合约测试。
- [ ] 使用真实本地服务执行第 6 节灰度脚本。
- [ ] 只修复 P0/P1 回归，不追加新体验或扩大范围。
- [ ] 记录基线对比、测试结果、已知问题、回滚方式和后续候选。
- [ ] 更新本文档状态与执行记录。

内部灰度门槛：

- [ ] lint、test、typecheck、build 全部通过。
- [ ] 固定人工脚本全部通过。
- [ ] 无消息丢失或重复、错误提交、composer 永久锁死。
- [ ] 可选服务故障不会拖垮基础聊天。
- [ ] 桌面和手机均可完成核心闭环。

## 5. 工程接口变更

- 后端 HTTP、SSE、消息、Session 和数据库契约保持不变。
- `play_webui/package.json` 新增 `test`、`typecheck`、`check`，并修复 `lint`。
- CI 新增 Play WebUI 独立门禁，任何一步失败阻止合并。
- 前端内部允许抽取明确的流式状态类型、纯函数和测试辅助器。
- TanStack Query 继续作为服务器状态真源。
- 可选工作台改为按需查询和动态加载。

## 6. 固定灰度脚本

### 核心会话

- [ ] 新 Session 完成“角色 → Opening”原子绑定。
- [ ] 普通、IC、OOC、GM 正文均可发送并提交。
- [ ] 斜杠命令正常，且 Context 达阈值后仍可执行。
- [ ] 正常流式完成后消息只出现一次，usage 和 committed turn 正确。
- [ ] 停止生成只在收到 `cancelled` 后显示 stopped。
- [ ] retry、edit、delete 后历史和当前页正确收敛。
- [ ] 历史前后翻页、返回最新页和页面刷新恢复正确。
- [ ] 切换 Session 时旧请求不会回写新 Session。

### 故障注入

- [ ] Agent/Provider ERROR 不留下成功消息或锁死 composer。
- [ ] 流中断或缺失 DONE 不显示成功。
- [ ] Media service 不可用时基础聊天正常。
- [ ] TTS service 不可用时基础聊天正常。
- [ ] Dream service 不可用时基础聊天正常。
- [ ] 局部服务恢复后可在原页面重试。

### 设备与可访问性

- [ ] `1440×900` 桌面核心闭环。
- [ ] `2560×1440` 桌面核心闭环。
- [ ] `390×844` 手机核心闭环与软键盘。
- [ ] 键盘完成对话框、发送、停止和关闭工作台。
- [ ] 200% 字号下关键操作可达。
- [ ] reduced motion 下无依赖动画才能完成的操作。

## 7. 提交拆分

建议每个提交只处理一个逻辑主题：

1. `chore: add play webui quality gates`
2. `test: cover session stream terminal states`
3. `fix: harden session stream and recovery flow`
4. `fix: isolate optional session workspace failures`
5. `perf: defer noncritical session workspaces`
6. `fix: improve session room responsive accessibility`

实际提交可以合并相邻的小改动，但不得把后端架构工作包或新产品能力夹带进来。

## 8. 跨会话接续规则

每次开始执行前：

1. 阅读根目录 `AGENTS.md`；若涉及启动流程、共享状态或 `AgentManager`，再完整阅读
   `CLAUDE.md`。
2. 执行 `git status --short`，保护用户已有改动。
3. 阅读本文档的“当前进度”和“执行记录”，从第一个未完成门禁继续。
4. 运行当天涉及范围的基线检查，既有失败先记录，不归因于本轮。
5. 不修改或提交 `data/`、缓存、日志、密钥和 SQLite WAL/SHM。

每个工作日结束时：

1. 勾选真实完成的任务和验收项。
2. 记录验证命令、结果、实际提交、偏差与遗留问题。
3. 未通过验收的工作不得标记完成。
4. 若发现 P0/P1，记录在“阻塞与遗留”并提升到下一工作日首项。

## 9. 当前进度

- [x] Day 1：可靠基线与自动门禁
- [ ] Day 2：核心聊天状态机
- [ ] Day 3：故障隔离与恢复体验
- [ ] Day 4：桌面体验、手机可达性与性能
- [ ] Day 5：回归与内部灰度
- [ ] 内部灰度门槛全部通过

## 10. 执行记录

### Day 1

- 日期：2026-07-29
- 执行会话/负责人：Codex Sol Max
- 开始提交：`d52a6f5`
- 实际提交：
  - `chore: add play webui quality gates`
  - `test: cover play webui stream and history contracts`
- 完成项：
  - ESLint 9 flat config 与 `27` 条存量 warning 上限；
  - Vitest/Testing Library/jsdom 测试基础设施；
  - `lint/test/test:watch/typecheck/check` 工程命令；
  - SSE parser、stream reducer、Context 门禁和 Timeline 映射测试；
  - Node 22 独立 Play WebUI GitHub Actions job；
  - Next.js 与 `eslint-config-next` 同系列补丁升级至 `15.5.22`。
- 验证命令与结果：
  - `npm ci`：通过；
  - `npm run check`：通过；
  - `npm run lint`：`0 errors, 27 warnings`；
  - `npm run test`：`4 files, 37 tests passed`；
  - `npm run typecheck`：通过，包含 `next typegen`；
  - `npm run build`：通过，Session 路由 `250 kB First Load JS`；
  - `eslint --max-warnings 26`：按预期失败，证明新增 warning 会阻断门禁；
  - workflow YAML：本地解析通过，首次远端运行等待推送。
- 偏差：
  - 安装测试依赖时发现 Next 15.5.19 命中公开安全公告，因此在同一主版本内升级到
    15.5.22；构建与 37 项测试通过，未修改应用契约。
- 遗留：
  - `npm audit --omit=dev` 仍报告 Next 内置 `postcss/sharp` 链路的 3 个 high，
    当前建议修复会错误地跨主版本降级 Next，未执行 `npm audit fix --force`；
    后续等待 Next 15 可用的非破坏性上游修复。
  - 远端 GitHub Actions 首次结果需在提交推送后回填。

### Day 2

- 日期：
- 执行会话/负责人：
- 开始提交：
- 实际提交：
- 完成项：
- 验证命令与结果：
- 偏差：
- 遗留：

### Day 3

- 日期：
- 执行会话/负责人：
- 开始提交：
- 实际提交：
- 完成项：
- 验证命令与结果：
- 偏差：
- 遗留：

### Day 4

- 日期：
- 执行会话/负责人：
- 开始提交：
- 实际提交：
- 完成项：
- 验证命令与结果：
- 偏差：
- 遗留：

### Day 5

- 日期：
- 执行会话/负责人：
- 开始提交：
- 实际提交：
- 完成项：
- 验证命令与结果：
- 灰度结论：
- 回滚信息：
- 遗留：

## 11. 阻塞与遗留

- 非阻断：Next 15.5.22 的上游依赖仍触发 3 个 production audit high，暂无
  可接受的非破坏性自动修复。
- 非阻断：Play WebUI workflow 尚未推送，远端首次运行结果待回填。
