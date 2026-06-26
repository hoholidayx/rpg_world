# RPG World Play WebUI

Play WebUI 是面向玩家沉浸式聊天、游玩和数据维护的唯一 Web 主体验。

## 本阶段范围

- Next.js App Router + React + TypeScript 脚手架。
- 独立 `/play-api/v1` 服务端契约。
- Home / Continue 与 `/session/[sessionId]` 游玩房间骨架。
- Timeline、Scene HUD、输入区、Debug Event Panel。
- 当前接口仅消费 Play API，不直接访问 `data/`。

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
