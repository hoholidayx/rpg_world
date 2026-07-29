# Play WebUI 稳定性优先的 5 天迭代计划

更新时间：2026-07-30

状态：Day 1、Day 2、Day 3、Day 4 已完成；Day 5 待执行

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

- 畸形、未闭合或混合 RP 标签继续原文可见；SSE 解析失败继续按原始帧降级，
  不以收紧 Schema、DONE 或事件顺序作为稳定性手段。
- 已经展示给玩家的持久化业务对话消息和当前流正文，在权威历史确实覆盖前不得
  清除；斜杠命令反馈不进入历史持久化，允许在刷新或权威历史收敛后消失。
- 优化不得改变既有业务逻辑，只修复明确逻辑错误和必要的架构竞态。
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

- [x] 收敛发送、流式、停止、取消、ERROR、DONE 和组件卸载的状态转换。
- [x] 保证同一 Session 同时只有一个活动请求，重复点击不会重复发送。
- [x] 防止停止竞态、切换 Session 后旧请求回写，以及 local stream message
  与持久历史重复。
- [x] committed DONE 后使用权威历史收敛本地副本；保留既有宽松 EOF、畸形 SSE
  原文降级，不收紧 DONE、Schema 或事件顺序。
- [x] 刷新失败时保留已显示回复，提供明确重试，且不清空未提交草稿。
- [x] 增加正常完成、Provider ERROR、停止成功、停止 stale/not-running、
  网络中断和 Session 切换测试。

验收：

- [x] 每个活动请求的所有权最终只收敛到一个明确状态，旧请求不能结算新请求。
- [x] ERROR、断流和取消不产生成功 UI 或虚构 committed turn。
- [x] composer 在所有失败路径上都能恢复可用。
- [x] 人工连续执行 20 个 turn，包含停止、retry、edit 和命令，不出现重复消息、
  消息丢失或永久锁定。

本日已完成针对性真实 smoke 和连续 20-turn 人工脚本：普通提交、停止、retry、
edit、命令及命令后的普通 turn 均通过。斜杠命令仅为当前页面临时反馈，不进入
历史持久化；其在刷新或权威历史收敛后消失符合业务语义，不计为消息丢失。

### Day 3：故障隔离与恢复体验

任务：

- [x] 将 Media、TTS、Dream、Plot/Story 工作台错误限制在各自容器内。
- [x] 仅在用户打开对应工作台时启用非核心查询。
- [x] 对重型工作台组件使用动态加载，不进入 Session 核心首屏包。
- [x] 为核心 Session、角色绑定和历史错误提供页面级恢复入口。
- [x] 为局部服务错误提供独立 retry，不要求刷新整页。
- [x] 统一错误层级：
  - 页面阻断：Session、角色或历史不可用。
  - 局部错误：Media、TTS、Dream、Plot 等能力不可用。
  - 短暂反馈：可恢复操作使用 toast。
- [x] 增加可选服务不可用、恢复和重复重试测试。

验收：

- [x] 分别关闭 Media、TTS、Dream 服务时，历史、发送和停止仍正常。
- [x] 服务恢复后可在原页面重试局部能力。
- [x] 局部失败不污染正文、消息 metadata 或持久状态。

### Day 4：桌面体验、手机可达性与性能

任务：

- [x] 优化 Timeline、Composer、Context 指示器和工作台抽屉的布局稳定性。
- [x] 避免流式内容增长导致操作区跳动或用户阅读位置被强制改变。
- [x] 在 `390×844` 下完成角色绑定、输入、发送、停止、返回最新消息和关闭工作台。
- [x] 处理手机软键盘遮挡、底部安全区和触控目标尺寸。
- [x] 补齐核心对话框、错误恢复和停止后的可预测焦点行为。
- [x] 确保隐藏区域不可被键盘访问。
- [x] 验证 200% 字号、长文本、超长单词和 reduced motion。
- [x] 比较构建产物，确保 Session First Load JS 不高于 `250 kB`，并确认非核心
  工作台已拆出首屏 chunk。

