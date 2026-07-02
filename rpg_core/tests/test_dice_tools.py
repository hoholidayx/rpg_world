from __future__ import annotations

import random

import pytest

from rpg_core.rp_modules.dice.tools import DiceCheckDCTool, DiceRollTool, DiceRoller
from rpg_core.settings import DiceModuleSettings


@pytest.mark.asyncio
async def test_dice_roll_tool_returns_reproducible_result():
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(1))
    tool = DiceRollTool(roller)

    result = await tool.execute(expression="2d6+3", reason="潜行", actor="艾拉")

    assert "骰子结果:" in result
    assert "expression=2d6+3" in result
    assert "rolls=[2, 5]" in result
    assert "modifier=3" in result
    assert "total=10" in result
    assert "reason=潜行" in result
    assert "actor=艾拉" in result


@pytest.mark.asyncio
async def test_dice_check_dc_tool_combines_expression_and_extra_modifier():
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(2))
    tool = DiceCheckDCTool(roller)

    result = await tool.execute(expression="1d20+2", dc=5, modifier=1)

    assert "检定结果:" in result
    assert "expression=1d20+2" in result
    assert "rolls=[2]" in result
    assert "modifier=3" in result
    assert "extra_modifier=1" in result
    assert "total=5" in result
    assert "dc=5" in result
    assert "outcome=success" in result


def test_dice_tool_schemas_do_not_expose_seed():
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(0))

    roll_schema = DiceRollTool(roller).parameters()
    check_schema = DiceCheckDCTool(roller).parameters()

    assert "seed" not in roll_schema["properties"]
    assert "seed" not in check_schema["properties"]


def test_dice_mvp_does_not_write_jsonl(tmp_path):
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(0))
    roller.roll("1d20")

    assert list(tmp_path.iterdir()) == []
