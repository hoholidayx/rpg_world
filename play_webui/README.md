# RPG World Play WebUI

Play WebUI 是面向玩家沉浸式聊天、游玩和数据维护的唯一 Web 主体验。

## 当前范围

- Next.js App Router + React + TypeScript。
- Home、最近会话与 `/session/[sessionId]` 游玩房间。
- Timeline、Scene HUD、命令面板、输入区和 Debug Event Panel。
- 角色库：workspace 角色卡、详情、metadata、头像和 story 挂载。
- 世界设定：workspace lorebook 条目、metadata、缩略图和 story 挂载。
- 状态表：模板、story 挂载、session 运行表、`scene` / `normal` 状态类型。
- 设置页：运行目录扫描、未索引目录清理和 Play API 相关维护入口。
- 前端只访问 `/play-api/v1`，不直接读取或写入 `data/`。

会话页 URL 只携带全局短 `sessionId`；workspace/story 由 Play API 通过 catalog session 反查。
角色库、世界设定和状态表都是 workspace 资产，只有挂载到 story 后才进入对应 session 的上下文或初始化流程。
状态表正文以后端 SQLite `document_json` 为真源，前端通过 `StatusTableDocument` 形态的 API payload 编辑 rows/key/value，不维护 CSV 文件路径。

## 常用命令

```bash
npm install
npm run dev
npm run build
```

开发代理默认将 `/play-api/v1/*` 转发到 `RPG_WORLD_PLAY_API_ORIGIN`。

Play API 服务可通过以下命令单独启动：

```bash
uv run python -m run_play_api
```
