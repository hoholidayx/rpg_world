from __future__ import annotations

import pytest

from commons.scene_time import SceneTime


def test_scene_time_strict_parse_format_and_ordinal() -> None:
    value = SceneTime.parse("第 3 年 6 月 15 日 14 时 30 分")

    assert value == SceneTime(3, 6, 15, 14, 30)
    assert value.format() == "第 3 年 6 月 15 日 14 时 30 分"
    assert SceneTime.parse("第 3 年 6 月 15 日 14 时").minute == 0
    assert SceneTime(1, 1, 2, 0).elapsed_minutes_since(
        SceneTime(1, 1, 1, 23)
    ) == 60


@pytest.mark.parametrize(
    "raw",
    [
        "3-6-15 14:30",
        "第 0 年 1 月 1 日 0 时",
        "第 1 年 13 月 1 日 0 时",
        "第 1 年 1 月 32 日 0 时",
        "第 1 年 1 月 1 日 24 时",
    ],
)
def test_scene_time_rejects_noncanonical_or_out_of_range_values(raw: str) -> None:
    with pytest.raises(ValueError):
        SceneTime.parse(raw)