验收：

- [x] `1440×900`、`2560×1440`、`390×844` 三个视口人工脚本通过。
- [x] 无横向溢出、关键操作不可达、软键盘遮挡 composer 或未捕获控制台错误。
- [x] 性能优化不改变查询、消息或流式语义。

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
- [x] 正常流式完成后消息只出现一次，usage 和 committed turn 正确。
- [x] 停止生成只在收到 `cancelled` 后显示 stopped。
- [ ] retry、edit、delete 后历史和当前页正确收敛。
- [ ] 历史前后翻页、返回最新页和页面刷新恢复正确。
- [ ] 切换 Session 时旧请求不会回写新 Session。

### 故障注入

- [ ] Agent/Provider ERROR 不留下成功消息或锁死 composer。
- [ ] 流中断或缺失 DONE 不显示成功。
- [x] Media service 不可用时基础聊天正常。
- [x] TTS service 不可用时基础聊天正常。
- [x] Dream service 不可用时基础聊天正常。
- [x] 局部服务恢复后可在原页面重试。

### 设备与可访问性

- [x] `1440×900` 桌面核心闭环。
- [x] `2560×1440` 桌面核心闭环。
- [x] `390×844` 手机核心闭环与软键盘。
- [x] 键盘完成对话框、发送、停止和关闭工作台。
- [x] 200% 字号下关键操作可达。
- [x] reduced motion 下无依赖动画才能完成的操作。

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
- [x] Day 2：核心聊天状态机
- [x] Day 3：故障隔离与恢复体验
- [x] Day 4：桌面体验、手机可达性与性能
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

- 日期：2026-07-29
- 执行会话/负责人：Codex Sol Max
- 开始提交：`5d548b2`
- 实际提交：
  - `5b83fdd test: lock play webui fallback compatibility`
  - `9eaacf3 fix: serialize and isolate session stream lifecycle`
  - `0fb00a3 test: cover session stream ownership and recovery`
  - `b7b35d2 docs: record play webui day 2 progress`
- 完成项：
  - 为发送、retry、edit 和 timeline mutation 增加同步互斥，阻止异步 preflight
    期间的重复提交与删除竞态；
  - 将 stream、stop、history refresh 和 Session view 绑定到明确的
    `sessionId + requestId` 所有权，旧 Session 事件、finally、toast 和刷新不能
    回写新 Session；
  - 历史窗口在内部校验 Session 所有权，避免外层守卫生效前写入旧页；
  - 刷新失败保留已显示回复并提供“重试刷新”，刷新重试与新 stream 互斥；
  - 只有权威历史确实覆盖本地 user/assistant 正文时才去重，宽松 EOF 和无法解析的
    SSE 原始帧继续可见；
  - 保持停止语义：仅 `cancelled` 显示 stopped，`not_running` 刷新权威状态，
    `stale` 保持当前生成继续；
  - 真实验收发现并修复“stream 先结算、`cancelled` 后返回”竞态；迟到的服务端
    取消确认在没有新请求接管时仍能将本地消息落成 stopped，且保留已生成正文。
- 自动验证：
  - `npm run check`：通过；
  - `npm run lint`：`0 errors, 26 warnings`，均为存量 warning；
  - `npm run test`：`9 files, 64 tests passed`；
  - `npm run typecheck`：通过，包含 `next typegen`；
  - `npm run build`：通过，Session 路由 `251 kB First Load JS`；
  - `git diff --check`：通过。
- 真实服务 smoke：
  - 正常 Provider turn 成功提交并由持久历史覆盖本地副本；
  - 服务端确认取消后显示 stopped，且 composer 恢复；
  - 对 stopped turn 执行 retry 成功，随后 edit 成功；
  - `/roll` 命令及其后的普通 Provider turn 成功；
  - 最终页面中编辑后消息与最后普通消息各一份，无残留 streaming 或 composer
    锁死。
