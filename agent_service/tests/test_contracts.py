from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

from agent_service import main as service_main
from commons.errors import (
    LLM_SERVICE_UNAVAILABLE_ERROR_CODE,
    LLM_SERVICE_UNAVAILABLE_STATUS_CODE,
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE,
    MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE,
    TURN_METADATA_INVALID_ERROR_CODE,
    TURN_METADATA_INVALID_STATUS_CODE,
    MainContextWindowThresholdExceededError,
)
from llm_client.client import LLMServiceClientError
from llm_client.types import LLMBizCatalog, LLMProviderOption, LLMUsage
import rpg_core.agent.runtime.main_llm as main_llm_module
from rpg_core.agent.agent_types import (
    AgentStreamEvent,
    CallRecord,
    StreamEventKind,
    TurnCancelResult,
    TurnCancelStatus,
    TurnStats,
)
from rpg_core.agent.command import CommandDef, CommandResult
from rpg_core.agent.loop import AgentReply
from rpg_core.context.rpg_context import Message, Role
from rpg_core.session.turn_metadata import InvalidTurnMetadataError
from rpg_data import models
from rpg_data.services import SessionDerivationDataError


class FakeAgent:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self.history = [Message(Role.USER, "hello"), Message(Role.ASSISTANT, "hi")]
        self.last_stream_request_id: str | None = None
        self.closed = False

    @property
    def session_id(self) -> str:
        return self._session_id

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True

    async def send(self, message: str) -> AgentReply:
        stats = TurnStats(started_at=0.0, finished_at=0.0123)
        stats.add_call(CallRecord(
            source="chat_loop",
            model="fake-model",
            usage=LLMUsage(prompt_tokens=11, completion_tokens=7, total_tokens=18, prompt_cache_hit_tokens=3),
            duration_ms=12.3,
        ))
        return AgentReply(text=f"reply:{message}", stats=stats)

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

    async def send_stream(self, message: str, *, request_id: str | None = None):
        self.last_stream_request_id = request_id
        yield AgentStreamEvent(kind=StreamEventKind.TEXT, content=f"stream:{message}")
        yield AgentStreamEvent(
            kind=StreamEventKind.DONE,
            content=f"stream:{message}",
            usage=LLMUsage(prompt_tokens=13, completion_tokens=5, total_tokens=18, prompt_cache_hit_tokens=2),
            model="stream-model",
            finish_reason="stop",
            duration_ms=9.5,
        )

    async def cancel_current_turn(self, request_id: str | None = None) -> TurnCancelResult:
        return TurnCancelResult(
            status=TurnCancelStatus.CANCELLED,
            session_id=self._session_id,
            request_id=request_id,
        )

    async def execute_command(self, command: str) -> CommandResult:
        parts = command.split()
        if parts[:1] == ["/session_switch"] and len(parts) > 1:
            self._session_id = parts[1]
        if parts[:1] == ["/role_bind"] and len(parts) > 1:
            bind_result = FakeGateway.session_roles.bind_by_index(self._session_id, int(parts[1]))
            return CommandResult(
                reply=f"cmd:{command}",
                handled=True,
                role_bind_result=bind_result,
            )
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
            "usageEstimate": {
                "usedTokens": 3,
                "contextLimit": 100,
                "source": "context_preview",
                "accuracy": "estimated",
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
    deleting: set[str] = set()

    @classmethod
    def get_or_create(cls, session_id: str):
        if session_id not in cls.instances:
            cls.instances[session_id] = FakeAgent(session_id)
        return cls.instances[session_id]

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()
        cls.deleting.clear()

    @classmethod
    async def areset(cls) -> None:
        agents = tuple(cls.instances.values())
        cls.reset()
        for agent in agents:
            await agent.close()

    @classmethod
    async def drop_session(cls, session_id: str) -> None:
        agent = cls.instances.pop(session_id, None)
        if agent is not None:
            await agent.close()

    @classmethod
    async def begin_session_deletion(cls, session_id: str) -> None:
        cls.deleting.add(session_id)
        agent = cls.instances.pop(session_id, None)
        if agent is not None:
            await agent.close()

    @classmethod
    def finish_session_deletion(cls, session_id: str) -> None:
        cls.deleting.discard(session_id)


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


class InvalidTurnAgent(FakeAgent):
    async def send(self, message: str) -> AgentReply:
        del message
        raise InvalidTurnMetadataError("invalid persisted turn metadata")

    async def send_stream(self, message: str, *, request_id: str | None = None):
        del message, request_id
        if False:
            yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="")
        raise InvalidTurnMetadataError("invalid persisted turn metadata")


