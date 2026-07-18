from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from commons.errors import MainContextWindowThresholdExceededError
import rpg_core.agent.runtime.context as context_module
from rpg_core.agent.runtime.context import AgentContextService
from rpg_core.agent.runtime.resources import AgentContextResources
from rpg_core.agent.turn import (
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnMode,
    TurnPlayerCharacterSnapshot,
    TurnRequest,
)
from rpg_core.context.fixed_layer.contributors import PLAYER_CHARACTER_SECTION_ID
from rpg_core.context.models import (
    FixedLayerData,
    HotHistoryLayer,
    Message,
    RPModulesLayer,
    Role,
    RPGContext,
    UserMessageLayer,
)
from rpg_core.session import SessionManager


class _Counter:
    @staticmethod
    def count_messages(messages: list[Message]) -> int:
        return sum(len(message.content) for message in messages)


class _Builder:
    config = SimpleNamespace(
        hot_history_rounds=5,
        enable_lorebook=True,
        enable_character=True,
    )

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.persistent_memory_loads = 0

    async def load_persistent_memory_snapshot(self):  # noqa: ANN201
        self.persistent_memory_loads += 1
        return ()

    def build(
        self,
        *,
        fixed_layer,
        history_messages,
        current_user_message,
        **kwargs,
    ) -> RPGContext:  # noqa: ANN001
        self.calls.append(
            {
                "fixed_layer": fixed_layer,
                "history_messages": list(history_messages),
                "current_user_message": current_user_message,
                **kwargs,
            }
        )
        return RPGContext(
            fixed_layer=fixed_layer,
            hot_history=HotHistoryLayer(messages=list(history_messages)),
            rp_modules=RPModulesLayer(
                sections=list(kwargs.get("rp_module_sections") or [])
            ),
            user_message=UserMessageLayer(
                user_input=(current_user_message.content if current_user_message else "")
            ),
        )


class _Scene:
    @staticmethod
    def get_context() -> str:
        return "<scene>大厅</scene>"


def _resources(builder: _Builder, scene=None, characters=None) -> AgentContextResources:  # noqa: ANN001
    return AgentContextResources(
        builder=builder,
        character_manager=characters,
        lorebook_manager=None,
        status_manager=None,
        scene_tracker=scene,
        memory_manager=None,
    )


def _service(builder: _Builder, *, session=None, scene=None, characters=None):  # noqa: ANN001, ANN201
    session = session or SessionManager(history_enabled=False)
    resources = _resources(builder, scene, characters)
    return AgentContextService(
        world_name="World",
        session_id=lambda: "s1",
        session_manager=session,
        resources=lambda: resources,
        rp_module_registry=lambda: None,
        main_llm_selection=lambda _sid: SimpleNamespace(
            effective=SimpleNamespace(context_window=100)
        ),
        token_counter=_Counter(),
    )


def _execution(
    mode: TurnMode = TurnMode.IC,
    *,
    player_character: TurnPlayerCharacterSnapshot | None = None,
    rendered_story_prompt: str = "",
) -> TurnExecutionSnapshot:
    request = TurnRequest.create("preview", mode=mode)
    return TurnExecutionSnapshot(
        request=request,
        mode_prompt="",
        narrative_style_id=None,
        narrative_style_name="",
        narrative_style_prompt="",
        policy=TurnExecutionPolicy.for_mode(mode),
        player_character=player_character,
        rendered_story_prompt=rendered_story_prompt,
    )


class _Characters:
    @staticmethod
    def list_enabled_characters() -> list[dict[str, object]]:
        return [
            {"id": 1, "mount_id": 10, "name": "Bob"},
            {"id": 2, "mount_id": 20, "name": "Alice"},
        ]


def test_context_preview_composes_scene_before_input_without_mutating_history() -> None:
    session = SessionManager(history_enabled=False)
    history = [Message(Role.USER, "old", turn_id=1, seq_in_turn=1)]
    session.replace_history(history, persist=False)
    builder = _Builder()
    service = _service(builder, session=session, scene=_Scene())
    service._assemble_fixed_layer = MagicMock(return_value=FixedLayerData())

    context = service.build_for_inspection(
        "我观察四周",
        turn_execution=_execution(),
    )

    current = builder.calls[0]["current_user_message"]
    assert current.content == "<scene>大厅</scene>\n我观察四周"
    assert context.to_message_objects()[-1].content == current.content
    assert [message.content for message in session.history] == ["old"]


def test_context_service_reassembles_fixed_layer_for_each_build() -> None:
    builder = _Builder()
    service = _service(builder)
    service._assemble_fixed_layer = MagicMock(
        side_effect=[
            FixedLayerData(world_name="first"),
            FixedLayerData(world_name="second"),
        ]
    )

    service.build_transformed_context(
        current_user_message=Message(Role.USER, "one")
    )
    service.build_transformed_context(
        current_user_message=Message(Role.USER, "two")
    )

    assert service._assemble_fixed_layer.call_count == 2
    assert builder.calls[0]["fixed_layer"].world_name == "first"
    assert builder.calls[1]["fixed_layer"].world_name == "second"