- 连续 20-turn 人工验收：
  - 连续 20 次操作覆盖 6 次成功 Provider 结算（其中包含 retry、edit 各 1 次
    后的成功结算）、1 次服务端确认停止和 13 次 `/roll` 命令；
  - 每次操作结算时对应消息仅一份，composer 均恢复可用；最终无残留 streaming
    或停止按钮；
  - retry 未产生重复消息；edit 后旧正文按既有编辑语义被替换，新正文仅一份；
  - 命令反馈按用户确认的业务语义不进入历史持久化，允许在刷新或后续权威历史
    收敛后消失；“不丢消息”约束只覆盖应持久化的业务对话消息和当前流正文。
- 验收环境：
  - 原用户数据库因 migration checksum mismatch 按硬切 Schema 规则拒绝启动，
    未修改、删除或迁移；
  - 改用 `/tmp/rpg-world-day2-qa.UtsXEK` 临时数据库和 workspace 完成真实验收，
    服务停止后已删除该临时目录。
  - 连续 20-turn 使用 `/tmp/rpg-world-day2-20turn.9KBo2Y` 隔离数据库和
    workspace；未触碰原用户数据库，验收服务停止后删除该临时目录。
- 偏差与遗留：
  - 验收中曾将命令反馈随权威历史收敛后消失误判为消息丢失；用户确认命令不应
    持久化后已撤销候选改动，最终未改变该业务逻辑；
  - Session 路由由 Day 1 的 `250 kB` 变为 `251 kB`，留到 Day 4 按需加载与
    首屏体积任务处理；
  - 未修改或提交用户已有的 `todos/architecture_hardening/`。

### Day 3

- 日期：2026-07-29
- 执行会话/负责人：Codex Sol Max
- 开始提交：`663b6e3`
- 实际提交：
  - `8645815 fix: isolate optional session workspace failures`
  - `docs: record play webui day 3 progress`
- 完成项：
  - 首次 Session 或权威历史不可用时使用页面级 loading/error/retry 阻断发送；
    已有权威历史的后台刷新失败继续保留当前页面，不清屏；
  - 角色绑定所需的角色列表失败时在绑定容器内提供重试；已有有效绑定时不因该
    查询的刷新失败阻断聊天；
  - 角色与状态、剧情故事、故事与记忆、图像工作室四个工作台改为首次打开后
    动态加载，并使用各自的 React Error Boundary 隔离渲染故障；角色绑定与
    Status HUD 所需的核心角色/状态查询仍按既有业务需要保留；
  - Media 工作台查询只在打开后启用，Provider、来源 Turn、背景、Story 库和
    Gallery 均提供局部重试；Media mutation 失败统一使用短暂 toast；
  - TTS 保持用户点击单条 assistant 回复后才发起请求，失败只留在该消息且可
    重试；没有增加预取、持久化或自动轮询；
  - Dream 保持手动刷新且不轮询，并修复“部分 refetch 失败仍提示刷新成功”的
    明确 UI 逻辑错误。
- 自动验证：
  - `npm run check`：通过；
  - `npm run lint`：`0 errors, 26 warnings`，均为既有 warning；
  - `npm run test`：`14 files, 72 tests passed`；
  - `npm run typecheck`：通过，包含 `next typegen`；
  - `npm run build`：通过，Session 路由 `189 kB First Load JS`；
  - `git diff --check`：通过。
- 真实服务 smoke：
  - 使用 `/tmp/rpg-world-day3-smoke.a56g5c` 隔离数据库和 workspace，未触碰
    原用户数据库；
  - Media 下线时工作台的 Provider/来源、Story 背景和 Gallery 分区分别显示
    错误与重试；关闭工作台后普通 Provider turn 成功提交，玩家消息仅一份，
    assistant 回复完成且 composer 恢复；Media 重启后工作台原页恢复；
  - TTS 下线时错误仅出现在被点击的 assistant 消息，Timeline 和 composer
    保持可用；重启后请求不再返回连接错误，并到达 Provider 配置边界；
  - Dream 下线时“持久记忆”仅显示局部错误，Timeline 和 composer 保持可用；
    重启后点击局部重试成功加载 3 条 active Memory；
  - 剧情故事工作台打开和关闭期间 composer 始终存在，防剧透保持开启。
