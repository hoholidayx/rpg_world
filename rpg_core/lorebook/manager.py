"""Thin agent-facing adapter for session lorebook reads."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_data.services import get_data_service_gateway

if TYPE_CHECKING:
    from rpg_data.models import SessionLorebookEntry
    from rpg_data.services.lorebook import LorebookReadService


class LorebookManager:
    """Read lorebook entries mounted to one session's story."""

    def __init__(
        self,
        session_id: str,
        service: "LorebookReadService | None" = None,
    ) -> None:
        self.session_id = session_id
        self._service = service or get_data_service_gateway().lorebook

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_entries(self) -> list[dict[str, object]]:
        """Return all lorebook entries mounted to this session's story."""

        return [
            _entry_to_dict(entry)
            for entry in self._service.list_entries(self.session_id)
        ]

    def list_enabled_entries(self) -> list[dict[str, object]]:
        """Compatibility alias for mounted lorebook entries."""

        return [
            _entry_to_dict(entry)
            for entry in self._service.list_enabled_entries(self.session_id)
        ]

    def get_entry(self, name: str) -> dict[str, object]:
        """Return a mounted lorebook entry by name."""

        entry = self._service.get_entry(self.session_id, name)
        if entry is None:
            raise FileNotFoundError(f"Lorebook entry not found: {name}")
        return _entry_to_dict(entry)


def _entry_to_dict(entry: "SessionLorebookEntry") -> dict[str, object]:
    return {
        "id": entry.id,
        "mount_id": entry.mount_id,
        "workspace_id": entry.workspace_id,
        "story_id": entry.story_id,
        "name": entry.name,
        "content": entry.content,
        "description": entry.description,
        "tags": list(entry.tags),
        "sort_order": entry.sort_order,
    }
