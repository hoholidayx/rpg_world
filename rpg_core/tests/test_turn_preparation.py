from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import rpg_core.agent.turn.preparation as preparation_module
import rpg_core.agent.loop as loop_module
from llm_service.types import LLMResponse
from rpg_core.agent.loop import run_chat_loop
from rpg_core.agent.turn.preparation import TurnPreparation
from rpg_core.context.rpg_context import Message, Role


class _ContextService:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def compose_scene_user_input(self, scene_ctx, user_input: str) -> str:  # noqa: ANN001
        assert scene_ctx is None
        self.events.append("compose")
        return user_input

    def build_transformed_context(self, **_kwargs) -> list[Message]:  # noqa: ANN003
        self.events.append("context")
        return [
            Message(Role.SYSTEM, "system body must stay private"),
            Message(Role.USER, "user body must stay private"),
        ]


class _ToolService:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.registry = _ToolRegistry()
        self.schemas = [{
            "type": "function",
            "function": {
                "name": "set_state",
                "description": "schema body must stay private",
                "parameters": {"type": "object", "properties": {}},
            },
        }]

    def registry_for_turn(self, *_args, **_kwargs):  # noqa: ANN002, ANN003, ANN201
        self.events.append("registry")
        return self.registry

    def main_schemas(self, *_args, **_kwargs):  # noqa: ANN002, ANN003, ANN201
        self.events.append("schemas")
        return self.schemas


class _MemoryRecall:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def run(self, user_input: str) -> None:
        assert user_input == "current action"
        self.events.append("recall")


class _ToolRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def execute(self, name: str, arguments: object) -> str:
        self.calls.append((name, arguments))
        return "updated"


class _Transaction:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.staged_contents: list[str] = []

    def stage_user_message(self, content: str) -> Message:
        self.events.append("stage")
        self.staged_contents.append(content)
        return Message(Role.USER, content)


def _runtime(events: list[str]) -> SimpleNamespace:
    execution = object()
    return SimpleNamespace(
        plan=SimpleNamespace(
            request=SimpleNamespace(text="current action"),
            execution=execution,
        ),
        scratch=SimpleNamespace(scene_tracker=None, status_manager=object()),
        transaction=_Transaction(events),
        rp_module_runtime=None,
    )


def _preparation(events: list[str]) -> tuple[TurnPreparation, _ToolService]:
    tool_service = _ToolService(events)
    return (
        TurnPreparation(
            context_service=_ContextService(events),  # type: ignore[arg-type]
            tool_service=tool_service,  # type: ignore[arg-type]
            memory_recall=_MemoryRecall(events),  # type: ignore[arg-type]
        ),
        tool_service,
    )


async def test_turn_preparation_logs_final_main_fingerprint_once_after_schemas(
    monkeypatch,
) -> None:
    events: list[str] = []
    preparation, tool_service = _preparation(events)
    info = MagicMock(side_effect=lambda *_args: events.append("fingerprint"))
    monkeypatch.setattr(
        preparation_module,
        "settings",
        SimpleNamespace(verbose_logging=True),
    )
    monkeypatch.setattr(preparation_module.logger, "info", info)

    prepared = await preparation.build(_runtime(events))  # type: ignore[arg-type]

    assert prepared.tool_registry is tool_service.registry
    assert prepared.schemas is tool_service.schemas
    assert events == [
        "compose",
        "stage",
        "recall",
        "context",
        "registry",
        "schemas",
        "fingerprint",
    ]
    assert info.call_count == 1
    call = info.call_args
    assert "source=main_initial" in call.args[0]
    assert len(call.args[1]) == 16
    assert call.args[2] == len("system body must stay privateuser body must stay private")
    assert len(call.args[3]) == 16
    assert call.args[4] == len("system body must stay private")
    assert len(call.args[5]) == 16
    assert call.args[7] == 2
    assert call.args[8] == {
        "system": 1,
        "user": 1,
        "assistant": 0,
        "tool": 0,
    }
    assert call.args[9] == ["set_state"]
    assert call.args[10] == [
        {
            "index": 0,
            "role": "system",
            "hash": call.args[10][0]["hash"],
            "chars": len("system body must stay private"),
        },
        {
            "index": 1,
            "role": "user",
            "hash": call.args[10][1]["hash"],
            "chars": len("user body must stay private"),
        },
    ]
    assert all(len(item["hash"]) == 16 for item in call.args[10])
    logged = repr(call)
    assert "system body must stay private" not in logged
    assert "user body must stay private" not in logged
    assert "schema body must stay private" not in logged


