"""CharacterManager — manage character cards with full CRUD."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rpg_world.rpg_core.utils.manager_base import BaseManager
from rpg_world.rpg_core.character.loader import CharacterLoader


class CharacterManager(BaseManager):
    """Manages character cards in memory with CRUD operations.

    Data layout — one ``.json`` file per character::

        path/
        ├── alice.json    {"name":"Alice", "content":"…", …}
        └── bob.json      {"name":"Bob",   "content":"…", …}
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.loader = CharacterLoader(self.path)
        self.data: dict[str, dict[str, Any]] = {}  # name → card
        super().__init__()

    # ------------------------------------------------------------------
    # BaseManager abstract methods
    # ------------------------------------------------------------------

    def _data_dir(self) -> Path:
        return self.path

    def reload(self) -> None:
        """Re-read all character cards from disk into memory."""
        logger = logging.getLogger("rpg_core.manager")
        logger.info("CharacterManager.reload from %s", self.path)
        self.data = {}
        for card in self.loader.load_all():
            name = card.get("name")
            if name:
                self.data[name] = card
        logger.info("  -> loaded %d characters", len(self.data))

    def load(self) -> dict[str, dict[str, Any]]:
        """Alias for ``reload()`` returning ``self.data``."""
        self.reload()
        return self.data

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_characters(self) -> list[dict[str, Any]]:
        """Return all character cards (shallow copy list)."""
        if not self.data:
            self.load()
        return list(self.data.values())

    def list_enabled_characters(self) -> list[dict[str, Any]]:
        """Return only character cards where ``enable`` is ``True``."""
        return [c for c in self.list_characters() if c.get("enable")]

    def get_character(self, name: str) -> dict[str, Any]:
        """Return a single character card by name.

        Raises ``FileNotFoundError`` if not found.
        """
        if not self.data:
            self.load()
        card = self.data.get(name)
        if card is None:
            # Try a fresh disk lookup before failing
            try:
                card = self.loader.load_one(name)
                self.data[card["name"]] = card
            except FileNotFoundError:
                raise FileNotFoundError(f"Character not found: {name}") from None
        return card

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_character(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new character card.

        Requires at least a ``name`` key in *data*.  Persists to disk.
        Returns the stored dict.
        """
        name = data.get("name")
        if not name:
            raise ValueError("Character must have a 'name' field")
        # Ensure data is loaded from disk before checking duplicates
        self.list_characters()
        if name in self.data:
            raise ValueError(f"Character already exists: {name}")

        data.setdefault("content", "")
        self.loader.save(name, data)
        self.data[name] = data
        return data

    def update_character(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing character card.

        Returns the updated dict.  If the ``name`` field in *data*
        differs from *name*, the old file is removed.
        Raises ``FileNotFoundError`` if *name* does not exist.
        """
        # Ensure the target exists
        self.get_character(name)

        new_name = data.get("name", name)
        if new_name != name:
            # Rename — merge old entry into new data, remove old file
            old = dict(self.data.get(name, {}))
            old.update(data)
            old["name"] = new_name
            self.loader.delete(name)
            self.data.pop(name, None)
            self.loader.save(new_name, old)
            self.data[new_name] = old
            return old
        else:
            # Merge with existing record to preserve fields not sent by client
            existing = self.data[name]
            merged = {**existing, **data}
            self.loader.save(name, merged)
            self.data[name] = merged
            return merged

    def delete_character(self, name: str) -> None:
        """Delete a character card.

        Raises ``FileNotFoundError`` if *name* does not exist.
        """
        self.get_character(name)  # ensure exists
        self.loader.delete(name)
        self.data.pop(name, None)

    # ------------------------------------------------------------------
    # L2 Detail queries
    # ------------------------------------------------------------------

    def list_details(self, character_name: str) -> list[dict[str, Any]]:
        """Return all L2 details for a character."""
        card = self.get_character(character_name)
        return list(card.get("details", []))

    def get_detail(self, character_name: str, detail_name: str) -> dict[str, Any]:
        """Return a single L2 detail by name.

        Raises ``FileNotFoundError`` if character or detail not found.
        """
        for detail in self.list_details(character_name):
            if detail.get("name") == detail_name:
                return detail
        raise FileNotFoundError(f"Detail not found: {detail_name}")

    # ------------------------------------------------------------------
    # L2 Detail mutations
    # ------------------------------------------------------------------

    def _reload_and_save(self, character_name: str) -> dict[str, Any]:
        """Reload character from disk, return mutable dict."""
        card = self.loader.load_one(character_name)
        self.data[character_name] = card
        return card

    def add_detail(self, character_name: str, detail_data: dict[str, Any]) -> dict[str, Any]:
        """Add an L2 detail to a character.

        Raises ``ValueError`` if a detail with the same name already exists.
        """
        card = self._reload_and_save(character_name)
        details = card.setdefault("details", [])
        detail_name = detail_data.get("name")
        if not detail_name:
            raise ValueError("Detail must have a 'name' field")
        for d in details:
            if d.get("name") == detail_name:
                raise ValueError(f"Detail already exists: {detail_name}")
        detail_data.setdefault("enable", True)
        detail_data.setdefault("content", "")
        detail_data.setdefault("tags", [])
        details.append(detail_data)
        self.loader.save(character_name, card)
        self.data[character_name] = card
        return detail_data

    def update_detail(
        self, character_name: str, detail_name: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an L2 detail.

        Raises ``FileNotFoundError`` if detail not found.
        """
        card = self._reload_and_save(character_name)
        details = card.get("details", [])
        for detail in details:
            if detail.get("name") == detail_name:
                detail.update(data)
                detail["name"] = detail_name  # preserve original name
                self.loader.save(character_name, card)
                self.data[character_name] = card
                return detail
        raise FileNotFoundError(f"Detail not found: {detail_name}")

    def remove_detail(self, character_name: str, detail_name: str) -> None:
        """Remove an L2 detail by name.

        Raises ``FileNotFoundError`` if detail not found.
        """
        card = self._reload_and_save(character_name)
        details = card.get("details", [])
        new_details = [d for d in details if d.get("name") != detail_name]
        if len(new_details) == len(details):
            raise FileNotFoundError(f"Detail not found: {detail_name}")
        card["details"] = new_details
        self.loader.save(character_name, card)
        self.data[character_name] = card