class InvalidTurnAgentManager(FakeAgentManager):
    instances: dict[str, FakeAgent] = {}

    @classmethod
    def get_or_create(cls, session_id: str):
        if session_id not in cls.instances:
            cls.instances[session_id] = InvalidTurnAgent(session_id)
        return cls.instances[session_id]


class ContextThresholdAgent(FakeAgent):
    @staticmethod
    def _error() -> MainContextWindowThresholdExceededError:
        return MainContextWindowThresholdExceededError(
            used_tokens=90,
            context_limit=100,
            threshold_ratio=0.9,
        )

    async def send(self, message: str) -> AgentReply:
        del message
        raise self._error()

    async def send_stream(self, message: str, *, request_id: str | None = None):
        del message, request_id
        if False:
            yield AgentStreamEvent(kind=StreamEventKind.TEXT, content="")
        raise self._error()


class ContextThresholdAgentManager(FakeAgentManager):
    instances: dict[str, FakeAgent] = {}

    @classmethod
    def get_or_create(cls, session_id: str):
        if session_id not in cls.instances:
            cls.instances[session_id] = ContextThresholdAgent(session_id)
        return cls.instances[session_id]


class FakeCatalog:
    stories: dict[int, models.Story] = {}
    sessions: dict[str, models.Session] = {}
    created_count = 0

    @classmethod
    def reset(cls) -> None:
        cls.stories = {
            1: models.Story(1, "ws", "Main Story"),
            2: models.Story(2, "other", "Foreign Story"),
        }
        cls.sessions = {
            "s1": models.Session("s1", "ws", 1, title="Existing"),
            "provisioning": models.Session(
                "provisioning",
                "ws",
                1,
                title="Hidden",
                lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
            ),
            "foreign": models.Session("foreign", "other", 2, title="Foreign"),
        }
        cls.created_count = 0

    @classmethod
    def get_session(cls, session_id: str) -> models.Session | None:
        return cls.sessions.get(session_id)

    @staticmethod
    def list_workspaces() -> list[models.Workspace]:
        return [
            models.Workspace("ws", "Workspace", "/tmp/ws"),
            models.Workspace("other", "Other", "/tmp/other"),
        ]

    @classmethod
    def get_story(cls, workspace_id: str, story_id: int) -> models.Story | None:
        story = cls.stories.get(story_id)
        if story is None or story.workspace_id != workspace_id:
            return None
        return story

    @classmethod
    def get_session_story(cls, session_id: str) -> models.Story | None:
        session = cls.get_session(session_id)
        if session is None:
            return None
        return cls.get_story(session.workspace_id, session.story_id)

    @classmethod
    def set_story_main_llm_provider_key(
        cls,
        workspace_id: str,
        story_id: int,
        provider_key: str | None,
    ) -> models.Story | None:
        story = cls.get_story(workspace_id, story_id)
        if story is None:
            return None
        updated = replace(story, main_llm_provider_key=provider_key)
        cls.stories[story_id] = updated
        return updated

    @classmethod
    def set_session_main_llm_provider_key(
        cls,
        session_id: str,
        provider_key: str | None,
    ) -> models.Session | None:
        session = cls.get_session(session_id)
        if session is None:
            return None
        updated = replace(session, main_llm_provider_key=provider_key)
        cls.sessions[session_id] = updated
        return updated

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
            if session.workspace_id == workspace_id
            and int(session.story_id) == story_id
            and session.lifecycle == models.SESSION_LIFECYCLE_READY
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
            first_message="Welcome Bob" if index == 1 else "",
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


