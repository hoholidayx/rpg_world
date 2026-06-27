from __future__ import annotations

from pathlib import Path

import pytest

from play_api.backends import data_manager as data_manager_module
from play_api.backends.data_manager import DataManagerBackend


class FakeCatalog:
    def list_workspaces(self):
        return [{"id": "workspace"}]

    def list_sessions(self, workspace: str, story_id: int):
        return [{"id": "session", "workspace": workspace, "story_id": story_id}]

    def create_session(self, workspace: str, story_id: int, *, title: str = "", description: str = ""):
        return {
            "id": "created",
            "workspace": workspace,
            "story_id": story_id,
            "title": title,
            "description": description,
        }

    def get_session(self, session_id: str):
        return {"id": session_id, "workspace": "workspace", "story_id": 1}


class FakeGateway:
    def __init__(self) -> None:
        self.catalog = FakeCatalog()
        self.initialize_calls = 0
        self.close_calls = 0

    def initialize(self) -> None:
        self.initialize_calls += 1

    def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_data_manager_backend_uses_gateway(monkeypatch, tmp_path: Path) -> None:
    gateway = FakeGateway()
    requested_paths: list[Path] = []

    def fake_get_gateway(path: Path):
        requested_paths.append(path)
        return gateway

    monkeypatch.setattr(data_manager_module, "get_data_service_gateway", fake_get_gateway)

    db_path = tmp_path / "play.sqlite3"
    backend = DataManagerBackend(db_path)

    assert requested_paths == [db_path]
    assert gateway.initialize_calls == 1
    assert await backend.list_workspaces() == [{"id": "workspace"}]
    assert (await backend.list_sessions("workspace", 1))[0]["id"] == "session"
    assert (await backend.create_session("workspace", 1, title="Title"))["title"] == "Title"
    assert (await backend.get_session("session"))["id"] == "session"

    backend.close()

    assert gateway.close_calls == 1
