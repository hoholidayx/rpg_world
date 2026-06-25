"""Agent service backend provider for Play API."""

from __future__ import annotations

from collections.abc import AsyncIterator

from play_api import agent_client


class AgentBackend:
    async def list_sessions(self, workspace: str) -> list[dict[str, object]]:
        result = await agent_client.get_agent_client().list_sessions(workspace, "demo_session")
        sessions = [str(item) for item in result.get("sessions", []) if str(item)]
        return [
            {
                "id": session_id,
                "workspace": workspace,
                "title": session_id,
                "description": None,
            }
            for session_id in sessions
        ]

    async def get_history(self, workspace: str, session_id: str) -> list[dict[str, object]]:
        result = await agent_client.get_agent_client().get_history(workspace, session_id)
        return list(result.get("history", []))

    async def get_scene(self, workspace: str, session_id: str) -> dict[str, object]:
        return {
            "attrs": {"workspace": workspace, "session_id": session_id},
            "time": None,
            "location": None,
            "presentCharacters": [],
            "mood": None,
        }

    async def list_commands(self, workspace: str, session_id: str) -> list[dict[str, object]]:
        result = await agent_client.get_agent_client().list_commands(workspace, session_id)
        return [
            {
                "name": str(item.get("command", "")),
                "description": str(item.get("description", "")),
                "mode": "slash",
            }
            for item in result.get("commands", [])
        ]

    async def send(self, workspace: str, session_id: str, text: str, mode: str) -> dict[str, object]:
        return await agent_client.get_agent_client().send(workspace, session_id, text)

    async def stream(
        self,
        workspace: str,
        session_id: str,
        text: str,
        mode: str,
    ) -> AsyncIterator[dict[str, object]]:
        async for event in agent_client.get_agent_client().stream(workspace, session_id, text):
            yield event.to_dict()