class FakeSessionDeletion:
    @staticmethod
    def validate_regular_deletion(session_id: str) -> models.Session | None:
        session = FakeCatalog.sessions.get(session_id)
        if session is None:
            return None
        if session.lifecycle != models.SESSION_LIFECYCLE_READY:
            raise SessionDerivationDataError(
                "DERIVATION_TARGET_PROVISIONING",
                f"Session is still provisioning: {session_id}",
            )
        return session

    @staticmethod
    def delete(session_id: str) -> models.SessionDeleteResult | None:
        FakeSessionDeletion.validate_regular_deletion(session_id)
        if FakeCatalog.sessions.pop(session_id, None) is None:
            return None
        return models.SessionDeleteResult(
            session_id=session_id,
            runtime_cleanup=models.SESSION_RUNTIME_CLEANUP_DELETED,
        )


class FakeSessionDerivations:
    """Empty derivation queue used by unrelated Agent Service contract tests."""

    @staticmethod
    def list_jobs(*statuses: str) -> list[models.SessionDerivationJob]:
        del statuses
        return []

    @staticmethod
    def interrupt_running_jobs() -> list[models.SessionDerivationJob]:
        return []


class FakeGateway:
    catalog = FakeCatalog
    messages = FakeMessages
    session_roles = FakeSessionRoles
    session_deletion = FakeSessionDeletion
    session_derivations = FakeSessionDerivations


