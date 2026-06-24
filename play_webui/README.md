# RPG World Play WebUI

Play WebUI 是面向玩家沉浸式聊天和游玩的独立前端项目，不复用 Dashboard WebUI 的前端代码，也不绑定 Dashboard API 契约。

## 本阶段范围

- Next.js App Router + React + TypeScript 脚手架。
- 独立 `/play-api/v1` 服务端契约。
- Home / Continue 与 `/session/[sessionId]` 游玩房间骨架。
- Timeline、Scene HUD、输入区、Debug Event Panel。
- 当前接口仅消费 Play API mock，不直接访问 `data/` 或 Dashboard API。

## 常用命令

```bash
npm install
npm run dev
npm run build
```

开发代理默认将 `/play-api/v1/*` 转发到 `RPG_WORLD_PLAY_API_ORIGIN`。

Play API mock 服务可通过以下命令单独启动：

```bash
uv run python -m run_play_api
```
