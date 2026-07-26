from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from commons.errors import MainContextWindowThresholdExceededError
import rpg_core.agent.runtime.context as context_module
from rpg_core.agent.adjudication import AdjudicationContextSnapshot
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
from rpg_core.context import FixedLayerSection
from rpg_core.context.models import (
    FixedLayerData,
    HotHistoryLayer,
    LayerType,
    Message,
    PersistentMemoryFact,
    RPModulesLayer,
    Role,
    RPGContext,
    StoryMemoryFact,
    UserMessageLayer,
)
from rpg_core.session import SessionManager
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionPlayerCharacterState,
)


class _Counter:
    @staticmethod
    def count(text: str) -> int:
        return len(text)

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
        self.story_memory_loads = 0

    async def load_persistent_memory_snapshot(self):  # noqa: ANN201
        self.persistent_memory_loads += 1
        return ()

    async def load_story_memory_snapshot(self):  # noqa: ANN201
        self.story_memory_loads += 1
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


class _TurnSnapshotData:
    @staticmethod
    def get_session(_session_id: str):  # noqa: ANN201
        return None

    @staticmethod
    def get_session_story(_session_id: str):  # noqa: ANN201
        return None


class _SessionComposer:
    @staticmethod
    def resolve_session_style(
        _session_id: str,
        _override_style_id: int | None,
    ):  # noqa: ANN201
        return None


class _RoleReader:
    @staticmethod
    def get_state(_session_id: str) -> SessionPlayerCharacterState:
        return SessionPlayerCharacterState(
            status=PlayerCharacterBindingStatus.INVALID,
            player=None,
        )

    @staticmethod
    def list_options(_session_id: str) -> list:
        return []


def _resources(
    builder: _Builder,
    scene=None,
    characters=None,
    lorebook=None,
) -> AgentContextResources:  # noqa: ANN001
    return AgentContextResources(
        builder=builder,
        character_manager=characters,
        lorebook_manager=lorebook,
        status_manager=None,
        scene_tracker=scene,
        memory_manager=None,
    )


def _service(
    builder: _Builder,
    *,
    session=None,
    scene=None,
    characters=None,
    lorebook=None,
):  # noqa: ANN001, ANN201
    session = session or SessionManager(history_enabled=False)
    resources = _resources(builder, scene, characters, lorebook)
    return AgentContextService(
        world_name="World",
        session_id=lambda: "s1",
        session_manager=session,
        resources=lambda: resources,
        rp_module_service=lambda: None,
        main_llm_selection=lambda _sid: SimpleNamespace(
            effective=SimpleNamespace(context_window=100)
        ),
        token_counter=_Counter(),
        turn_snapshot_data=_TurnSnapshotData(),
        session_composer=_SessionComposer(),
        role_snapshot_reader=_RoleReader(),
    )


def _execution(
    mode: TurnMode = TurnMode.IC,
    *,
    player_character: TurnPlayerCharacterSnapshot | None = None,
    rendered_story_prompt: str = "",
    narrative_style_name: str = "",
    narrative_style_prompt: str = "",
) -> TurnExecutionSnapshot:
    request = TurnRequest.create("preview", mode=mode)
    return TurnExecutionSnapshot(
        request=request,
        narrative_style_id=None,
        narrative_style_name=narrative_style_name,
        narrative_style_prompt=narrative_style_prompt,
        policy=TurnExecutionPolicy.for_mode(mode),
        player_character=player_character,
        rendered_story_prompt=rendered_story_prompt,
    )


class _Characters:
    @staticmethod
    def list_enabled_characters() -> list[dict[str, object]]:
        return [
            {"id": 1, "name": "Bob"},
            {"id": 2, "name": "Alice"},
        ]


class _Lorebook:
    @staticmethod
    def list_enabled_entries() -> list[dict[str, object]]:
        return [{"name": "北境", "content": "北境仍处于永夜。"}]


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


def test_fixed_layer_bytes_are_identical_across_all_message_modes() -> None:
    service = _service(_Builder(), characters=_Characters())
    rendered: list[str | None] = []

    for mode in TurnMode:
        fixed_layer = service._assemble_fixed_layer(
            turn_execution=_execution(
                mode,
                player_character=TurnPlayerCharacterSnapshot(
                    character_id=2,
                    story_id=1,
                    name="Alice",
                ),
                rendered_story_prompt="Story prompt",
                narrative_style_name="克制",
                narrative_style_prompt="保持克制的叙事风格。",
            )
        )
        rendered.append(
            RPGContext(fixed_layer=fixed_layer).render_layer(LayerType.FIXED)
        )

    assert len(set(rendered)) == 1


