"""Agent service backend provider for Play API."""

from __future__ import annotations

from collections.abc import AsyncIterator

from loguru import logger

from agent_service.client import ContextPreviewPayload
from play_api import agent_client


class AgentBackend:
    async def get_main_llm_options(self) -> dict[str, object]:
        return dict(await agent_client.get_agent_client().get_main_llm_options())

    async def get_story_main_llm(
        self,
        workspace: str,
        story_id: int,
    ) -> dict[str, object]:
        return dict(
            await agent_client.get_agent_client().get_story_main_llm(
                workspace,
                story_id,
            )
        )

    async def set_story_main_llm(
        self,
        workspace: str,
        story_id: int,
        provider_key: str | None,
    ) -> dict[str, object]:
        return dict(
            await agent_client.get_agent_client().set_story_main_llm(
                workspace,
                story_id,
                provider_key,
            )
        )

    async def get_session_main_llm(self, session_id: str) -> dict[str, object]:
        return dict(await agent_client.get_agent_client().get_session_main_llm(session_id))

    async def set_session_main_llm(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> dict[str, object]:
        return dict(
            await agent_client.get_agent_client().set_session_main_llm(
                session_id,
                provider_key,
            )
        )

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
                "detail": str(item.get("detail", "")),
                "mode": "slash",
            }
            for item in result.get("commands", [])
        ]

    async def get_context_preview(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
        *,
        mode: str | None = None,
        narrative_style_id: int | None = None,
    ) -> ContextPreviewPayload:
        del workspace, story_id
        if (mode is None or mode == "ic") and narrative_style_id is None:
            return await agent_client.get_agent_client().get_context_preview(session_id)
        return await agent_client.get_agent_client().get_context_preview(
            session_id,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )

    async def send(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
        text: str,
        mode: str,
        narrative_style_id: int | None = None,
    ) -> dict[str, object]:
        del workspace, story_id
        if mode == "ic" and narrative_style_id is None:
            return await agent_client.get_agent_client().send(session_id, text)
        return await agent_client.get_agent_client().send(
            session_id,
            text,
            mode=mode,
            narrative_style_id=narrative_style_id,
        )

    async def reload_history(self, workspace: str, story_id: int, session_id: str) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().reload_history(session_id)

    async def bind_player_character(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
        player_character_id: int,
        *,
        story_opening_id: int | None = None,
    ) -> dict[str, object]:
        del workspace, story_id
        logger.info(
            "[PlayAPI] forwarding player character bind to Agent service: session_id={}, character_id={}, story_opening_id={}",
            session_id,
            player_character_id,
            story_opening_id,
        )
        result = await agent_client.get_agent_client().bind_player_character(
            session_id,
            player_character_id,
            story_opening_id=story_opening_id,
        )
        logger.info(
            "[PlayAPI] Agent service player character bind completed: session_id={}, character_id={}, status={}",
            session_id,
            player_character_id,
            result.get("status"),
        )
        return result

    async def truncate_turn(self, workspace: str, story_id: int, session_id: str, turn_id: int) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().truncate_turn(session_id, turn_id)

    async def delete_message(self, workspace: str, story_id: int, session_id: str, message_id: int) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().delete_message(session_id, message_id)

    async def delete_session(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
    ) -> dict[str, object]:
        del workspace, story_id
        return dict(await agent_client.get_agent_client().delete_session(session_id))

    async def create_session_derivation(
        self,
        source_session_id: str,
        branch_turn_id: int,
        *,
        title: str = "",
    ) -> dict[str, object]:
        return dict(
            await agent_client.get_agent_client().create_session_derivation(
                source_session_id,
                branch_turn_id,
                title=title,
            )
        )

    async def get_session_derivation(self, job_id: str) -> dict[str, object]:
        return dict(
            await agent_client.get_agent_client().get_session_derivation(job_id)
        )

    async def stream(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
        text: str,
        mode: str,
        narrative_style_id: int | None = None,
        request_id: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        del workspace, story_id
        events = (
            agent_client.get_agent_client().stream(
                session_id,
                text,
                request_id=request_id,
            )
            if mode == "ic" and narrative_style_id is None
            else agent_client.get_agent_client().stream(
                session_id,
                text,
                request_id=request_id,
                mode=mode,
                narrative_style_id=narrative_style_id,
            )
        )
        async for event in events:
            yield event.to_dict()

    async def stop(
        self,
        workspace: str,
        story_id: int,
        session_id: str,
        request_id: str | None = None,
    ) -> dict[str, object]:
        del workspace, story_id
        return await agent_client.get_agent_client().stop(session_id, request_id=request_id)
