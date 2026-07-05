from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from agent_service import main as service_main
from rpg_core.agent.agent_types import AgentStreamEvent, StreamEventKind
from rpg_core.agent.command import CommandDef, CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.context.rpg_context import Message, Role
from rpg_data import models


class FakeAgent:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self.history = [Message(Role.USER, "hello"), Message(Role.ASSISTANT, "hi")]

    async def _ensure_initialized(self) -> None:
        return None

    async def send(self, message: str) -> AgentReply:
        return AgentReply(text=f"reply:{message}")

    async def reload_history(self) -> None:
        self.history = [Message(Role.USER, "reloaded", turn_id=1, seq_in_turn=1)]

    async def truncate_history_from_turn(self, turn_id: int) -> dict[str, object]:
        self.history = [message for message in self.history if message.turn_id < turn_id]
        return {
            "status": "truncated",
            "session_id": self._session_id,
            "turn_id": turn_id,
            "removed": 1,
            "agent_sync_status": "synced",
        }

    async def delete_message(self, message_id: int) -> Message:
        return Message(Role.USER, "deleted", uid=message_id, turn_id=1, seq_in_turn=1)

    async def send_stream(self, message: str):
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content=f"stream:{message}")
        yield AgentStreamEvent(kind=StreamEventKind.DONE, content=f"stream:{message}")

    async def execute_command(self, command: str) -> CommandResult:
        parts = command.split()
        if parts[:1] == ["/session_switch"] and len(parts) > 1:
            self._session_id = parts[1]
        if parts[:1] == ["/role_bind"] and len(parts) > 1:
            FakeGateway.session_roles.bind_by_index(self._session_id, int(parts[1]))
        return CommandResult(reply=f"cmd:{command}", handled=True)

    async def get_context_payload(self) -> dict[str, object]:
        return {
            "formatVersion": "context-preview.v1",
            "sessionId": self._session_id,
            "hotHistoryRounds": 5,
            "totals": {
                "layerCount": 1,
                "activeLayers": 1,
                "tokenCount": 3,
                "messageCount": 1,
            },
            "layers": [
                {
                    "index": 0,
                    "type": "fixed_layer",
                    "role": "system",
                    "status": "active",
                    "charCount": 12,
                    "tokenCount": 3,
                    "description": "fixed",
                    "content": "## Fixed",
                }
            ],
            "messages": [{"role": "system", "content": "## Fixed"}],
        }

    def list_commands(self):
        return [CommandDef(name="/help", description="help", detail="list commands")]


class FakeAgentManager:
    instances: dict[str, FakeAgent] = {}

    @classmethod
    def get_or_create(cls, session_id: str):
        if session_id not in cls.instances:
            cls.instances[session_id] = FakeAgent(session_id)
        return cls.instances[session_id]

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()

    @classmethod
    def drop_session(cls, session_id: str) -> None:
        cls.instances.pop(session_id, None)


class FailedSyncAgent(FakeAgent):
    async def truncate_history_from_turn(self, turn_id: int) -> dict[str, object]:
        return {
            "status": "truncated",
            "session_id": self._session_id,
            "turn_id": turn_id,
            "removed": 1,
            "agent_sync_status": "failed",
        }


class FailedSyncAgentManager(FakeAgentManager):
    instances: dict[str, FakeAgent] = {}

    @classmethod
    def get_or_create(cls, session_id: str):
        if session_id not in cls.instances:
            cls.instances[session_id] = FailedSyncAgent(session_id)
        return cls.instances[session_id]


