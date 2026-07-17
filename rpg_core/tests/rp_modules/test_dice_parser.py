from __future__ import annotations

import pytest

from rpg_core.rp_modules.dice.parser import DiceParseError, parse_dice_expression


@pytest.mark.parametrize(
    ("raw", "count", "sides", "modifier", "normalized"),
    [
        ("d20", 1, 20, 0, "1d20"),
        ("1d20", 1, 20, 0, "1d20"),
        ("2d6+3", 2, 6, 3, "2d6+3"),
        ("4d6-2", 4, 6, -2, "4d6-2"),
        ("1d100", 1, 100, 0, "1d100"),
    ],
)
def test_parse_valid_dice_expressions(raw, count, sides, modifier, normalized):
    parsed = parse_dice_expression(raw)

    assert parsed.count == count
    assert parsed.sides == sides
    assert parsed.modifier == modifier
    assert parsed.normalized == normalized


@pytest.mark.parametrize(
    "raw",
    ["", "abc", "0d6", "1d1", "2d6+1d4", "d20 advantage"],
)
def test_parse_rejects_invalid_dice_expressions(raw):
    with pytest.raises(DiceParseError):
        parse_dice_expression(raw)


def test_parse_enforces_boundaries():
    with pytest.raises(DiceParseError):
        parse_dice_expression("101d6", max_dice_count=100)
    with pytest.raises(DiceParseError):
        parse_dice_expression("1d1001", max_die_sides=1000)
    with pytest.raises(DiceParseError):
        parse_dice_expression("1d20+100001")
