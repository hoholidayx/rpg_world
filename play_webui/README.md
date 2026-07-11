# RPG World Play WebUI

Play WebUI 是面向玩家沉浸式聊天、游玩和数据维护的唯一 Web 主体验。

## 当前范围

- Next.js App Router + React + TypeScript。
- Home、最近会话与 `/session/[sessionId]` 游玩房间。
- Timeline、Scene HUD、命令面板、输入区和设置菜单。
- SessionRoom 内统一处理玩家扮演角色选择：`playerCharacterStatus=invalid` 时打开不可取消弹窗，绑定前禁用 composer；设置菜单可查看并切换当前扮演角色，切换需要二次确认。
- SessionRoom 流式生成支持 `requestId` 停止打断；只有 Play API 返回 `cancelled` 时才在本地展示 stopped，`not_running/stale` 会按后端状态收敛。
- SessionRoom 历史通过 `/history-page` 按 turn 分页，默认从 `play_webui.config.json` 读取每页 turn 数；前端只渲染当前 active buffer，最多缓存相邻页，并在离开最新页后提供快速返回底部按钮。
- SessionRoom 输入区底部的 context 圆圈始终展示 `context-preview` 的下一轮主 Agent Context 估算；上一轮 provider usage 仅在对应回复气泡底部和圆圈展开详情中展示，不覆盖圆环，也不持久化。
- context 占用达到 `session.contextUsage.inputBlockThresholdRatio` 时，普通发送、retry 和 edit 被阻止，前导空白后以 `/` 开头的命令仍可执行；界面只引导用户手动 `/compact` 或切换更大窗口模型，不自动压缩或清空草稿。
- context 圆环左侧可切换 session 级主 Agent LLM；Story 详情编辑页配置 story 默认。选项只来自后台白名单，优先级为系统默认、故事默认、会话覆盖，生成中切换从下一 turn 生效。
- 角色库：workspace 角色卡、详情、metadata、头像和 story 挂载。
- 世界设定：workspace lorebook 条目、metadata、缩略图和 story 挂载。
- 状态表：模板、story 挂载、session 运行表、`scene` / `normal` 状态类型。
- 设置页：运行目录扫描、未索引目录清理和 Play API 相关维护入口。
- 前端只访问 `/play-api/v1`，不直接读取或写入 `data/`。
- 流式错误展示使用 `errorCode` + `message`，其中 `message` 是后端底层错误文本，不把 HTTP status 当成业务错误码。

会话页 URL 只携带全局短 `sessionId`；workspace/story 由 Play API 通过 catalog session 反查。
角色库、世界设定和状态表都是 workspace 资产，只有挂载到 story 后才进入对应 session 的上下文或初始化流程。
状态表正文以后端 SQLite `document_json` 为真源，前端通过 `StatusTableDocument` 形态的 API payload 编辑 rows/key/value，不维护 CSV 文件路径。

玩家扮演角色绑定不在 SessionCenter 或进入 SessionRoom 前处理。WebUI 调用
`PATCH /play-api/v1/sessions/{sessionId}/player-character`，由 Play API 转发到 Agent service，并复用 `/role_bind` 的后端绑定逻辑；前端不要直接推断场景在场角色或首个角色作为“你”的身份。

## 常用命令

```bash
npm install
npm run dev
npm run build
```

通用前端配置入口是 `play_webui.config.json`，当前包含 `session.historyPagination` 和 `session.contextUsage.inputBlockThresholdRatio`。正文门禁阈值合法范围为 `(0, 1]`、默认 `0.9`，非法值由 typed loader 回退为 `0.9`。

开发代理默认将 `/play-api/v1/*` 转发到 `RPG_WORLD_PLAY_API_ORIGIN`。

Play API 服务可通过以下命令单独启动：

```bash
uv run python -m run_play_api
```