class FakeCatalog:
    sessions: dict[str, models.Session] = {}
    created_count = 0

    @classmethod
    def reset(cls) -> None:
        cls.sessions = {
            "s1": models.Session("s1", "ws", 1, title="Existing"),
            "foreign": models.Session("foreign", "other", 2, title="Foreign"),
        }
        cls.created_count = 0

    @classmethod
    def get_session(cls, session_id: str) -> models.Session | None:
        return cls.sessions.get(session_id)

    @classmethod
    def create_session(
        cls,
        workspace_id: str,
        story_id: int,
        *,
        title: str = "",
        session_id: str | None = None,
    ) -> models.Session | None:
        if workspace_id == "missing":
            return None
        cls.created_count += 1
        sid = session_id or f"generated_{cls.created_count}"
        session = models.Session(sid, workspace_id, story_id, title=title)
        cls.sessions[sid] = session
        return session

    @classmethod
    def list_sessions(cls, workspace_id: str, story_id: int) -> list[models.Session] | None:
        if workspace_id == "missing":
            return None
        return [
            session
            for session in cls.sessions.values()
            if session.workspace_id == workspace_id and int(session.story_id) == story_id
        ]


class FakeMessages:
    @staticmethod
    def list(session_id: str) -> list[models.SessionMessage]:
        return [
            models.SessionMessage(
                id=1,
                session_id=session_id,
                role="user",
                content="hello",
                turn_id=1,
                seq_in_turn=1,
                metadata_json='{"speakerName":"Bob"}',
                created_at="2026-01-01T00:00:00",
            ),
            models.SessionMessage(
                id=2,
                session_id=session_id,
                role="assistant",
                content="hi",
                turn_id=1,
                seq_in_turn=2,
                metadata_json='{"speakerName":"Narrator"}',
                created_at="2026-01-01T00:00:01",
            ),
        ]


class FakeSessionRoles:
    state: dict[str, SimpleNamespace] = {}

    @classmethod
    def reset(cls) -> None:
        cls.state = {}

    @staticmethod
    def list_options(session_id: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(snapshot=SimpleNamespace(character_id=101, name="Bob")),
            SimpleNamespace(snapshot=SimpleNamespace(character_id=102, name="Alice")),
        ]

    @classmethod
    def bind_by_index(cls, session_id: str, index: int) -> SimpleNamespace:
        options = cls.list_options(session_id)
        option = options[index - 1]
        cls.state[session_id] = option.snapshot
        return SimpleNamespace(
            state=SimpleNamespace(status=models.PLAYER_CHARACTER_STATUS_BOUND, player=option.snapshot),
            first_message="",
        )

    @classmethod
    def get_state(cls, session_id: str) -> SimpleNamespace:
        player = cls.state.get(session_id)
        if player is None:
            return SimpleNamespace(status=models.PLAYER_CHARACTER_STATUS_INVALID, player=None)
        return SimpleNamespace(status=models.PLAYER_CHARACTER_STATUS_BOUND, player=player)


class InvalidTurnMessages:
    @staticmethod
    def list(session_id: str) -> list[models.SessionMessage]:
        return [
            models.SessionMessage(
                id=1,
                session_id=session_id,
                role="user",
                content="hello",
                turn_id=1,
                seq_in_turn=1,
            ),
            models.SessionMessage(
                id=2,
                session_id=session_id,
                role="assistant",
                content="broken",
                turn_id=1,
                seq_in_turn=0,
            ),
        ]


class FakeGateway:
    catalog = FakeCatalog
    messages = FakeMessages
    session_roles = FakeSessionRoles


