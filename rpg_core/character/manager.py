"""Thin agent-facing adapter for session character reads."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_data.services import get_data_service_gateway

if TYPE_CHECKING:
    from rpg_data.models import SessionCharacter, SessionCharacterDetail
    from rpg_data.services.character import CharacterReadService


class CharacterManager:
    """Read character cards mounted to one session's story."""

    def __init__(
        self,
        session_id: str,
        service: "CharacterReadService | None" = None,
    ) -> None:
        self.session_id = session_id
        self._service = service or get_data_service_gateway().character

    def list_characters(self) -> list[dict[str, object]]:
        """Return all character cards mounted to this session's story."""

        return [
            _character_to_dict(character)
            for character in self._service.list_characters(self.session_id)
        ]

    def list_enabled_characters(self) -> list[dict[str, object]]:
        """Compatibility alias for mounted character cards."""

        return self.list_characters()

    def get_character(self, name: str) -> dict[str, object]:
        """Return a mounted character card by name."""

        character = self._service.get_character(self.session_id, name)
        if character is None:
            raise FileNotFoundError(f"Character not found: {name}")
        return _character_to_dict(character)

    def list_details(self, character_name: str) -> list[dict[str, object]]:
        """Return all details for a mounted character."""

        character = self.get_character(character_name)
        return list(character.get("details", []))

    def get_detail(self, character_name: str, detail_name: str) -> dict[str, object]:
        """Return a single detail by name."""

        for detail in self.list_details(character_name):
            if detail.get("name") == detail_name:
                return detail
        raise FileNotFoundError(f"Detail not found: {detail_name}")

    def list_detail_names(self, character_name: str) -> list[str]:
        """Return all detail names for a mounted character."""

        return [
            str(detail["name"])
            for detail in self.list_details(character_name)
        ]

    def get_details_by_names(
        self,
        character_name: str,
        detail_names: list[str],
    ) -> list[dict[str, object]]:
        """Return details matching ``detail_names``."""

        name_set = set(detail_names)
        return [
            detail
            for detail in self.list_details(character_name)
            if detail.get("name") in name_set
        ]

    def get_all_details(self, character_name: str) -> list[dict[str, object]]:
        """Return all details for a mounted character."""

        return self.list_details(character_name)


def _character_to_dict(character: "SessionCharacter") -> dict[str, object]:
    return {
        "id": character.id,
        "mount_id": character.mount_id,
        "workspace_id": character.workspace_id,
        "story_id": character.story_id,
        "name": character.name,
        "personality": character.personality,
        "content": character.content,
        "details": [
            _detail_to_dict(detail)
            for detail in character.details
        ],
        "sort_order": character.sort_order,
    }


def _detail_to_dict(detail: "SessionCharacterDetail") -> dict[str, object]:
    return {
        "id": detail.id,
        "character_id": detail.character_id,
        "name": detail.name,
        "content": detail.content,
        "tags": list(detail.tags),
        "sort_order": detail.sort_order,
    }