class InvalidHistoryGateway:
    catalog = FakeCatalog
    messages = InvalidTurnMessages
    session_derivations = FakeSessionDerivations


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

    class UnavailableHealthClient:
        async def health(self):  # noqa: ANN201
            raise RuntimeError("offline")

    class FakeLLMClientManager:
        client = UnavailableHealthClient()

        async def get_catalog(self, biz_key: str) -> LLMBizCatalog:
            return LLMBizCatalog(
                biz_key=biz_key,
                kind="chat",
                default_provider_key="deepseek_v4_flash",
                options=(
                    LLMProviderOption(
                        "deepseek_v4_flash",
                        "openai",
                        "deepseek-v4-flash",
                        1_000_000,
                    ),
                ),
            )

    monkeypatch.setattr(
        service_main.LLMClientManager,
        "get",
        classmethod(lambda cls: FakeLLMClientManager()),
    )
    monkeypatch.setattr(
        main_llm_module.LLMClientManager,
        "get",
        classmethod(lambda cls: FakeLLMClientManager()),
    )
    async def fake_provider_catalog(_self):  # noqa: ANN001, ANN202
        return service_main.MainLLMProviderCatalog(
            config_default_provider_key="deepseek_v4_flash",
            options=(
                LLMProviderOption(
                    "deepseek_v4_flash",
                    "openai",
                    "deepseek-v4-flash",
                    1_000_000,
                ),
            ),
        )

    monkeypatch.setattr(
        service_main.MainLLMSelectionService,
        "get_provider_catalog",
        fake_provider_catalog,
    )
    FakeCatalog.reset()
    FakeSessionRoles.reset()

    with TestClient(service_main.app) as client:
        assert client.get("/agent/v1/health").json() == {
            "status": "degraded",
            "llm_service": "unavailable",
        }

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
        assert context_preview.json()["usageEstimate"]["usedTokens"] == 3
        assert context_preview.json()["usageEstimate"]["contextLimit"] == 100

        main_llm_options = client.get("/agent/v1/chat/main-llm/options")
        assert main_llm_options.status_code == 200
        assert main_llm_options.json()["config_default_provider_key"] == "deepseek_v4_flash"
        main_llm_option_rows = main_llm_options.json()["options"]
        assert main_llm_option_rows[0]["provider_key"] == "deepseek_v4_flash"
        assert all(
            set(item) == {
                "provider_key",
                "backend",
                "model",
                "context_window",
            }
            for item in main_llm_option_rows
        )

        story_main_llm = client.get(
            "/agent/v1/chat/main-llm/story",
            params={"workspace_id": "ws", "story_id": 1},
        )
        assert story_main_llm.status_code == 200
        assert story_main_llm.json()["effective_source"] == "config"

        story_selected = client.post(
            "/agent/v1/chat/main-llm/story",
            json={
                "workspace_id": "ws",
                "story_id": 1,
                "provider_key": "deepseek_v4_flash",
            },
        )
        assert story_selected.status_code == 200
        assert story_selected.json()["story_provider_key"] == "deepseek_v4_flash"
        assert story_selected.json()["effective_source"] == "story"

        session_inherits_story = client.get(
            "/agent/v1/chat/main-llm/session",
            params={"session_id": "s1"},
        )
        assert session_inherits_story.status_code == 200
        assert session_inherits_story.json()["effective_source"] == "story"

        session_selected = client.post(
            "/agent/v1/chat/main-llm/session",
            json={"session_id": "s1", "provider_key": "deepseek_v4_flash"},
        )
        assert session_selected.status_code == 200
        assert session_selected.json()["session_provider_key"] == "deepseek_v4_flash"
        assert session_selected.json()["effective_source"] == "session"

        session_cleared = client.post(
            "/agent/v1/chat/main-llm/session",
            json={"session_id": "s1", "provider_key": None},
        )
        assert session_cleared.status_code == 200
        assert session_cleared.json()["session_provider_key"] is None
        assert session_cleared.json()["effective_source"] == "story"

        story_cleared = client.post(
            "/agent/v1/chat/main-llm/story",
            json={"workspace_id": "ws", "story_id": 1, "provider_key": None},
        )
        assert story_cleared.status_code == 200
        assert story_cleared.json()["story_provider_key"] is None
        assert story_cleared.json()["effective_source"] == "config"

        assert client.get(
            "/agent/v1/chat/main-llm/story",
            params={"workspace_id": "missing", "story_id": 1},
        ).status_code == 404
        assert client.get(
            "/agent/v1/chat/main-llm/session",
            params={"session_id": "missing_session"},
        ).status_code == 404
        assert client.get(
            "/agent/v1/chat/main-llm/session",
            params={"session_id": "bad/session"},
        ).status_code == 422
        assert client.get(
            "/agent/v1/chat/main-llm/story",
            params={"workspace_id": " ", "story_id": 1},
        ).status_code == 422
        assert client.post(
            "/agent/v1/chat/main-llm/session",
            json={"session_id": "s1", "provider_key": "not_selectable"},
        ).status_code == 422
        assert client.post(
            "/agent/v1/chat/main-llm/session",
            json={"session_id": "s1"},
        ).status_code == 422

        sessions = client.get(
            "/agent/v1/chat/sessions",
            params={"workspace_id": "ws", "story_id": 1},
        )
        assert sessions.status_code == 200
        assert sessions.json()["sessions"] == [
            {"session_id": "s1", "title": "Existing"},
        ]

        overview = client.get(
            "/agent/v1/chat/session/overview",
            params={"session_id": "s1"},
        )
        assert overview.status_code == 200
        assert overview.json() == {
            "workspace_id": "ws",
            "workspace_title": "Workspace",
            "story_id": 1,
            "story_title": "Main Story",
            "session_id": "s1",
            "session_title": "Existing",
            "player_character_status": "invalid",
            "player_character": None,
            "role_options": [
                {"character_id": 101, "name": "Bob"},
                {"character_id": 102, "name": "Alice"},
            ],
        }

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

        provisioning_requests = [
            client.get(
                "/agent/v1/chat/history",
                params={"session_id": "provisioning"},
            ),
            client.get(
                "/agent/v1/chat/session/overview",
                params={"session_id": "provisioning"},
            ),
            client.post(
                "/agent/v1/chat/session/ensure",
                json={
                    "workspace_id": "ws",
                    "story_id": 1,
                    "session_id": "provisioning",
                },
            ),
            client.get(
                "/agent/v1/chat/main-llm/session",
                params={"session_id": "provisioning"},
            ),
            client.post(
                "/agent/v1/chat/main-llm/session",
                json={"session_id": "provisioning", "provider_key": None},
            ),
            client.delete(
                "/agent/v1/chat/session",
                params={"session_id": "provisioning"},
            ),
        ]
        assert all(response.status_code == 409 for response in provisioning_requests)
        assert all(
            response.json()["detail"]["error_code"]
            == "DERIVATION_TARGET_PROVISIONING"
            for response in provisioning_requests
        )
        assert "provisioning" in FakeCatalog.sessions

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
        assert sessions.json()["sessions"] == [
            {"session_id": "s1", "title": "Existing"},
            {"session_id": "generated_1", "title": "New"},
            {"session_id": "generated_2", "title": "Default"},
        ]

        send = client.post(
            "/agent/v1/chat/send",
            json={"session_id": "s1", "message": "go"},
        )
        assert send.status_code == 200
        assert send.json()["reply"] == "reply:go"
        assert send.json()["usage"]["prompt_tokens"] == 11
        assert send.json()["usage"]["completion_tokens"] == 7
        assert send.json()["usage"]["cached_tokens"] == 3
        assert send.json()["usage"]["source"] == "provider_usage"
        assert send.json()["usage"]["accuracy"] == "accurate"

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
        assert bind_player.json()["player_character"] == {"character_id": 101, "name": "Bob"}
        assert bind_player.json()["first_message"] == "Welcome Bob"
        assert FakeSessionRoles.state["s1"].character_id == 101

        generic_bind = client.post(
            "/agent/v1/chat/command",
            json={"session_id": "s1", "command": "/role_bind 2"},
        )
        assert generic_bind.status_code == 200
        assert set(generic_bind.json()) == {"reply", "handled", "active_session"}

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

        stop = client.post(
            "/agent/v1/chat/stop",
            json={"session_id": "s1", "request_id": "req-stop"},
        )
        assert stop.status_code == 200
        assert stop.json() == {
            "status": TurnCancelStatus.CANCELLED.value,
            "session_id": "s1",
            "request_id": "req-stop",
        }

        command = client.post(
            "/agent/v1/chat/command",
            json={"session_id": "s1", "command": "/session_switch s2"},
        )
        assert command.status_code == 200
        assert command.json()["active_session"] == "s2"

        with client.stream(
            "POST",
            "/agent/v1/chat/stream",
            json={"session_id": "s1", "message": "go", "request_id": "req-stream"},
        ) as stream:
            body = "".join(stream.iter_text())
        assert '"kind": "text"' in body
        assert '"kind": "done"' in body
        assert '"prompt_tokens": 13' in body
        assert '"source": "provider_usage"' in body
        assert FakeAgentManager.instances["s1"].last_stream_request_id == "req-stream"


