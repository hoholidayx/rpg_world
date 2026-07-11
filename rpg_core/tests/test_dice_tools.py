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


@pytest.mark.asyncio
async def test_dice_tools_apply_unambiguous_defaults_when_arguments_are_omitted():
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(3))

    roll_result = await DiceRollTool(roller).execute(reason="随机天气")
    check_result = await DiceCheckDCTool(roller, default_dc=15).execute(reason="搜索线索")

    assert "expression=1d20" in roll_result
    assert "reason=随机天气" in roll_result
    assert "expression=1d20" in check_result
    assert "dc=15" in check_result
    assert "reason=搜索线索" in check_result


def test_dice_tool_schemas_do_not_expose_seed():
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(0))

    roll_schema = DiceRollTool(roller).parameters()
    check_schema = DiceCheckDCTool(roller).parameters()

    assert "seed" not in roll_schema["properties"]
    assert "seed" not in check_schema["properties"]


def test_dice_tool_schemas_are_low_level_and_keep_configured_defaults():
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(0))
    roll_tool = DiceRollTool(roller)
    check_tool = DiceCheckDCTool(roller, default_dc=16)

    roll_schema = roll_tool.parameters()
    check_schema = check_tool.parameters()

    assert "底层骰子随机能力" in roll_tool.description
    assert "不应注册到主 LLM" in roll_tool.description
    assert "底层 DC 计算能力" in check_tool.description
    assert "不应注册到主 LLM" in check_tool.description
    assert roll_schema["properties"]["expression"]["default"] == "1d20"
    assert check_schema["properties"]["expression"]["default"] == "1d20"
    assert check_schema["properties"]["dc"]["default"] == 16
    assert "modifier" not in check_schema["properties"]
    assert "required" not in roll_schema
    assert "required" not in check_schema


def test_dice_check_tool_rejects_negative_default_dc():
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(0))

    with pytest.raises(ValueError, match="默认 DC 不能为负数"):
        DiceCheckDCTool(roller, default_dc=-1)


def test_dice_mvp_does_not_write_jsonl(tmp_path):
    roller = DiceRoller(DiceModuleSettings(), rng=random.Random(0))
    roller.roll("1d20")

    assert list(tmp_path.iterdir()) == []
