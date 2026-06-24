from __future__ import annotations

from fastapi.testclient import TestClient

from agent_service import main as service_main
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind
from rpg_core.agent.command import CommandDef, CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.context.rpg_context import Message, Role


class FakeAgent:
    def __init__(self, workspace: str, session_id: str, api_key: str | None = None) -> None:
        self.workspace = workspace
        self._session_id = session_id
        self.api_key = api_key
        self.history = [Message(Role.USER, "hello"), Message(Role.ASSISTANT, "hi")]

    async def _ensure_initialized(self) -> None:
        return None

    async def send(self, message: str) -> AgentReply:
        return AgentReply(text=f"reply:{message}")

    async def send_stream(self, message: str):
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content=f"stream:{message}")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content=f"stream:{message}")

    async def execute_command(self, command: str) -> CommandResult:
        parts = command.split()
        if parts[:1] == ["/session_switch"] and len(parts) > 1:
            self._session_id = parts[1]
        return CommandResult(reply=f"cmd:{command}", handled=True)

    def list_commands(self):
        return [CommandDef(name="/help", description="help", detail="list commands")]


class FakeAgentManager:
    instances: dict[tuple[str, str, str | None], FakeAgent] = {}

    @classmethod
    def get_or_create(cls, workspace: str, session_id: str, api_key: str | None = None):
        key = (workspace, session_id, api_key)
        if key not in cls.instances:
            cls.instances[key] = FakeAgent(workspace, session_id, api_key)
        return cls.instances[key]

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()

    @classmethod
    def drop_session(cls, workspace: str, session_id: str) -> None:
        prefix = (workspace, session_id)
        for key in [key for key in cls.instances if key[:2] == prefix]:
            cls.instances.pop(key, None)


class FakeSessionManager:
    sessions: dict[str, set[str]] = {}

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        if not session_id or any(ch in session_id for ch in "/\\"):
            raise ValueError("session_id must match ^[A-Za-z0-9_]+$")
        return session_id

    @classmethod
    def list_sessions(cls, workspace: str) -> list[str]:
        return sorted(cls.sessions.get(workspace, set()))

    @classmethod
    def create(cls, workspace: str, session_id: str) -> None:
        cls.validate_session_id(session_id)
        bucket = cls.sessions.setdefault(workspace, set())
        if session_id in bucket:
            raise FileExistsError(session_id)
        bucket.add(session_id)

    @classmethod
    def delete(cls, workspace: str, session_id: str) -> None:
        cls.sessions.get(workspace, set()).discard(session_id)

    @classmethod
    def clone(cls, workspace: str, source_id: str, target_id: str) -> None:
        cls.validate_session_id(source_id)
        cls.validate_session_id(target_id)
        bucket = cls.sessions.setdefault(workspace, set())
        if source_id not in bucket:
            raise FileNotFoundError(source_id)
        if target_id in bucket:
            raise FileExistsError(target_id)
        bucket.add(target_id)


def test_agent_service_contracts(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", FakeAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "configure_llama_client_from_runtime_config", lambda: None)
    FakeSessionManager.sessions.clear()

    with TestClient(service_main.app) as client:
        assert client.get("/agent/v1/health").json() == {"status": "ok"}

        history = client.get(
            "/agent/v1/chat/history",
            params={"workspace": "data/ws", "session_id": "s1"},
        )
        assert history.status_code == 200
        assert history.json()["history"][0]["content"] == "hello"

        commands = client.get(
            "/agent/v1/chat/commands",
            params={"workspace": "data/ws", "session_id": "s1"},
        )
        assert commands.status_code == 200
        assert commands.json()["commands"][0]["command"] == "/help"

        sessions = client.get(
            "/agent/v1/chat/sessions",
            params={"workspace": "data/ws", "session_id": "s1"},
        )
        assert sessions.status_code == 200
        assert "sessions" in sessions.json()

        created = client.post(
            "/agent/v1/chat/sessions",
            json={"workspace": "data/ws", "session_id": "s2"},
        )
        assert created.status_code == 200
        assert created.json()["session_id"] == "s2"

        sessions = client.get(
            "/agent/v1/chat/sessions",
            params={"workspace": "data/ws", "session_id": "s1"},
        )
        assert sessions.json()["sessions"] == ["s2"]

        cloned = client.post(
            "/agent/v1/chat/sessions/s2/clone",
            json={"workspace": "data/ws", "target_session_id": "s3"},
        )
        assert cloned.status_code == 200
        assert cloned.json()["target"] == "s3"

        deleted = client.delete(
            "/agent/v1/chat/sessions/s2",
            params={"workspace": "data/ws"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["session_id"] == "s2"

        send = client.post(
            "/agent/v1/chat/send",
            json={"workspace": "data/ws", "session_id": "s1", "message": "go"},
        )
        assert send.status_code == 200
        assert send.json()["reply"] == "reply:go"

        command = client.post(
            "/agent/v1/chat/command",
            json={"workspace": "data/ws", "session_id": "s1", "command": "/session_switch s2"},
        )
        assert command.status_code == 200
        assert command.json()["active_session"] == "s2"

        with client.stream(
            "POST",
            "/agent/v1/chat/stream",
            json={"workspace": "data/ws", "session_id": "s1", "message": "go"},
        ) as stream:
            body = "".join(stream.iter_text())
        assert '"kind": "text"' in body
        assert '"kind": "done"' in body
