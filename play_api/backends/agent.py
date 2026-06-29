"""Agent service backend provider for Play API."""

from __future__ import annotations

from collections.abc import AsyncIterator

from play_api import agent_client


class AgentBackend:
    async def get_history(self, workspace: str, story_id: int, session_id: str) -> list[dict[str, object]]:
        del workspace, story_id
        result = await agent_client.get_agent_client().get_history(session_id)
        return list(result.get("history", []))

    async def get_scene(self, workspace: str, story_id: int, session_id: str) -> dict[str, object]:
        return {
            "attrs": {"workspace": workspace, "story_id": str(story_id), "session_id": session_id},
            "time": None,
            "location": None,
            "presentCharacters": [],
            "mood": None,
        }

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

    async def send(self, workspace: str, story_id: int, session_id: str, text: str, mode: str) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().send(session_id, text)

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
