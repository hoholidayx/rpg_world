from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg_data.errors import DataIntegrityError
from rpg_data.services.gateway import DataServiceGateway


@pytest.fixture(autouse=True)
def _isolate_workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))


def test_catalog_creates_and_reads_workspace_without_runtime_directory(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "catalog-workspace.sqlite3")
    try:
        catalog = gateway.catalog
        created = catalog.create_workspace(
            "fixture_world",
            name="Fixture World",
            root_path="data/fixture_world",
            description="fixture",
            metadata={"source": "test", "flags": {"fictional": True}},
        )

        loaded = catalog.get_workspace("fixture_world")
        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.name == created.name
        assert loaded.root_path == created.root_path
        assert created.root_path == "data/fixture_world"
        assert json.loads(created.metadata_json) == {
            "flags": {"fictional": True},
            "source": "test",
        }
        assert not (tmp_path / "data/fixture_world").exists()
    finally:
        gateway.close()


def test_catalog_rejects_duplicate_workspace(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "catalog-conflict.sqlite3")
    try:
        gateway.catalog.create_workspace(
            "fixture_world",
            name="Fixture World",
            root_path="data/fixture_world",
        )

        with pytest.raises(DataIntegrityError, match="persisted constraints"):
            gateway.catalog.create_workspace(
                "fixture_world",
                name="Duplicate",
                root_path="data/duplicate",
            )
    finally:
        gateway.close()


def test_catalog_rejects_non_json_workspace_metadata(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "catalog-metadata.sqlite3")
    try:
        with pytest.raises(ValueError, match="JSON-serializable"):
            gateway.catalog.create_workspace(
                "fixture_world",
                name="Fixture World",
                root_path="data/fixture_world",
                metadata={"weight": float("nan")},
            )

        assert gateway.catalog.get_workspace("fixture_world") is None
    finally:
        gateway.close()
