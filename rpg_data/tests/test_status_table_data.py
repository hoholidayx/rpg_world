from __future__ import annotations

import json

import pytest

from rpg_data.model.status import (
    STATUS_TABLE_SCHEMA_VERSION,
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


def test_status_document_clears_values_without_changing_structure() -> None:
    document = StatusTableDocument.from_rows(
        key_column="字段",
        value_column="当前值",
        rows=[
            StatusTableRow(
                "关系",
                "亲密",
                True,
                {"format": "text"},
                update_rule="关系发生明确变化时更新",
            ),
            StatusTableRow("长期信任", "高"),
        ],
        metadata={"ui": {"compact": True}},
    )

    cleared = document.with_cleared_values()

    assert cleared.data_rows == (("关系", ""), ("长期信任", ""))
    assert cleared.headers == document.headers
    assert cleared.metadata == document.metadata
    assert cleared.rows[0].runtime_key_locked is True
    assert cleared.rows[0].metadata == {"format": "text"}
    assert cleared.rows[0].update_rule == "关系发生明确变化时更新"
    assert document.data_rows == (("关系", "亲密"), ("长期信任", "高"))


def test_status_document_v2_round_trips_rules_and_metadata() -> None:
    document = StatusTableDocument.from_rows(rows=[
        StatusTableRow(
            "关系",
            "疏远",
            metadata={"format": "text"},
            update_rule="  对方明确接受道歉时更新  ",
        ),
        StatusTableRow("长期信任", "低"),
    ])

    restored = parse_status_document(serialize_status_document(document))

    assert restored.schema_version == STATUS_TABLE_SCHEMA_VERSION
    assert restored.rows[0].update_rule == "对方明确接受道歉时更新"
    assert restored.rows[0].metadata == {"format": "text"}


@pytest.mark.parametrize("schema_version", [None, 1, "2", True])
def test_status_document_rejects_non_v2_schema(schema_version: object) -> None:
    raw = json.dumps({
        "schemaVersion": schema_version,
        "kind": "status_table",
        "mode": "key_value",
        "keyColumn": "属性",
        "valueColumn": "值",
        "rows": [],
        "metadata": {},
    })

    with pytest.raises(ValueError, match="schemaVersion"):
        parse_status_document(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("updateFrequency", "realtime"),
        ("deferredIntervalTurns", 5),
        ("llmWritable", True),
    ],
)
def test_status_document_rejects_removed_or_unknown_row_fields(
    field: str,
    value: object,
) -> None:
    raw = json.dumps({
        "schemaVersion": 2,
        "kind": "status_table",
        "mode": "key_value",
        "keyColumn": "属性",
        "valueColumn": "值",
        "rows": [{
            "key": "位置",
            "value": "森林",
            "runtimeKeyLocked": False,
            "updateRule": "",
            "metadata": {},
            field: value,
        }],
        "metadata": {},
    })

    with pytest.raises(ValueError, match="unsupported fields"):
        parse_status_document(raw)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("key", 1, "key must be a string"),
        ("value", None, "value must be a string"),
        ("runtimeKeyLocked", "false", "runtimeKeyLocked must be a boolean"),
        ("updateRule", None, "updateRule must be a string"),
        ("metadata", [], "metadata must be an object"),
    ],
)
def test_status_document_rejects_invalid_v2_row_types(
    field: str,
    value: object,
    message: str,
) -> None:
    row = {
        "key": "位置",
        "value": "森林",
        "runtimeKeyLocked": False,
        "updateRule": "",
        "metadata": {},
    }
    row[field] = value
    raw = json.dumps({
        "schemaVersion": 2,
        "kind": "status_table",
        "mode": "key_value",
        "keyColumn": "属性",
        "valueColumn": "值",
        "rows": [row],
        "metadata": {},
    })

    with pytest.raises(ValueError, match=message):
        parse_status_document(raw)
