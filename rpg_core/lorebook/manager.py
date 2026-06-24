"""LorebookManager — manage lorebook entries with full CRUD."""

from __future__ import annotations

import logging
from pathlib import Path

from rpg_core.utils.manager_base import BaseManager
from rpg_core.lorebook.loader import LorebookLoader


class LorebookManager(BaseManager):
    """Manages lorebook entries in memory with CRUD operations.

    Supports both single-file and directory-backed storage.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.loader = LorebookLoader(self.path)
        self.data: dict[str, object] = {}  # will hold {"entries": [...]}
        super().__init__()

    # ------------------------------------------------------------------
    # BaseManager abstract methods
    # ------------------------------------------------------------------

    def _data_dir(self) -> Path:
        return self.path

    def reload(self) -> None:
        """Re-read all entries from disk into memory."""
        logger = logging.getLogger("rpg_core.manager")
        logger.info("LorebookManager.reload from %s", self.path)
        entries = self.loader.load()
        self.data = {"entries": entries}
        logger.info("  -> loaded %d entries", len(entries))

    def load(self) -> dict[str, object]:
        """Alias for ``reload()`` returning ``self.data``."""
        self.reload()
        return self.data

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_entries(self) -> list[dict[str, object]]:
        """Return all lorebook entries."""
        if not self.data:
            self.load()
        return self.data.get("entries", [])

    def list_enabled_entries(self) -> list[dict[str, object]]:
        """Return only entries where ``enable`` is ``True``."""
        return [e for e in self.list_entries() if e.get("enable", True)]

    def get_entry(self, name: str) -> dict[str, object]:
        """Return a single entry by name.

        Raises ``FileNotFoundError`` if not found.
        """
        if not self.data:
            self.load()

        for entry in self.data.get("entries", []):
            if entry.get("name") == name:
                return entry

        # Try fresh disk lookup before failing
        try:
            entry = self.loader.load_one(name)
            self.data.setdefault("entries", []).append(entry)
            return entry
        except FileNotFoundError:
            raise FileNotFoundError(f"Lorebook entry not found: {name}") from None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_entry(self, data: dict[str, object]) -> dict[str, object]:
        """Create a new lorebook entry.

        Requires at least a ``name`` key in *data*.  Persists to disk.
        Returns the stored dict.
        """
        name = data.get("name")
        if not name:
            raise ValueError("Entry must have a 'name' field")

        entries = self.list_entries()
        if any(e.get("name") == name for e in entries):
            raise ValueError(f"Entry already exists: {name}")

        data.setdefault("enable", True)
        data.setdefault("content", "")
        entries.append(data)

        self._persist(entries)
        return data

    def update_entry(self, name: str, data: dict[str, object]) -> dict[str, object]:
        """Update an existing lorebook entry.

        If the ``name`` field in *data* differs from *name*, the entry
        is renamed.  Raises ``FileNotFoundError`` if *name* does not
        exist.  Raises ``ValueError`` if *new_name* already belongs to
        another entry.
        """
        entries = self.list_entries()
        idx = next(
            (i for i, e in enumerate(entries) if e.get("name") == name),
            None,
        )
        if idx is None:
            raise FileNotFoundError(f"Lorebook entry not found: {name}")

        new_name = data.get("name", name)
        if new_name != name:
            # Ensure the new name is not taken by another entry
            if any(e.get("name") == new_name for i, e in enumerate(entries) if i != idx):
                raise ValueError(f"Lorebook entry already exists: {new_name}")
            merged = dict(entries[idx])
            merged.update(data)
            entries[idx] = merged
        else:
            entries[idx].update(data)

        self._persist(entries)
        return entries[idx]

    def delete_entry(self, name: str) -> None:
        """Delete a lorebook entry by name.

        Raises ``FileNotFoundError`` if *name* does not exist.
        """
        entries = self.list_entries()
        idx = next(
            (i for i, e in enumerate(entries) if e.get("name") == name),
            None,
        )
        if idx is None:
            raise FileNotFoundError(f"Lorebook entry not found: {name}")

        entries.pop(idx)
        self._persist(entries)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(self, entries: list[dict[str, object]]) -> None:
        """Write the entry list to disk and update in-memory state."""
        self.loader.save_all(entries)
        # Merge into existing data to preserve fields not tracked in entries
        self.data = {**self.data, "entries": entries}
