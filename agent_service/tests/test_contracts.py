from __future__ import annotations

from fastapi.testclient import TestClient

from agent_service import main as service_main
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind
from rpg_core.agent.command import CommandDef, CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.context.rpg_context import Message, Role


class FakeAgent:
    def __init__(self, workspace: str, session_id: str) -> None:
        self.workspace = workspace
        self._session_id = session_id
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
    instances: dict[str, FakeAgent] = {}

    @classmethod
    def get_or_create(cls, workspace: str, session_id: str):
        if session_id not in cls.instances:
            cls.instances[session_id] = FakeAgent(workspace, session_id)
        return cls.instances[session_id]

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()

    @classmethod
    def drop_session(cls, session_id: str) -> None:
        cls.instances.pop(session_id, None)


class FakeCatalog:
    sessions: dict[str, dict[str, object]] = {}
    created_count = 0

    @classmethod
    def reset(cls) -> None:
        cls.sessions = {
            "s1": {"id": "s1", "workspace": "ws", "story_id": 1, "title": "Existing"},
            "foreign": {"id": "foreign", "workspace": "other", "story_id": 2, "title": "Foreign"},
        }
        cls.created_count = 0

    @classmethod
    def get_session(cls, session_id: str) -> dict[str, object] | None:
        return cls.sessions.get(session_id)

    @classmethod
    def create_session(
        cls,
        workspace_id: str,
        story_id: int,
        *,
        title: str = "",
        session_id: str | None = None,
    ) -> dict[str, object] | None:
        if workspace_id == "missing":
            return None
        cls.created_count += 1
        sid = session_id or f"generated_{cls.created_count}"
        session = {"id": sid, "workspace": workspace_id, "story_id": story_id, "title": title}
        cls.sessions[sid] = session
        return session

    @classmethod
    def list_sessions(cls, workspace_id: str, story_id: int) -> list[dict[str, object]] | None:
        if workspace_id == "missing":
            return None
        return [
            session
            for session in cls.sessions.values()
            if session["workspace"] == workspace_id and int(session["story_id"]) == story_id
        ]


class FakeGateway:
    catalog = FakeCatalog


class FakeSessionManager:
    @staticmethod
    def validate_session_id(session_id: str) -> str:
        if not session_id or any(ch in session_id for ch in "/\\"):
            raise ValueError("session_id must match ^[A-Za-z0-9_]+$")
        return session_id


def test_agent_service_contracts(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", FakeAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: FakeGateway)
    monkeypatch.setattr(service_main, "configure_llama_client_from_runtime_config", lambda: None)
    FakeCatalog.reset()

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
            params={"workspace_id": "ws", "story_id": 1},
        )
        assert sessions.status_code == 200
        assert sessions.json()["sessions"] == ["s1"]

        created = client.post(
            "/agent/v1/chat/sessions",
            json={"workspace_id": "ws", "story_id": 1, "title": "New"},
        )
        assert created.status_code == 200
        assert created.json()["session_id"] == "generated_1"
        assert created.json()["title"] == "New"

        ensured_created = client.post(
            "/agent/v1/chat/session/ensure",
            json={"workspace_id": "ws", "story_id": 1, "session_id": None, "title": "Default"},
        )
        assert ensured_created.status_code == 200
        assert ensured_created.json()["session_id"] == "generated_2"

        ensured_existing = client.post(
            "/agent/v1/chat/session/ensure",
            json={"workspace_id": "ws", "story_id": 1, "session_id": "s1", "title": "Ignored"},
        )
        assert ensured_existing.status_code == 200
        assert ensured_existing.json()["session_id"] == "s1"

        missing = client.post(
            "/agent/v1/chat/session/ensure",
            json={"workspace_id": "ws", "story_id": 1, "session_id": "missing_session", "title": "Ignored"},
        )
        assert missing.status_code == 404

        mismatch = client.post(
            "/agent/v1/chat/session/ensure",
            json={"workspace_id": "ws", "story_id": 1, "session_id": "foreign", "title": "Ignored"},
        )
        assert mismatch.status_code == 400

        api_key_rejected = client.post(
            "/agent/v1/chat/send",
            json={"workspace": "data/ws", "session_id": "s1", "message": "go", "api_key": "legacy"},
        )
        assert api_key_rejected.status_code == 422

        sessions = client.get(
            "/agent/v1/chat/sessions",
            params={"workspace_id": "ws", "story_id": 1},
        )
        assert sessions.json()["sessions"] == ["s1", "generated_1", "generated_2"]

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
