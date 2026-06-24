"""Mock backend provider for Play API demos."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from play_api.mock_data import (
    MOCK_COMMANDS,
    mock_history,
    mock_scene,
    mock_session_ids,
    mock_session_summary,
    mock_session_title,
)
from play_api.settings import play_settings


class MockPlayBackend:
    async def list_workspaces(self) -> list[dict[str, object]]:
        return [{"id": "default", "name": "默认工作区", "description": "Play API mock workspace"}]

    async def list_sessions(self, workspace: str) -> list[dict[str, object]]:
        return [
            {
                "id": session_id,
                "workspace": workspace,
                "title": mock_session_title(session_id),
                "description": mock_session_summary(session_id),
            }
            for session_id in mock_session_ids()
        ]

    async def get_history(self, workspace: str, session_id: str) -> list[dict[str, object]]:
        return list(mock_history(session_id))

    async def get_scene(self, workspace: str, session_id: str) -> dict[str, object]:
        scene = mock_scene(session_id)
        attrs = scene.get("attrs", {})
        return {
            **scene,
            "attrs": {**attrs, "workspace": workspace, "session_id": session_id}
            if isinstance(attrs, dict)
            else {"workspace": workspace, "session_id": session_id},
        }

    async def list_commands(self, workspace: str, session_id: str) -> list[dict[str, object]]:
        return list(MOCK_COMMANDS)

    async def send(self, workspace: str, session_id: str, text: str, mode: str) -> dict[str, object]:
        return {
            "reply": _mock_reply(session_id=session_id, text=text, mode=mode),
            "mock": True,
        }

    async def stream(
        self,
        workspace: str,
        session_id: str,
        text: str,
        mode: str,
    ) -> AsyncIterator[dict[str, object]]:
        delay = max(play_settings.mock_stream_delay_ms(), 0) / 1000
        for event in _mock_stream_events(workspace=workspace, session_id=session_id, text=text, mode=mode):
            if delay:
                await asyncio.sleep(delay)
            yield event


def _mock_reply(*, session_id: str, text: str, mode: str) -> str:
    scene = mock_scene(session_id)
    location = scene.get("location", "当前场景")
    if mode == "ooc":
        return f"收到 OOC 备注：{text}。接下来会继续保持 {location} 的节奏与氛围。"
    if mode == "gm":
        return f"GM 指令已记录：{text}。演示 mock 会把它作为下一幕的导演意图。"
    if mode == "slash":
        return f"命令 {text} 已执行。场景状态保持为 {location}。"
    return f"你在{location}采取行动：{text}。雾气随之分开，新的线索露出一角。"


def _mock_stream_events(*, workspace: str, session_id: str, text: str, mode: str) -> list[dict[str, object]]:
    scene = mock_scene(session_id)
    location = scene.get("location", "当前场景")
    reply = _mock_reply(session_id=session_id, text=text, mode=mode)
    return [
        {"kind": "round_start", "round_index": 1, "model": "play-api-mock"},
        {"kind": "thinking", "content": f"读取 {location} 的 scene mock，并解析输入模式 {mode}。"},
        {
            "kind": "tool_call",
            "tool_name": "mock_scene_lookup",
            "tool_arguments": json.dumps(
                {"workspace": workspace, "session_id": session_id},
                ensure_ascii=False,
            ),
        },
        {
            "kind": "tool_result",
            "tool_name": "mock_scene_lookup",
            "tool_result_preview": f"地点：{location}；氛围：{scene.get('mood', '待展开')}",
        },
        {"kind": "text", "content": reply[: max(1, len(reply) // 2)]},
        {"kind": "text", "content": reply[max(1, len(reply) // 2) :]},
        {"kind": "round_end", "round_index": 1, "duration_ms": 360},
        {
            "kind": "done",
            "finish_reason": "mock_completed",
            "usage": {"prompt_tokens": 128, "completion_tokens": 64},
        },
    ]