async def test_turn_preparation_skips_fingerprint_when_verbose_is_disabled(
    monkeypatch,
) -> None:
    events: list[str] = []
    preparation, _tool_service = _preparation(events)
    info = MagicMock()
    fingerprint = MagicMock(side_effect=AssertionError("must not fingerprint"))
    monkeypatch.setattr(
        preparation_module,
        "settings",
        SimpleNamespace(verbose_logging=False),
    )
    monkeypatch.setattr(preparation_module.logger, "info", info)
    monkeypatch.setattr(preparation_module, "build_request_fingerprint", fingerprint)

    await preparation.build(_runtime(events))  # type: ignore[arg-type]

    info.assert_not_called()
    fingerprint.assert_not_called()


@pytest.mark.asyncio
async def test_turn_preparation_persists_scene_snapshot_without_runtime_guidance() -> None:
    class SceneTracker:
        @staticmethod
        def get_context() -> str:
            return "[scene]\n位置: 大厅\n\n（仅供 LLM 的提示）\n[/scene]"

        @staticmethod
        def get_snapshot_context() -> str:
            return "[scene]\n位置: 大厅\n[/scene]"

    class ContextService:
        def __init__(self) -> None:
            self.current_user_message: Message | None = None

        @staticmethod
        def compose_scene_user_input(scene_ctx, user_input: str) -> str:  # noqa: ANN001
            if scene_ctx and user_input:
                return f"{scene_ctx}\n{user_input}"
            return scene_ctx or user_input

        def build_transformed_context(self, **kwargs) -> list[Message]:  # noqa: ANN003
            self.current_user_message = kwargs["current_user_message"]
            return [self.current_user_message]

    events: list[str] = []
    context_service = ContextService()
    tool_service = _ToolService(events)
    transaction = _Transaction(events)
    runtime = _runtime(events)
    runtime.scratch.scene_tracker = SceneTracker()
    runtime.transaction = transaction
    preparation = TurnPreparation(
        context_service=context_service,  # type: ignore[arg-type]
        tool_service=tool_service,  # type: ignore[arg-type]
        memory_recall=_MemoryRecall(events),  # type: ignore[arg-type]
    )

    await preparation.build(runtime)  # type: ignore[arg-type]

    assert transaction.staged_contents == [
        "[scene]\n位置: 大厅\n[/scene]\ncurrent action"
    ]
    assert context_service.current_user_message is not None
    assert context_service.current_user_message.content == (
        "[scene]\n位置: 大厅\n\n（仅供 LLM 的提示）\n[/scene]\ncurrent action"
    )


@pytest.mark.asyncio
async def test_main_initial_fingerprint_is_not_repeated_for_tool_rounds(
    monkeypatch,
) -> None:
    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, _messages, *, tools):  # noqa: ANN001
            self.calls += 1
            assert tools == tool_service.schemas
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "set_state", "arguments": "{}"},
                    }],
                    finish_reason="tool_calls",
                    model="fake-model",
                )
            return LLMResponse(
                content="done",
                tool_calls=None,
                finish_reason="stop",
                model="fake-model",
            )

        def get_default_model(self) -> str:
            return "fake-model"

    events: list[str] = []
    preparation, tool_service = _preparation(events)
    info = MagicMock()
    monkeypatch.setattr(
        preparation_module,
        "settings",
        SimpleNamespace(verbose_logging=True),
    )
    monkeypatch.setattr(
        loop_module,
        "settings",
        SimpleNamespace(verbose_logging=False, max_tool_calls=3),
    )
    monkeypatch.setattr(preparation_module.logger, "info", info)
    prepared = await preparation.build(_runtime(events))  # type: ignore[arg-type]
    provider = Provider()

    reply, records = await run_chat_loop(
        provider,  # type: ignore[arg-type]
        prepared.tool_registry,  # type: ignore[arg-type]
        prepared.messages,
        prepared.schemas,
    )

    assert reply == "done"
    assert len(records) == 1
    assert provider.calls == 2
    assert tool_service.registry.calls == [("set_state", "{}")]
    fingerprint_logs = [
        call
        for call in info.call_args_list
        if "main LLM request fingerprint" in call.args[0]
    ]
    assert len(fingerprint_logs) == 1
