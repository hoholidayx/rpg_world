from __future__ import annotations

from pathlib import Path

import pytest

from rpg_data import db
from rpg_data.settings import get_database_path


def test_get_database_path_defaults_to_data(monkeypatch) -> None:
    monkeypatch.delenv("RPG_WORLD_DB_PATH", raising=False)

    path = get_database_path()

    assert path == Path(__file__).resolve().parents[2] / "data" / "rpg_world.sqlite3"


def test_get_database_path_can_be_overridden(tmp_path: Path, monkeypatch) -> None:
    configured = tmp_path / "custom.sqlite3"
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(configured))

    assert get_database_path() == configured


def test_connect_creates_parent_directory_and_can_create_table(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "rpg_world.sqlite3"

    conn = db.connect(db_path)
    try:
        conn.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        conn.execute("INSERT INTO entries (name) VALUES (?)", ("Mira",))
        row = conn.execute("SELECT id, name FROM entries").fetchone()

        assert db_path.exists()
        assert row["name"] == "Mira"
    finally:
        conn.close()


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "commit.sqlite3")
    try:
        conn.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")

        with db.transaction(conn) as tx:
            tx.execute("INSERT INTO entries (name) VALUES (?)", ("Lyra",))

        row = conn.execute("SELECT name FROM entries").fetchone()
        assert row["name"] == "Lyra"
    finally:
        conn.close()


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "rollback.sqlite3")
    try:
        conn.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")

        with pytest.raises(RuntimeError):
            with db.transaction(conn) as tx:
                tx.execute("INSERT INTO entries (name) VALUES (?)", ("Nyx",))
                raise RuntimeError("boom")

        row = conn.execute("SELECT name FROM entries").fetchone()
        assert row is None
    finally:
        conn.close()
