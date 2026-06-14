"""Shared fixtures for API tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from rpg_world.api.main import app
from rpg_world.api import deps as api_deps
from rpg_world.api.routers import chat as chat_router
from rpg_world.api.routers import sessions as sessions_router
from rpg_world.api.routers import workspace as workspace_router
from rpg_world.api.settings import api_settings
from rpg_world.rpg_core.agent.agent_types import StreamEventKind
from rpg_world.rpg_core.agent.command import CommandDef, CommandResult
from rpg_world.rpg_core.agent.loop import AgentReply
from rpg_world.rpg_core.context.rpg_context import Message, Role
from rpg_world.rpg_core.agent.agent_types import TurnStats


@dataclass
class FakeCharacterManager:
    characters: dict[str, dict[str, object]] = field(default_factory=dict)

    def list_characters(self):
        return list(self.characters.values())

    def get_character(self, name: str):
        if name not in self.characters:
            raise FileNotFoundError(name)
        return self.characters[name]

    def create_character(self, data: dict[str, object]):
        name = str(data["name"])
        if name in self.characters:
            raise ValueError("Character already exists")
        self.characters[name] = dict(data)
        return self.characters[name]

    def update_character(self, name: str, data: dict[str, object]):
        if name not in self.characters:
            raise FileNotFoundError(name)
        new_name = str(data.get("name", name))
        merged = {**self.characters[name], **data, "name": new_name}
        if new_name != name:
            if new_name in self.characters:
                raise ValueError("Character already exists")
            self.characters.pop(name)
        self.characters[new_name] = merged
        return merged

    def delete_character(self, name: str):
        if name not in self.characters:
            raise FileNotFoundError(name)
        self.characters.pop(name)

    def list_details(self, character_name: str):
        return list(self.get_character(character_name).get("details", []))

    def get_detail(self, character_name: str, detail_name: str):
        for detail in self.list_details(character_name):
            if detail.get("name") == detail_name:
                return detail
        raise FileNotFoundError(detail_name)

    def add_detail(self, character_name: str, detail_data: dict[str, object]):
        card = self.get_character(character_name)
        details = card.setdefault("details", [])
        if any(d.get("name") == detail_data["name"] for d in details):
            raise ValueError("Detail already exists")
        details.append(dict(detail_data))
        return detail_data

    def update_detail(self, character_name: str, detail_name: str, data: dict[str, object]):
        card = self.get_character(character_name)
        for detail in card.setdefault("details", []):
            if detail.get("name") == detail_name:
                detail.update(data)
                detail["name"] = detail_name
                return detail
        raise FileNotFoundError(detail_name)

    def remove_detail(self, character_name: str, detail_name: str):
        card = self.get_character(character_name)
        details = card.setdefault("details", [])
        new_details = [d for d in details if d.get("name") != detail_name]
        if len(new_details) == len(details):
            raise FileNotFoundError(detail_name)
        card["details"] = new_details


@dataclass
class FakeLorebookManager:
    entries: dict[str, dict[str, object]] = field(default_factory=dict)

    def list_entries(self):
        return list(self.entries.values())

    def get_entry(self, name: str):
        if name not in self.entries:
            raise FileNotFoundError(name)
        return self.entries[name]

    def create_entry(self, data: dict[str, object]):
        name = str(data["name"])
        if name in self.entries:
            raise ValueError("Entry already exists")
        self.entries[name] = dict(data)
        return self.entries[name]

    def update_entry(self, name: str, data: dict[str, object]):
        if name not in self.entries:
            raise FileNotFoundError(name)
        new_name = str(data.get("name", name))
        merged = {**self.entries[name], **data, "name": new_name}
        if new_name != name:
            if new_name in self.entries:
                raise ValueError("Entry already exists")
            self.entries.pop(name)
        self.entries[new_name] = merged
        return merged

    def delete_entry(self, name: str):
        if name not in self.entries:
            raise FileNotFoundError(name)
        self.entries.pop(name)


@dataclass
class FakeStatusManager:
    tables: dict[str, dict[str, dict[str, object]]] = field(default_factory=dict)

    def list_types(self):
        return list(self.tables.keys())

    def create_type(self, name: str):
        if name in self.tables:
            raise ValueError("Status type already exists")
        self.tables[name] = {}

    def rename_type(self, old_name: str, new_name: str):
        if old_name not in self.tables:
            raise FileNotFoundError(old_name)
        if new_name in self.tables and new_name != old_name:
            raise ValueError("Status type already exists")
        self.tables[new_name] = self.tables.pop(old_name)

    def delete_type(self, name: str):
        if name not in self.tables:
            raise FileNotFoundError(name)
        self.tables.pop(name)

    def list_tables(self, type_name: str):
        if type_name not in self.tables:
            raise FileNotFoundError(type_name)
        return list(self.tables[type_name].keys())

    def get_table(self, type_name: str, table_name: str):
        if type_name not in self.tables or table_name not in self.tables[type_name]:
            raise FileNotFoundError(f"{type_name}/{table_name}")
        return self.tables[type_name][table_name]

    def create_table(self, type_name: str, table_name: str, headers, rows):
        self.tables.setdefault(type_name, {})
        if table_name in self.tables[type_name]:
            raise ValueError("Table already exists")
        data = {"name": table_name, "headers": headers, "rows": rows}
        self.tables[type_name][table_name] = data
        return data

    def save_table(self, type_name: str, table_name: str, headers, rows):
        if type_name not in self.tables or table_name not in self.tables[type_name]:
            raise FileNotFoundError(f"{type_name}/{table_name}")
        data = {"name": table_name, "headers": headers, "rows": rows}
        self.tables[type_name][table_name] = data
        return data

    def rename_table(self, type_name: str, old_name: str, new_name: str):
        if type_name not in self.tables or old_name not in self.tables[type_name]:
            raise FileNotFoundError(f"{type_name}/{old_name}")
        if new_name in self.tables[type_name] and new_name != old_name:
            raise ValueError("Table already exists")
        self.tables[type_name][new_name] = self.tables[type_name].pop(old_name)
        self.tables[type_name][new_name]["name"] = new_name
        return self.tables[type_name][new_name]

    def delete_table(self, type_name: str, table_name: str):
        if type_name not in self.tables or table_name not in self.tables[type_name]:
            raise FileNotFoundError(f"{type_name}/{table_name}")
        self.tables[type_name].pop(table_name)


class FakeAgent:
    def __init__(self, workspace: str, session_id: str, api_key: str | None = None) -> None:
        self.workspace = workspace
        self._session_id = session_id
        self.api_key = api_key
        self.init_calls = 0
        self.history = [Message(Role.USER, "hello"), Message(Role.ASSISTANT, "hi")]
        self._cmd_dispatcher = SimpleNamespace(
            list_commands=lambda: [
                CommandDef(name="/clear", description="clear", detail="clear history"),
                CommandDef(name="/help", description="help", detail="list commands"),
                CommandDef(name="/session_create", description="session create", detail="create session"),
                CommandDef(name="/session_switch", description="session switch", detail="switch session"),
                CommandDef(name="/memory_reindex", description="memory reindex", detail="reindex memory"),
            ],
        )

    async def _ensure_initialized(self) -> None:
        self.init_calls += 1

    async def send(self, message: str) -> AgentReply:
        return AgentReply(text=f"reply:{message}", stats=TurnStats())

    async def send_stream(self, message: str):
        from rpg_world.rpg_core.agent.agent_types import AgentStreamEvent

        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content=f"stream:{message}")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content=f"stream:{message}")

    def list_commands(self):
        return self._cmd_dispatcher.list_commands()

    async def execute_command(self, command: str) -> CommandResult:
        return CommandResult(reply=f"cmd:{command}", handled=True, stats={"ok": True})


class FakeAgentManager:
    instances: dict[tuple[str, str, str | None], FakeAgent] = {}

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()

    @classmethod
    def get_or_create(cls, workspace: str = "", session_id: str = "default", api_key: str | None = None):
        key = (workspace, session_id, api_key)
        if key not in cls.instances:
            cls.instances[key] = FakeAgent(workspace=workspace, session_id=session_id, api_key=api_key)
        return cls.instances[key]


class FakeSessionManager:
    sessions: dict[str, set[str]] = {}

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        if not session_id or any(ch in session_id for ch in "/\\"):
            raise ValueError("session_id must match ^[A-Za-z0-9_]+$")
        return session_id

    @classmethod
    def list_sessions(cls, workspace: str):
        return sorted(cls.sessions.get(workspace, set()))

    @classmethod
    def create(cls, workspace: str, session_id: str):
        cls.validate_session_id(session_id)
        bucket = cls.sessions.setdefault(workspace, set())
        if session_id in bucket:
            raise FileExistsError(session_id)
        bucket.add(session_id)

    @classmethod
    def delete(cls, workspace: str, session_id: str):
        cls.sessions.get(workspace, set()).discard(session_id)

    @classmethod
    def clone(cls, workspace: str, source_id: str, target_id: str):
        cls.validate_session_id(source_id)
        cls.validate_session_id(target_id)
        bucket = cls.sessions.setdefault(workspace, set())
        if source_id not in bucket:
            raise FileNotFoundError(source_id)
        if target_id in bucket:
            raise FileExistsError(target_id)
        bucket.add(target_id)


@pytest.fixture(autouse=True)
def _disable_api_logging(monkeypatch):
    monkeypatch.setitem(api_settings._raw, "log_chat_messages", False)
    monkeypatch.setitem(api_settings._raw, "log_llm_stats", False)
    yield


@pytest.fixture
def client(monkeypatch, tmp_path):
    api_deps.clear_all_caches()
    FakeAgentManager.reset()
    FakeSessionManager.sessions.clear()

    monkeypatch.setattr(workspace_router, "PACKAGE_ROOT", tmp_path / "pkg")
    monkeypatch.setattr(chat_router, "AgentManager", FakeAgentManager)
    monkeypatch.setattr(chat_router, "ensure_workspace_dir", lambda *args, **kwargs: None)
    monkeypatch.setattr(sessions_router, "SessionManager", FakeSessionManager)

    character_mgr = FakeCharacterManager()
    lorebook_mgr = FakeLorebookManager()
    status_mgr = FakeStatusManager()

    app.dependency_overrides.clear()
    app.dependency_overrides[api_deps.get_character_manager] = lambda workspace="": character_mgr
    app.dependency_overrides[api_deps.get_lorebook_manager] = lambda workspace="": lorebook_mgr
    app.dependency_overrides[api_deps.get_session_status_manager] = (
        lambda workspace="", session_id="default": status_mgr
    )

    with TestClient(app) as client:
        yield {
            "client": client,
            "character_mgr": character_mgr,
            "lorebook_mgr": lorebook_mgr,
            "status_mgr": status_mgr,
        }

    app.dependency_overrides.clear()
    api_deps.clear_all_caches()
    FakeAgentManager.reset()
    FakeSessionManager.sessions.clear()
