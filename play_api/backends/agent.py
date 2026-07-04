"""Agent service backend provider for Play API."""

from __future__ import annotations

from collections.abc import AsyncIterator

from agent_service.client import ContextPreviewPayload
from play_api import agent_client


class AgentBackend:
    async def get_history(self, workspace: str, story_id: int, session_id: str) -> list[dict[str, object]]:
        del workspace, story_id
        result = await agent_client.get_agent_client().get_history(session_id)
        return list(result.get("history", []))

    async def list_commands(self, workspace: str, story_id: int, session_id: str) -> list[dict[str, object]]:
        del workspace, story_id
        result = await agent_client.get_agent_client().list_commands(session_id)
        return [
            {
                "name": str(item.get("command", "")),
                "description": str(item.get("description", "")),
                "mode": "slash",
            }
            for item in result.get("commands", [])
        ]

    async def get_context_preview(self, workspace: str, story_id: int, session_id: str) -> ContextPreviewPayload:
        del workspace, story_id
        return await agent_client.get_agent_client().get_context_preview(session_id)

    async def send(self, workspace: str, story_id: int, session_id: str, text: str, mode: str) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().send(session_id, text)

    async def reload_history(self, workspace: str, story_id: int, session_id: str) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().reload_history(session_id)

    async def truncate_turn(self, workspace: str, story_id: int, session_id: str, turn_id: int) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().truncate_turn(session_id, turn_id)

    async def delete_message(self, workspace: str, story_id: int, session_id: str, message_id: int) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().delete_message(session_id, message_id)

    async def stream(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
        text: str,
        mode: str,
    ) -> AsyncIterator[dict[str, object]]:
        del workspace, story_id
        async for event in agent_client.get_agent_client().stream(session_id, text):
            yield event.to_dict()
