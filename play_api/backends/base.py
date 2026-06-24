"""Backend protocol for Play API route handlers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class PlayBackend(Protocol):
    async def list_workspaces(self) -> list[dict[str, object]]: ...

    async def list_sessions(self, workspace: str) -> list[dict[str, object]]: ...

    async def get_history(self, workspace: str, session_id: str) -> list[dict[str, object]]: ...

    async def get_scene(self, workspace: str, session_id: str) -> dict[str, object]: ...

    async def list_commands(self, workspace: str, session_id: str) -> list[dict[str, object]]: ...

    async def send(self, workspace: str, session_id: str, text: str, mode: str) -> dict[str, object]: ...

    async def stream(
        self,
        workspace: str,
        session_id: str,
        text: str,
        mode: str,
    ) -> AsyncIterator[dict[str, object]]: ...
