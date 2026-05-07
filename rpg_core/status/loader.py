"""StatusLoader — load/save CSV tables organized by type subdirectories.

Directory layout::

    path/
    ├── 全局状态/
    │   ├── 待完成事件.csv
    │   └── 世界状态.csv
    └── 角色状态/
        ├── 服装.csv
        └── 生理状态.csv
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any


def _csv_name(fpath: Path) -> str:
    """Return the CSV file name without ``.csv`` suffix."""
    return fpath.stem


class StatusLoader:
    """File I/O for status tables stored as individual ``.csv`` files
    grouped by type subdirectories."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------
    # Type (directory) operations
    # ------------------------------------------------------------------

    def list_types(self) -> list[str]:
        """Return sorted list of type (subdirectory) names."""
        if not self.path.is_dir():
            return []
        return sorted(
            d.name
            for d in self.path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def type_exists(self, name: str) -> bool:
        return (self.path / name).is_dir()

    def create_type(self, name: str) -> Path:
        """Create a new type directory. Returns the path."""
        target = self.path / name
        target.mkdir(parents=True, exist_ok=True)
        return target

    def delete_type(self, name: str) -> None:
        """Recursively delete a type directory and all its contents."""
        target = self.path / name
        if target.is_dir():
            shutil.rmtree(target)

    def rename_type(self, old_name: str, new_name: str) -> Path:
        """Rename a type directory. Returns the new path."""
        src = self.path / old_name
        dst = self.path / new_name
        src.rename(dst)
        return dst

    # ------------------------------------------------------------------
    # Table (CSV file) operations
    # ------------------------------------------------------------------

    def list_tables(self, type_name: str) -> list[str]:
        """Return sorted list of CSV table names (without ``.csv``)."""
        type_dir = self.path / type_name
        if not type_dir.is_dir():
            return []
        return sorted(
            _csv_name(f) for f in type_dir.iterdir() if f.suffix.lower() == ".csv"
        )

    def table_exists(self, type_name: str, table_name: str) -> bool:
        return (self.path / type_name / f"{table_name}.csv").is_file()

    def _table_path(self, type_name: str, table_name: str) -> Path:
        return (self.path / type_name / f"{table_name}.csv").resolve()

    def get_table(self, type_name: str, table_name: str) -> dict[str, Any]:
        """Read a CSV table and return ``{"name": …, "headers": […], "rows": [[…], …]}``.

        Raises ``FileNotFoundError`` if the file does not exist.
        """
        fpath = self._table_path(type_name, table_name)
        if not fpath.is_file():
            raise FileNotFoundError(f"Table not found: {type_name}/{table_name}")

        with fpath.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []
        return {"name": table_name, "headers": headers, "rows": data_rows}

    def save_table(
        self,
        type_name: str,
        table_name: str,
        headers: list[str],
        rows: list[list[str]],
    ) -> Path:
        """Write (create or update) a CSV table.

        Returns the path of the written file.
        """
        type_dir = self.path / type_name
        type_dir.mkdir(parents=True, exist_ok=True)
        fpath = type_dir / f"{table_name}.csv"

        with fpath.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)
        return fpath

    def delete_table(self, type_name: str, table_name: str) -> None:
        """Delete a CSV table file.

        Raises ``FileNotFoundError`` if not found.
        """
        fpath = self._table_path(type_name, table_name)
        if not fpath.is_file():
            raise FileNotFoundError(f"Table not found: {type_name}/{table_name}")
        fpath.unlink()

    def rename_table(
        self, type_name: str, old_name: str, new_name: str
    ) -> Path:
        """Rename a CSV table file. Returns the new path."""
        src = self._table_path(type_name, old_name)
        if not src.is_file():
            raise FileNotFoundError(f"Table not found: {type_name}/{old_name}")
        dst = src.with_name(f"{new_name}.csv")
        src.rename(dst)
        return dst
