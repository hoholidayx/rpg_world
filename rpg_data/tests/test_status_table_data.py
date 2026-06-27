from __future__ import annotations

import pytest

from rpg_data.models import StatusRowRef, StatusTableData


def test_status_table_data_resolves_columns_and_rows_by_name() -> None:
    data = StatusTableData(
        headers=("属性", "值", "备注"),
        rows=(("时间", "早晨", ""), ("位置", "森林", "安全")),
    )

    assert data.column_index("值") == 1
    assert data.column_index(2) == 2
    assert data.find_row_indexes("属性", "位置") == (1,)
    assert data.cell(StatusRowRef.match("属性", "位置"), "值") == "森林"

    with pytest.raises(KeyError):
        data.column_index("不存在")


def test_status_row_ref_match_reports_missing_and_ambiguous_rows() -> None:
    data = StatusTableData(
        headers=("属性", "值"),
        rows=(("位置", "森林"), ("位置", "城堡")),
    )

    with pytest.raises(FileNotFoundError):
        data.row_index(StatusRowRef.match("属性", "天气"))

    with pytest.raises(ValueError):
        data.row_index(StatusRowRef.match("属性", "位置"))


def test_status_table_data_write_helpers_are_immutable() -> None:
    data = StatusTableData(
        headers=("属性", "值"),
        rows=(("时间", "早晨"), ("位置", "森林")),
    )

    changed = data.with_cell(StatusRowRef.match("属性", "位置"), "值", "城堡")
    appended = changed.with_appended_row(["天气", "雨", "ignored"])
    replaced = appended.with_replaced_row(0, ["时间"])
    deleted = replaced.with_deleted_row(StatusRowRef.match("属性", "位置"))

    assert data.rows == (("时间", "早晨"), ("位置", "森林"))
    assert changed.rows == (("时间", "早晨"), ("位置", "城堡"))
    assert appended.rows[-1] == ("天气", "雨")
    assert replaced.rows[0] == ("时间", "")
    assert deleted.rows == (("时间", ""), ("天气", "雨"))


def test_status_table_data_key_value_helpers_update_append_and_delete() -> None:
    data = StatusTableData(headers=("属性", "值"), rows=(("位置", "森林"),))

    updated = data.with_key_value("位置", "城堡")
    appended = updated.with_key_value("天气", "雨")
    deleted = appended.without_key("位置")

    assert updated.rows == (("位置", "城堡"),)
    assert appended.rows == (("位置", "城堡"), ("天气", "雨"))
    assert deleted.rows == (("天气", "雨"),)