def test_adjudication_snapshot_uses_explicit_allowlist_and_both_memories() -> None:
    service = _service(
        _Builder(),
        characters=_Characters(),
        lorebook=_Lorebook(),
    )
    execution = _execution(
        mode=TurnMode.GM,
        player_character=TurnPlayerCharacterSnapshot(
            character_id=2,
            story_id=1,
            name="Alice",
        ),
        rendered_story_prompt="Story Prompt 真源。",
        narrative_style_name="不应注入",
        narrative_style_prompt="叙事风格秘密。",
    )
    persistent = PersistentMemoryFact(
        memory_id="pm-1",
        revision_number=2,
        text="常驻记忆事实。",
        memory_kind="world_fact",
        epistemic_status="confirmed",
        salience=0.9,
    )
    story = StoryMemoryFact(
        memory_id=4,
        turn_id=3,
        text="剧情记忆事实。",
        memory_kind="event",
        epistemic_status="confirmed",
        salience=0.8,
        source_turn_start=3,
        source_turn_end=3,
    )

    fixed = service._assemble_adjudication_fixed_layer(
        turn_execution=execution
    )
    snapshot = service.build_adjudication_context_snapshot(
        turn_execution=execution,
        persistent_memory_snapshot=(persistent,),
        story_memory_snapshot=(story,),
    )
    content = "\n".join(message.content for message in snapshot.messages)

    assert [section.id for section in fixed.sections] == [
        "adjudication_authority",
        "story_prompt",
        "lorebook",
        "player_character",
        "character_card",
    ]
    assert not any(
        section.source.startswith("rp_module")
        for section in fixed.sections
    )
    assert "Story Prompt 真源。" in content
    assert "北境仍处于永夜。" in content
    assert "当前玩家扮演角色：Alice" in content
    assert "Bob" in content and "Alice" in content
    assert "常驻记忆事实。" in content
    assert "剧情记忆事实。" in content
    assert "叙事风格秘密。" not in content
    assert "RP 正文必须由 XML" not in content
    assert "先在内部确定本轮叙事后果" not in content
    assert "[message_mode]" not in content
    assert "GM 托管" not in content
    assert "neutral/IC" not in content
    assert "召回记忆" not in content
    assert "Summary" not in content
    assert "rp_module:" not in content


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
    with pytest.raises(MainContextWindowThresholdExceededError):
        service.enforce_window_threshold(
            selection,
            rp_module_snapshot=SimpleNamespace(),
            turn_execution=_execution(),
            plot_schedule_snapshot=SimpleNamespace(
                enabled=True,
                context_gate_reserve_text="12",
            ),
        )
    service.enforce_window_threshold(
        selection,
        rp_module_snapshot=SimpleNamespace(),
        turn_execution=_execution(mode=TurnMode.OOC),
        plot_schedule_snapshot=SimpleNamespace(
            enabled=True,
            context_gate_reserve_text="12",
        ),
    )

    service.build_for_inspection = lambda *_args, **_kwargs: SimpleNamespace(  # type: ignore[method-assign]
        to_message_objects=lambda: [Message(Role.USER, "123456789")]
    )
    with pytest.raises(MainContextWindowThresholdExceededError):
        service.enforce_window_threshold(
            selection,
            rp_module_snapshot=SimpleNamespace(),
            turn_execution=_execution(),
        )


def test_plot_judge_context_uses_fixed_state_and_latest_complete_world_turns() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history(
        [
            Message(Role.USER, "ic user", mode="ic", turn_id=1, seq_in_turn=1),
            Message(Role.ASSISTANT, "ic reply", mode="ic", turn_id=1, seq_in_turn=2),
            Message(Role.USER, "ooc user", mode="ooc", turn_id=2, seq_in_turn=1),
            Message(Role.ASSISTANT, "ooc reply", mode="ooc", turn_id=2, seq_in_turn=2),
            Message(Role.USER, "gm user", mode="gm", turn_id=3, seq_in_turn=1),
            Message(Role.ASSISTANT, "gm reply", mode="gm", turn_id=3, seq_in_turn=2),
            Message(
                Role.USER,
                "neutral user",
                mode="neutral",
                turn_id=4,
                seq_in_turn=1,
            ),
            Message(
                Role.ASSISTANT,
                "neutral reply",
                mode="neutral",
                turn_id=4,
                seq_in_turn=2,
            ),
        ],
        persist=False,
    )
    service = _service(_Builder(), session=session)
    adjudication_context = AdjudicationContextSnapshot.from_messages(
        [Message(Role.SYSTEM, "shared adjudication marker")]
    )
    scene = SimpleNamespace(get_context=lambda: "[scene]\n位置: 大厅\n[/scene]")
    status = SimpleNamespace(
        list_context_tables=lambda: [
            {
                "id": 1,
                "name": "角色状态",
                "status_kind": "normal",
                "description": "测试",
                "headers": ["属性", "值"],
                "document": {
                    "rows": [
                        {
                            "key": "生命",
                            "value": "8",
                            "runtimeKeyLocked": False,
                            "updateRule": "",
                            "metadata": {},
                        }
                    ]
                },
            }
        ]
    )
    messages = service.build_plot_judge_messages(
        judge_prompt="judge marker",
        current_user_input="current marker",
        history_turns=2,
        status_manager=status,
        scene_tracker=scene,
        adjudication_context=adjudication_context,
    )

    contents = [message.content for message in messages]
    assert contents[0] == "shared adjudication marker"
    assert contents[1] == "judge marker"
    assert "位置: 大厅" in contents[2]
    assert "生命" in contents[2]
    assert contents[-5:] == [
        "gm user",
        "gm reply",
        "neutral user",
        "neutral reply",
        "current marker",
    ]
    assert all("ooc" not in content and "ic user" not in content for content in contents)
    assert all("rp fixed marker" not in content for content in contents)


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
        placement="rp_modules",
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