def test_agent_service_deletes_catalog_session_and_cached_runtime(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", FakeAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: FakeGateway)
    FakeCatalog.reset()
    FakeAgentManager.reset()
    agent = FakeAgentManager.get_or_create("s1")

    with TestClient(service_main.app) as client:
        response = client.delete(
            "/agent/v1/chat/session",
            params={"session_id": "s1"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "status": "deleted",
            "session_id": "s1",
            "runtime_cleanup": "deleted",
        }
        assert agent.closed is True
        assert "s1" not in FakeCatalog.sessions
        assert "s1" not in FakeAgentManager.instances
        assert "s1" not in FakeAgentManager.deleting

        missing = client.delete(
            "/agent/v1/chat/session",
            params={"session_id": "s1"},
        )
        assert missing.status_code == 404


def test_agent_service_history_rejects_invalid_turn_metadata(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", FakeAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: InvalidHistoryGateway)
    FakeCatalog.reset()

    with TestClient(service_main.app) as client:
        history = client.get(
            "/agent/v1/chat/history",
            params={"session_id": "s1"},
        )

    assert history.status_code == 409
    assert "history[1]" in history.json()["detail"]


def test_agent_service_send_and_stream_map_turn_metadata_error(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", InvalidTurnAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: FakeGateway)
    FakeCatalog.reset()
    InvalidTurnAgentManager.reset()

    with TestClient(service_main.app) as client:
        send = client.post(
            "/agent/v1/chat/send",
            json={"session_id": "s1", "message": "go"},
        )
        with client.stream(
            "POST",
            "/agent/v1/chat/stream",
            json={"session_id": "s1", "message": "go"},
        ) as stream:
            body = "".join(stream.iter_text())

    assert send.status_code == TURN_METADATA_INVALID_STATUS_CODE
    assert "invalid persisted turn metadata" in send.json()["detail"]
    assert f'"error_code": "{TURN_METADATA_INVALID_ERROR_CODE}"' in body
    assert f'"status_code": {TURN_METADATA_INVALID_STATUS_CODE}' in body
    assert '"content": "invalid persisted turn metadata"' in body
    assert f"{TURN_METADATA_INVALID_ERROR_CODE}: invalid persisted turn metadata" not in body


def test_agent_service_send_and_stream_map_context_threshold_error(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", ContextThresholdAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: FakeGateway)
    FakeCatalog.reset()
    ContextThresholdAgentManager.reset()

    with TestClient(service_main.app) as client:
        send = client.post(
            "/agent/v1/chat/send",
            json={"session_id": "s1", "message": "go"},
        )
        with client.stream(
            "POST",
            "/agent/v1/chat/stream",
            json={"session_id": "s1", "message": "go"},
        ) as stream:
            body = "".join(stream.iter_text())

    assert send.status_code == MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE
    assert "请先执行 /compact" in send.json()["detail"]
    assert f'"error_code": "{MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE}"' in body
    assert f'"status_code": {MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_STATUS_CODE}' in body
    assert '"content": "主 Agent Context 当前占用' in body
    assert MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE not in send.json()["detail"]


def test_agent_service_send_and_stream_map_llm_dependency_error(monkeypatch) -> None:
    class UnavailableLLMAgent(FakeAgent):
        async def send(self, message: str, **kwargs):  # noqa: ANN003, ANN201
            raise LLMServiceClientError("LLM service connection failed")

        async def send_stream(self, message: str, **kwargs):  # noqa: ANN003, ANN201
            raise LLMServiceClientError("LLM service connection failed")
            yield  # pragma: no cover

        async def execute_command(self, command: str) -> CommandResult:
            raise LLMServiceClientError("LLM service connection failed")

    class UnavailableLLMAgentManager(FakeAgentManager):
        @classmethod
        def get_or_create(cls, session_id: str):  # noqa: ANN206
            if session_id not in cls.instances:
                cls.instances[session_id] = UnavailableLLMAgent(session_id)
            return cls.instances[session_id]

    monkeypatch.setattr(service_main, "AgentManager", UnavailableLLMAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: FakeGateway)
    FakeCatalog.reset()
    UnavailableLLMAgentManager.reset()

    with TestClient(service_main.app) as client:
        send = client.post(
            "/agent/v1/chat/send",
            json={"session_id": "s1", "message": "go"},
        )
        command = client.post(
            "/agent/v1/chat/command",
            json={"session_id": "s1", "command": "/compact"},
        )
        with client.stream(
            "POST",
            "/agent/v1/chat/stream",
            json={"session_id": "s1", "message": "go"},
        ) as stream:
            body = "".join(stream.iter_text())

    assert send.status_code == LLM_SERVICE_UNAVAILABLE_STATUS_CODE
    assert send.json()["detail"] == {
        "error_code": LLM_SERVICE_UNAVAILABLE_ERROR_CODE,
        "message": "LLM service connection failed",
    }
    assert command.status_code == LLM_SERVICE_UNAVAILABLE_STATUS_CODE
    assert command.json()["detail"] == send.json()["detail"]
    assert f'"error_code": "{LLM_SERVICE_UNAVAILABLE_ERROR_CODE}"' in body
    assert f'"status_code": {LLM_SERVICE_UNAVAILABLE_STATUS_CODE}' in body
    assert '"content": "LLM service connection failed"' in body
    assert f"{LLM_SERVICE_UNAVAILABLE_ERROR_CODE}: LLM service connection failed" not in body


def test_agent_service_drops_cached_agent_when_truncate_sync_fails(monkeypatch) -> None:
    monkeypatch.setattr(service_main, "AgentManager", FailedSyncAgentManager)
    monkeypatch.setattr(service_main, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(service_main, "get_data_service_gateway", lambda: FakeGateway)
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