class InvalidHistoryGateway:
    catalog = FakeCatalog
    messages = InvalidTurnMessages


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
    FakeSessionRoles.reset()

    with TestClient(service_main.app) as client:
        assert client.get("/agent/v1/health").json() == {"status": "ok"}

        history = client.get(
            "/agent/v1/chat/history",
            params={"session_id": "s1"},
        )
        assert history.status_code == 200
        assert history.json()["history"][0]["content"] == "hello"
        assert history.json()["history"][0]["messageId"] == 1
        assert history.json()["history"][0]["metadata"]["speakerName"] == "Bob"

        commands = client.get(
            "/agent/v1/chat/commands",
            params={"session_id": "s1"},
        )
        assert commands.status_code == 200
        assert commands.json()["commands"][0]["command"] == "/help"

        context_preview = client.get(
            "/agent/v1/chat/context-preview",
            params={"session_id": "s1"},
        )
        assert context_preview.status_code == 200
        assert context_preview.json()["formatVersion"] == "context-preview.v1"
        assert context_preview.json()["sessionId"] == "s1"
        assert context_preview.json()["layers"][0]["content"] == "## Fixed"
        assert context_preview.json()["messages"][0]["content"] == "## Fixed"

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

        missing_history = client.get(
            "/agent/v1/chat/history",
            params={"session_id": "missing_session"},
        )
        assert missing_history.status_code == 404
        assert missing_history.json()["detail"] == "Session 'missing_session' not found"

        mismatch = client.post(
            "/agent/v1/chat/session/ensure",
            json={"workspace_id": "ws", "story_id": 1, "session_id": "foreign", "title": "Ignored"},
        )
        assert mismatch.status_code == 400

        api_key_rejected = client.post(
            "/agent/v1/chat/send",
            json={"session_id": "s1", "message": "go", "api_key": "legacy"},
        )
        assert api_key_rejected.status_code == 422

        sessions = client.get(
            "/agent/v1/chat/sessions",
            params={"workspace_id": "ws", "story_id": 1},
        )
        assert sessions.json()["sessions"] == ["s1", "generated_1", "generated_2"]

        send = client.post(
            "/agent/v1/chat/send",
            json={"session_id": "s1", "message": "go"},
        )
        assert send.status_code == 200
        assert send.json()["reply"] == "reply:go"

        reload_history = client.post(
            "/agent/v1/chat/session/reload-history",
            json={"session_id": "s1"},
        )
        assert reload_history.status_code == 200
        assert reload_history.json()["status"] == "reloaded"
        assert FakeAgentManager.instances["s1"].history[0].content == "reloaded"

        bind_player = client.post(
            "/agent/v1/chat/session/player-character",
            json={"session_id": "s1", "player_character_id": 101},
        )
        assert bind_player.status_code == 200
        assert bind_player.json()["status"] == "bound"
        assert bind_player.json()["reply"] == "cmd:/role_bind 1"
        assert FakeSessionRoles.state["s1"].character_id == 101

        invalid_bind = client.post(
            "/agent/v1/chat/session/player-character",
            json={"session_id": "s1", "player_character_id": 999},
        )
        assert invalid_bind.status_code == 422

        truncate = client.post(
            "/agent/v1/chat/session/turns/1/truncate",
            json={"session_id": "s1"},
        )
        assert truncate.status_code == 200
        assert truncate.json()["status"] == "truncated"
        assert truncate.json()["turn_id"] == 1
        assert truncate.json()["removed"] == 1

        delete = client.delete(
            "/agent/v1/chat/messages/1",
            params={"session_id": "s1"},
        )
        assert delete.status_code == 200
        assert delete.json()["status"] == "deleted"

        command = client.post(
            "/agent/v1/chat/command",
            json={"session_id": "s1", "command": "/session_switch s2"},
        )
        assert command.status_code == 200
        assert command.json()["active_session"] == "s2"

        with client.stream(
            "POST",
            "/agent/v1/chat/stream",
            json={"session_id": "s1", "message": "go"},
        ) as stream:
            body = "".join(stream.iter_text())
        assert '"kind": "text"' in body
        assert '"kind": "done"' in body


def test_agent_service_history_rejects_invalid_turn_metadata(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", FakeAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: InvalidHistoryGateway)
    monkeypatch.setattr(service_main, "configure_llama_client_from_runtime_config", lambda: None)
    FakeCatalog.reset()

    with TestClient(service_main.app) as client:
        history = client.get(
            "/agent/v1/chat/history",
            params={"session_id": "s1"},
        )

    assert history.status_code == 409
    assert "history[1]" in history.json()["detail"]


def test_agent_service_drops_cached_agent_when_truncate_sync_fails(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", FailedSyncAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: FakeGateway)
    monkeypatch.setattr(service_main, "configure_llama_client_from_runtime_config", lambda: None)
    FakeCatalog.reset()
    FailedSyncAgentManager.reset()

    with TestClient(service_main.app) as client:
        response = client.post(
            "/agent/v1/chat/session/turns/1/truncate",
            json={"session_id": "s1"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "truncated"
    assert response.json()["agent_sync_status"] == "failed"
    assert "s1" not in FailedSyncAgentManager.instances
