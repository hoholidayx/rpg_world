from __future__ import annotations

import pytest

from commons.errors import MessageModeUnavailableError
from rpg_core.rp_modules.message_mode import (
    MessageModeModule,
    PlayerPortrayalDetail,
    ensure_message_mode_available,
)
from rpg_core.rp_modules.models import (
    ModuleContextRequest,
    RPModuleSelectionSnapshot,
)
from rpg_core.session.modes import TurnMode


def _request(
    mode: TurnMode,
    *,
    details: tuple[PlayerPortrayalDetail, ...] = (),
) -> ModuleContextRequest:
    return ModuleContextRequest(
        session_id="s1",
        message_mode=mode.value,
        player_character_name="Alice",
        player_portrayal_details=details,
    )


def test_neutral_mode_adds_no_runtime_directive() -> None:
    assert MessageModeModule().get_runtime_sections(
        _request(TurnMode.NEUTRAL)
    ) == []


def test_guided_modes_render_late_turn_policy() -> None:
    module = MessageModeModule()

    ic = module.get_runtime_sections(_request(TurnMode.IC))[0]
    ooc = module.get_runtime_sections(_request(TurnMode.OOC))[0]
    gm = module.get_runtime_sections(
        _request(
            TurnMode.GM,
            details=(
                PlayerPortrayalDetail(name="性格", content="谨慎而敏锐"),
                PlayerPortrayalDetail(name="说话方式", content="简短直接"),
            ),
        )
    )[0]

    assert "不得补写玩家未声明的台词、主动行动、心理活动或关键选择" in ic.content
    assert "不得推进故事时间线" in ooc.content
    assert "无需使用 RP 正文标签" in ooc.content
    assert "在本 turn 内交由你托管" in gm.content
    assert gm.content.count("性格: 谨慎而敏锐") == 1
    assert gm.content.count("说话方式: 简短直接") == 1


@pytest.mark.parametrize("mode", [TurnMode.IC, TurnMode.OOC, TurnMode.GM])
def test_guided_modes_require_effective_message_mode_module(
    mode: TurnMode,
) -> None:
    snapshot = RPModuleSelectionSnapshot(
        session_id="s1",
        story_id=1,
        global_enabled=False,
        modules=(),
    )

    with pytest.raises(MessageModeUnavailableError) as exc_info:
        ensure_message_mode_available(snapshot, mode)

    assert exc_info.value.mode == mode.value


def test_neutral_remains_available_without_message_mode_module() -> None:
    snapshot = RPModuleSelectionSnapshot(
        session_id="s1",
        story_id=1,
        global_enabled=False,
        modules=(),
    )

    ensure_message_mode_available(snapshot, TurnMode.NEUTRAL)