def test_context_fixed_layer_uses_frozen_player_and_story_prompt() -> None:
    builder = _Builder()
    service = _service(builder, characters=_Characters())
    execution = _execution(
        player_character=TurnPlayerCharacterSnapshot(
            character_id=2,
            mount_id=20,
            story_id=1,
            name="Alice",
        ),
        rendered_story_prompt="本轮玩家角色是 Alice。",
    )

    fixed_layer = service._assemble_fixed_layer(turn_execution=execution)

    section_ids = [section.id for section in fixed_layer.sections]
    assert PLAYER_CHARACTER_SECTION_ID in section_ids
    assert fixed_layer.sections[section_ids.index("story_prompt")].content == "本轮玩家角色是 Alice。"
    player_section = fixed_layer.sections[section_ids.index(PLAYER_CHARACTER_SECTION_ID)]
    assert player_section.priority == 25
    assert "旧内容与本绑定冲突" in player_section.content
    assert fixed_layer.characters[0]["control_role"] == "npc"
    assert fixed_layer.characters[1]["control_role"] == "player_character"


def test_context_gate_excludes_new_input_and_rejects_at_threshold(monkeypatch) -> None:
    builder = _Builder()
    service = _service(builder)
    seen_inputs: list[str] = []

    def build_for_inspection(user_input: str, **_kwargs):  # noqa: ANN001, ANN201
        seen_inputs.append(user_input)
        return SimpleNamespace(
            to_message_objects=lambda: [Message(Role.USER, "12345678")]
        )

    service.build_for_inspection = build_for_inspection  # type: ignore[method-assign]
    monkeypatch.setattr(
        context_module,
        "settings",
        SimpleNamespace(context_window_reject_threshold_ratio=0.9),
    )
    selection = SimpleNamespace(
        effective=SimpleNamespace(context_window=10),
        effective_provider_key="test",
    )
    service.enforce_window_threshold(
        selection,
        rp_module_snapshot=SimpleNamespace(),
        turn_execution=_execution(),
    )
    assert seen_inputs == [""]

    service.build_for_inspection = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        to_message_objects=lambda: [Message(Role.USER, "123456789")]
    )
    with pytest.raises(MainContextWindowThresholdExceededError):
        service.enforce_window_threshold(
            selection,
            rp_module_snapshot=SimpleNamespace(),
            turn_execution=_execution(),
        )


def test_verbose_context_logging_only_logs_main_llm_context_once(monkeypatch) -> None:
    builder = _Builder()
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "history user secret", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "history assistant secret", turn_id=1, seq_in_turn=2),
    ], persist=False)
    service = _service(builder, session=session)
    debug = MagicMock()
    monkeypatch.setattr(
        context_module,
        "settings",
        SimpleNamespace(verbose_logging=True),
    )
    monkeypatch.setattr(context_module.logger, "debug", debug)
    section = SimpleNamespace(
        id="outcome",
        title="剧情预裁定",
        source="rp_module:narrative_outcome",
        priority=80,
        content="staged outcome runtime",
    )
    runtime = SimpleNamespace(
        get_fixed_sections=lambda: [],
        get_runtime_sections=lambda _request: [section],
    )

    service.build_for_inspection(
        "preview action",
        turn_execution=_execution(),
    )
    messages = service.build_transformed_context(
        current_user_message=Message(Role.USER, "current action"),
        user_input="行动",
        rp_module_runtime=runtime,
        turn_execution=_execution(),
    )

    assert messages[-1].content == "current action"
    context_logs = [
        call.args[-1]
        for call in debug.call_args_list
        if "current context prepared" in call.args[0]
    ]
    assert len(context_logs) == 1
    context_log = context_logs[0]
    assert "当前 Context（provider message 顺序）" in context_log
    assert "fixed_layer (system)" in context_log
    assert "rp_modules (system)" in context_log
    assert "staged outcome runtime" in context_log
    assert "user_message (user)" in context_log
    assert "current action" in context_log
    assert "preview action" not in context_log
    assert "hot_history (mixed)" in context_log
    assert "turns=1" in context_log
    assert "history user secret" not in context_log
    assert "history assistant secret" not in context_log


def test_compose_scene_user_input_keeps_user_after_scene_close_tag() -> None:
    scene = '<scene time="09:00">\n地点: 门厅\n</scene>'
    assert AgentContextService.compose_scene_user_input(scene, "我观察四周") == (
        '<scene time="09:00">\n地点: 门厅\n</scene>\n我观察四周'
    )
