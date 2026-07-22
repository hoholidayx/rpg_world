"""Thin core adapter for lorebook entries owned by a Session's Story."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rpg_data.models import SessionLorebookEntry


class LorebookReadPort(Protocol):
    """Session-scoped lorebook reads needed by the Core adapter."""

    def list_entries(self, session_id: str) -> list["SessionLorebookEntry"]: ...

    def list_enabled_entries(
        self,
        session_id: str,
    ) -> list["SessionLorebookEntry"]: ...

    def get_entry(
        self,
        session_id: str,
        name: str,
    ) -> "SessionLorebookEntry | None": ...


class LorebookManager:
    """Read lorebook entries owned by one Session's Story."""

    def __init__(
        self,
        session_id: str,
        service: LorebookReadPort,
    ) -> None:
        self.session_id = session_id
        self._service = service

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_entries(self) -> list[dict[str, object]]:
        """Return all lorebook entries owned by this Session's Story."""

        return [
            _entry_to_dict(entry)
            for entry in self._service.list_entries(self.session_id)
        ]

    def list_enabled_entries(self) -> list[dict[str, object]]:
        """Compatibility alias for Story-owned lorebook entries."""

        return [
            _entry_to_dict(entry)
            for entry in self._service.list_enabled_entries(self.session_id)
        ]

    def get_entry(self, name: str) -> dict[str, object]:
        """Return a Story-owned lorebook entry by name."""

        entry = self._service.get_entry(self.session_id, name)
        if entry is None:
            raise FileNotFoundError(f"Lorebook entry not found: {name}")
        return _entry_to_dict(entry)


def _entry_to_dict(entry: "SessionLorebookEntry") -> dict[str, object]:
    return {
        "id": entry.id,
        "workspace_id": entry.workspace_id,
        "story_id": entry.story_id,
        "name": entry.name,
        "content": entry.content,
        "description": entry.description,
        "tags": list(entry.tags),
        "sort_order": entry.sort_order,
    }
