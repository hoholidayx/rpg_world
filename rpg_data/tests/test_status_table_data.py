from __future__ import annotations

import json

import pytest

from rpg_data.models import (
    STATUS_UPDATE_FREQUENCY_DEFERRED,
    STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
    StatusRowRef,
    StatusTableData,
    StatusTableDocument,
    StatusTableRow,
    parse_status_document,
    serialize_status_document,
)


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


def test_status_document_updates_existing_values_without_changing_structure() -> None:
    document = StatusTableDocument.from_rows(
        rows=[
            StatusTableRow("生命", "10", True, {"format": "integer"}),
            StatusTableRow("法力", "5", False, {"format": "integer"}),
        ],
        metadata={"ui": {"compact": True}},
    )

    updated = document.with_existing_values([("法力", "3"), ("生命", "8")])

    assert updated.data_rows == (("生命", "8"), ("法力", "3"))
    assert updated.rows[0].runtime_key_locked is True
    assert updated.rows[0].metadata == {"format": "integer"}
    assert updated.metadata == {"ui": {"compact": True}}
    assert document.data_rows == (("生命", "10"), ("法力", "5"))

    with pytest.raises(FileNotFoundError, match="不存在"):
        document.with_existing_values([("不存在", "1")])
    with pytest.raises(ValueError, match="duplicate"):
        document.with_existing_values([("生命", "9"), ("生命", "8")])
    with pytest.raises(ValueError, match="empty"):
        document.with_existing_values([])


def test_status_update_policy_round_trips_and_legacy_defaults_to_realtime() -> None:
    document = StatusTableDocument.from_rows(rows=[
        StatusTableRow(
            "关系",
            "疏远",
            update_frequency=STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN,
            update_rule="对方明确接受道歉时更新",
        ),
        StatusTableRow(
            "长期信任",
            "低",
            update_frequency=STATUS_UPDATE_FREQUENCY_DEFERRED,
            deferred_interval_turns=8,
        ),
    ])

    restored = parse_status_document(serialize_status_document(document))

    assert restored.rows[0].update_rule == "对方明确接受道歉时更新"
    assert restored.rows[1].deferred_interval_turns == 8
    legacy = parse_status_document(
        '{"rows":[{"key":"位置","value":"森林"}]}'
    )
    assert legacy.rows[0].update_frequency == "realtime"


def test_status_update_policy_rejects_invalid_combinations() -> None:
    with pytest.raises(ValueError, match="require updateRule"):
        StatusTableDocument.from_rows(rows=[
            StatusTableRow("关系", "普通", update_frequency="event_driven")
        ])
    with pytest.raises(ValueError, match="only supported for deferred"):
        StatusTableDocument.from_rows(rows=[
            StatusTableRow("位置", "森林", deferred_interval_turns=3)
        ])
    with pytest.raises(ValueError, match="positive integer"):
        StatusTableDocument.from_rows(rows=[
            StatusTableRow(
                "长期信任",
                "低",
                update_frequency="deferred",
                deferred_interval_turns=1.5,  # type: ignore[arg-type]
            )
        ])


@pytest.mark.parametrize("value", [True, "5", 1.5])
def test_status_document_rejects_malformed_deferred_interval(value: object) -> None:
    raw = json.dumps({
        "rows": [{
            "key": "长期信任",
            "value": "低",
            "updateFrequency": "deferred",
            "deferredIntervalTurns": value,
        }]
    })

    with pytest.raises(ValueError, match="positive integer"):
        parse_status_document(raw)