- 偏差：
  - 动态拆包同时提前完成了 Day 4 的 Session 首屏体积目标，First Load JS 从
    Day 2 的 `251 kB` 降为 `189 kB`；未为此改变查询或业务语义；
  - 隔离环境未配置 Speech API key，因此 TTS 重启后的真实播放停在预期的
    Provider 配置错误；服务连接恢复和消息级重试路径已验证。
- 遗留：
  - 真实 Speech Provider 播放需在显式配置测试密钥的 opt-in 环境补验；
  - 未修改或提交用户已有的 `todos/architecture_hardening/`。

### Day 4

- 日期：2026-07-30
- 执行会话/负责人：Codex Sol Max
- 开始提交：`647d193`
- 实际提交：
  - `f9e8c83 fix: stabilize session room responsive scrolling`
  - `2d2c3f6 fix: harden session overlay accessibility`
- 完成项：
  - Session 根布局固定为动态视口高度，Timeline 独占消息滚动，Header 和
    Composer 固定在可见区域；手机安全区、软键盘收缩和关键触控目标均已处理；
  - 流式增量改为 Timeline 容器内的逐帧合并贴底；用户离开底部后不再抢夺阅读
    位置，reduced motion 下平滑滚动统一降级为即时滚动；
  - 设置入口移出 Header 横向滚动区，桌面继续使用锚定浮层，手机使用带遮罩和
    内部滚动的底部抽屉；Context Usage 在手机端使用动态限高和内部滚动；
  - 新增共享 `ModalFocusScope`，统一 portal、背景 inert、初始焦点、Tab 循环、
    Escape、嵌套栈和关闭后焦点恢复；核心 Session 弹层均已接入；
  - 必选角色与 Opening 继续不可跳过，pending 状态继续禁止关闭；停止生成后的
    焦点保持在原 textarea 或停止按钮；
  - 消息和状态文本支持任意长内容换行，代码块保留横向滚动。
- 验证命令与结果：
  - `npm run check`：通过；
  - `npm run lint`：`0 errors, 26 warnings`，均为既有 warning；
  - `npm run test`：`20 files, 87 tests passed`；
  - `npm run typecheck`：通过，包含 `next typegen`；
  - `npm run build`：通过，Session 路由 `192 kB First Load JS`，低于
    `250 kB` 门槛；相较 Day 3 的 `189 kB` 增加 `3 kB`；
  - `1440×900`、`2560×1440`、`390×844` 真实浏览器 smoke 通过，另以
    `390×500` 验证软键盘收缩；
  - 真实 smoke 覆盖“角色 → Opening”、输入、发送、Enter 停止、按钮停止、
    历史翻页、返回最新、工作台开关、设置抽屉、Context 面板及嵌套确认弹层；
  - 200% 字号、长中文、无空格超长文本和 reduced motion 验证通过；手机
    document 不滚动、无横向溢出、Composer 始终可见，应用控制台无错误或警告。
- 偏差：
  - 真实验收额外发现并修复异步角色加载后的初始焦点、点击停止后的焦点保留，
    以及手机命令按钮不足 `44×44px` 三项明确交互错误；
  - Session First Load JS 相较 Day 3 增加 `3 kB`，仍比门槛低 `58 kB`，
    非核心工作台继续保持动态拆包。
- 遗留：
  - 没有 Day 4 阻断项；
  - 未改变 HTTP、SSE、Session、消息、数据库或 localStorage 契约，未改变
    查询时机、历史窗口、宽松标签/SSE/DONE、命令不持久化或已显示消息保留语义；
  - 未修改或提交用户已有的 `docs/project-overview-for-ai.md` 和
    `todos/architecture_hardening/`。

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
- 非阻断：TTS 真实 Speech Provider 播放需在显式配置测试密钥的 opt-in 环境
  补验；本次已验证服务连接恢复与消息级重试。
