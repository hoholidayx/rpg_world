"""StatusManager — manage status types and CSV tables with full CRUD."""

from __future__ import annotations

import logging
from pathlib import Path

from rpg_world.rpg_core.utils.manager_base import BaseManager
from rpg_world.rpg_core.status.loader import StatusLoader


class StatusManager(BaseManager):
    """Manages status types and CSV tables in memory with CRUD operations.

    Data layout — subdirectories as types, ``.csv`` files within::

        path/
        ├── 全局状态/
        │   ├── 待完成事件.csv
        │   └── 世界状态.csv
        └── 角色状态/
            ├── 服装.csv
            └── 生理状态.csv

    The in-memory cache is structured as::

        {
          "<type_name>": {
            "<table_name>": {"name": …, "headers": […], "rows": [[…], …]},
            …
          },
          …
        }
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.loader = StatusLoader(self.path)
        # {type_name: {table_name: {name, headers, rows}}}
        self.data: dict[str, dict[str, dict[str, object]]] = {}
        super().__init__()

    # ------------------------------------------------------------------
    # BaseManager abstract methods
    # ------------------------------------------------------------------

    def _data_dir(self) -> Path:
        return self.path

    def reload(self) -> None:
        """Re-read all types and tables from disk into memory."""
        logger = logging.getLogger("rpg_core.manager")
        logger.info("StatusManager.reload from %s", self.path)
        self.data = {}
        for type_name in self.loader.list_types():
            tables: dict[str, dict[str, object]] = {}
            for table_name in self.loader.list_tables(type_name):
                try:
                    tables[table_name] = self.loader.get_table(type_name, table_name)
                except FileNotFoundError:
                    continue
            self.data[type_name] = tables
        logger.info("  -> loaded %d types", len(self.data))

    def load(self) -> dict[str, dict[str, dict[str, object]]]:
        """Alias for ``reload()`` returning ``self.data``."""
        self.reload()
        return self.data

    # ------------------------------------------------------------------
    # Type CRUD
    # ------------------------------------------------------------------

    def list_types(self) -> list[str]:
        """Return all type names."""
        if not self.data:
            self.load()
        return list(self.data.keys())

    def create_type(self, name: str) -> str:
        """Create a new type (directory).

        Raises ``ValueError`` if the type already exists.
        """
        if self.loader.type_exists(name):
            raise ValueError(f"Status type already exists: {name}")
        self.loader.create_type(name)
        self.data[name] = {}
        return name

    def rename_type(self, old_name: str, new_name: str) -> str:
        """Rename a type.

        Raises ``FileNotFoundError`` if ``old_name`` does not exist.
        Raises ``ValueError`` if ``new_name`` already exists.
        """
        if not self.loader.type_exists(old_name):
            raise FileNotFoundError(f"Status type not found: {old_name}")
        if old_name != new_name and self.loader.type_exists(new_name):
            raise ValueError(f"Status type already exists: {new_name}")
        self.loader.rename_type(old_name, new_name)
        tables = self.data.pop(old_name, {})
        self.data[new_name] = tables
        return new_name

    def delete_type(self, name: str) -> None:
        """Delete a type and all its tables.

        Raises ``FileNotFoundError`` if not found.
        """
        if not self.loader.type_exists(name):
            raise FileNotFoundError(f"Status type not found: {name}")
        self.loader.delete_type(name)
        self.data.pop(name, None)

    # ------------------------------------------------------------------
    # Table CRUD
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self.data:
            self.load()

    def _type_tables(self, type_name: str) -> dict[str, dict[str, object]]:
        """Return the table dict for *type_name*, loading if needed."""
        self._ensure_loaded()
        tables = self.data.get(type_name)
        if tables is None:
            # Try fresh disk lookup
            if self.loader.type_exists(type_name):
                tables = {}
                for table_name in self.loader.list_tables(type_name):
                    try:
                        tables[table_name] = self.loader.get_table(type_name, table_name)
                    except FileNotFoundError:
                        continue
                self.data[type_name] = tables
            else:
                raise FileNotFoundError(f"Status type not found: {type_name}")
        return tables

    def list_tables(self, type_name: str) -> list[str]:
        """Return all table names for a type."""
        return list(self._type_tables(type_name).keys())

    def get_table(self, type_name: str, table_name: str) -> dict[str, object]:
        """Return a single table's data.

        Raises ``FileNotFoundError`` if type or table not found.
        """
        tables = self._type_tables(type_name)
        table = tables.get(table_name)
        if table is None:
            # Try fresh disk lookup
            try:
                table = self.loader.get_table(type_name, table_name)
                tables[table_name] = table
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Table not found: {type_name}/{table_name}"
                ) from None
        return table

    def create_table(
        self,
        type_name: str,
        table_name: str,
        headers: list[str] | None = None,
        rows: list[list[str]] | None = None,
    ) -> dict[str, object]:
        """Create a new table in a type.

        Raises ``ValueError`` if the table already exists.
        """
        tables = self._type_tables(type_name)
        if self.loader.table_exists(type_name, table_name):
            raise ValueError(
                f"Table already exists: {type_name}/{table_name}"
            )

        headers = headers or []
        rows = rows or []
        self.loader.save_table(type_name, table_name, headers, rows)
        data = {"name": table_name, "headers": headers, "rows": rows}
        tables[table_name] = data
        return data

    def save_table(
        self,
        type_name: str,
        table_name: str,
        headers: list[str],
        rows: list[list[str]],
    ) -> dict[str, object]:
        """Update an existing table's data.

        Raises ``FileNotFoundError`` if the table does not exist.
        """
        tables = self._type_tables(type_name)
        if not self.loader.table_exists(type_name, table_name):
            raise FileNotFoundError(
                f"Table not found: {type_name}/{table_name}"
            )

        self.loader.save_table(type_name, table_name, headers, rows)
        data = {"name": table_name, "headers": headers, "rows": rows}
        tables[table_name] = data
        return data

    def rename_table(
        self, type_name: str, old_name: str, new_name: str
    ) -> dict[str, object]:
        """Rename a table.

        Raises ``FileNotFoundError`` if the old name does not exist.
        Raises ``ValueError`` if the new name already exists.
        """
        tables = self._type_tables(type_name)
        if not self.loader.table_exists(type_name, old_name):
            raise FileNotFoundError(
                f"Table not found: {type_name}/{old_name}"
            )
        if old_name != new_name and self.loader.table_exists(type_name, new_name):
            raise ValueError(
                f"Table already exists: {type_name}/{new_name}"
            )

        self.loader.rename_table(type_name, old_name, new_name)
        data = tables.pop(old_name, {"name": old_name, "headers": [], "rows": []})
        data["name"] = new_name
        tables[new_name] = data
        return data

    def delete_table(self, type_name: str, table_name: str) -> None:
        """Delete a table.

        Raises ``FileNotFoundError`` if not found.
        """
        tables = self._type_tables(type_name)
        self.loader.delete_table(type_name, table_name)
        tables.pop(table_name, None)
