"""Canonical typed persistence contracts for Status tables."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from typing import Mapping

from commons.types import JsonObject, JsonValue


class StatusKind(StrEnum):
    SCENE = "scene"
    NORMAL = "normal"


class StatusOrigin(StrEnum):
    STORY_COPY = "story_copy"
    SESSION_NATIVE = "session_native"


STATUS_TABLE_KIND = "status_table"
STATUS_TABLE_MODE_KEY_VALUE = "key_value"
STATUS_TABLE_SCHEMA_VERSION = 2
STATUS_KIND_SCENE = StatusKind.SCENE
STATUS_KIND_NORMAL = StatusKind.NORMAL
STATUS_ORIGIN_STORY_COPY = StatusOrigin.STORY_COPY
STATUS_ORIGIN_SESSION_NATIVE = StatusOrigin.SESSION_NATIVE
STATUS_KEY_COLUMN = "属性"
STATUS_VALUE_COLUMN = "值"
STATUS_ROW_UPDATE_RULE_KEY = "updateRule"
STATUS_METADATA_STORY_SOURCE_KEY = "storyStatusSource"
_STATUS_DOCUMENT_KEYS = frozenset({
    "schemaVersion",
    "kind",
    "mode",
    "keyColumn",
    "valueColumn",
    "rows",
    "metadata",
})
_STATUS_ROW_KEYS = frozenset({
    "key",
    "value",
    "runtimeKeyLocked",
    STATUS_ROW_UPDATE_RULE_KEY,
    "metadata",
})


@dataclass(frozen=True)
class SessionStatusResetResult:
    """Counts produced by resetting one session's status-table runtime."""

    session_id: str
    story_tables_cleared: int = 0
    story_tables_initialized: int = 0
    native_tables_reset: int = 0


@dataclass(frozen=True)
class SessionStatusDocumentWrite:
    """Caller-prepared document replacement for one Session status table."""

    table_id: int
    document: "StatusTableDocument"


@dataclass(frozen=True)
class SessionStatusResetPlan:
    """Explicit status-table mutations applied atomically by the data layer."""

    delete_table_ids: tuple[int, ...] = ()
    document_writes: tuple[SessionStatusDocumentWrite, ...] = ()
    story_status_table_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class StatusDocumentWrite:
    """One caller-prepared document replacement in an atomic write batch."""

    table_id: int
    expected_status_kind: StatusKind
    document: "StatusTableDocument"
    base_document: "StatusTableDocument | None" = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_status_kind",
            validate_status_kind(self.expected_status_kind),
        )


@dataclass(frozen=True)
class StatusDocumentSaveResult:
    """Persisted table plus a non-blocking baseline diagnostic."""

    table: "SessionStatusTable"
    baseline_matched: bool


@dataclass(frozen=True)
class StatusDocumentBatchResult:
    """Atomic batch result with tables whose caller baseline had drifted."""

    tables: tuple["SessionStatusTable", ...]
    baseline_mismatch_table_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class StatusCharacterIdentity:
    """Character identity projected for a status-table association read."""

    character_id: int
    character_name: str


@dataclass(frozen=True)
class StatusStoryTableIdentity:
    """Current Story definition associated with a copied status table."""

    story_status_table_id: int
    character: StatusCharacterIdentity | None = None


@dataclass(frozen=True)
class StatusContextCandidate:
    """Efficient persistence read model; Core decides Context visibility."""

    table: "SessionStatusTable"
    referenced_character: StatusCharacterIdentity | None = None
    current_story_table: StatusStoryTableIdentity | None = None


@dataclass(frozen=True)
class StoryStatusSourceSnapshot:
    """Denormalized Story source stored in Session table metadata."""

    story_status_table_id: int | None = None
    character_id: int | None = None
    character_name: str | None = None

    @property
    def has_character_binding(self) -> bool:
        return (
            self.character_id is not None
            or bool((self.character_name or "").strip())
        )

    def to_json_dict(self) -> JsonObject:
        return {
            "storyStatusTableId": self.story_status_table_id,
            "characterId": self.character_id,
            "characterName": self.character_name,
        }


@dataclass(frozen=True)
class SessionStatusMetadata:
    """Typed access to known metadata while preserving extension fields."""

    values: Mapping[str, JsonValue] = field(default_factory=dict)
    story_source: StoryStatusSourceSnapshot | None = None

    def with_story_source(
        self,
        story_source: StoryStatusSourceSnapshot,
    ) -> "SessionStatusMetadata":
        values = dict(self.values)
        values[STATUS_METADATA_STORY_SOURCE_KEY] = story_source.to_json_dict()
        return replace(self, values=values, story_source=story_source)


def parse_session_status_metadata(raw: str) -> SessionStatusMetadata:
    try:
        loaded: object = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        loaded = {}
    values = _json_object(loaded)
    raw_source = values.get(STATUS_METADATA_STORY_SOURCE_KEY)
    if not isinstance(raw_source, dict):
        return SessionStatusMetadata(values=values)
    return SessionStatusMetadata(
        values=values,
        story_source=StoryStatusSourceSnapshot(
            story_status_table_id=_optional_positive_int(
                raw_source.get("storyStatusTableId")
            ),
            character_id=_optional_positive_int(raw_source.get("characterId")),
            character_name=_optional_text(raw_source.get("characterName")),
        ),
    )


def serialize_session_status_metadata(metadata: SessionStatusMetadata) -> str:
    return json.dumps(
        dict(metadata.values),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _optional_positive_int(value: JsonValue | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_text(value: JsonValue | None) -> str | None:
    if value is None or isinstance(value, (list, dict)):
        return None
    return str(value)


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


@dataclass(frozen=True)
class StatusRowRef:
    """Reference a status table row by index or by matching a cell value."""

    row_index: int | None = None
    match_column: int | str | None = None
    match_value: str | None = None

    @staticmethod
    def index(row_index: int) -> "StatusRowRef":
        return StatusRowRef(row_index=row_index)

    @staticmethod
    def match(column: int | str, value: str) -> "StatusRowRef":
        return StatusRowRef(match_column=column, match_value=str(value))


@dataclass(frozen=True)
class StatusTableData:
    """Immutable helper for reading and editing key-value status data."""

    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()

    def column_index(self, column: int | str) -> int:
        if isinstance(column, int):
            if column < 0 or column >= len(self.headers):
                raise IndexError(f"Status table column index out of range: {column}")
            return column
        name = str(column)
        try:
            return self.headers.index(name)
        except ValueError as exc:
            raise KeyError(f"Status table column not found: {name}") from exc

    def find_row_indexes(self, column: int | str, value: str) -> tuple[int, ...]:
        col = self.column_index(column)
        expected = str(value)
        return tuple(
            idx
            for idx, row in enumerate(self.rows)
            if col < len(row) and row[col] == expected
        )

    def row_index(self, ref: int | StatusRowRef) -> int:
        if isinstance(ref, int):
            return self._validate_row_index(ref)
        if ref.row_index is not None:
            return self._validate_row_index(ref.row_index)
        if ref.match_column is None or ref.match_value is None:
            raise ValueError("Status row reference must specify an index or match")
        matches = self.find_row_indexes(ref.match_column, ref.match_value)
        if not matches:
            raise FileNotFoundError(f"Status table row not found: {ref.match_value}")
        if len(matches) > 1:
            raise ValueError(f"Status table row match is ambiguous: {ref.match_value}")
        return matches[0]

    def cell(self, ref: int | StatusRowRef, column: int | str) -> str:
        row_idx = self.row_index(ref)
        col_idx = self.column_index(column)
        row = self.rows[row_idx]
        return row[col_idx] if col_idx < len(row) else ""

    def with_cell(
        self,
        ref: int | StatusRowRef,
        column: int | str,
        value: str,
    ) -> "StatusTableData":
        row_idx = self.row_index(ref)
        col_idx = self.column_index(column)
        rows = [list(self._normalize_row(row)) for row in self.rows]
        rows[row_idx][col_idx] = str(value)
        return StatusTableData(
            headers=self.headers,
            rows=tuple(tuple(row) for row in rows),
        )

    def with_appended_row(self, values: object) -> "StatusTableData":
        return StatusTableData(
            headers=self.headers,
            rows=self.rows + (self._normalize_row(values),),
        )

    def with_replaced_row(
        self,
        ref: int | StatusRowRef,
        values: object,
    ) -> "StatusTableData":
        row_idx = self.row_index(ref)
        rows = list(self.rows)
        rows[row_idx] = self._normalize_row(values)
        return StatusTableData(headers=self.headers, rows=tuple(rows))

    def with_deleted_row(self, ref: int | StatusRowRef) -> "StatusTableData":
        row_idx = self.row_index(ref)
        return StatusTableData(
            headers=self.headers,
            rows=tuple(row for idx, row in enumerate(self.rows) if idx != row_idx),
        )

    def with_key_value(
        self,
        key: str,
        value: str,
        key_column: int | str = STATUS_KEY_COLUMN,
        value_column: int | str = STATUS_VALUE_COLUMN,
    ) -> "StatusTableData":
        key_idx = self.column_index(key_column)
        value_idx = self.column_index(value_column)
        matches = self.find_row_indexes(key_idx, key)
        if len(matches) > 1:
            raise ValueError(f"Status table key is ambiguous: {key}")
        if matches:
            return self.with_cell(matches[0], value_idx, value)
        row = [""] * len(self.headers)
        row[key_idx] = str(key)
        row[value_idx] = str(value)
        return self.with_appended_row(row)

    def without_key(
        self,
        key: str,
        key_column: int | str = STATUS_KEY_COLUMN,
    ) -> "StatusTableData":
        matches = self.find_row_indexes(key_column, key)
        if not matches:
            raise FileNotFoundError(f"Status table key not found: {key}")
        if len(matches) > 1:
            raise ValueError(f"Status table key is ambiguous: {key}")
        return self.with_deleted_row(matches[0])

    def _validate_row_index(self, row_index: int) -> int:
        if row_index < 0 or row_index >= len(self.rows):
            raise IndexError(f"Status table row index out of range: {row_index}")
        return row_index

    def _normalize_row(self, values: object) -> tuple[str, ...]:
        if isinstance(values, (str, bytes)):
            raw = (str(values),)
        else:
            try:
                raw = tuple(str(item) for item in values)  # type: ignore[operator]
            except TypeError:
                raw = (str(values),)
        if not self.headers:
            return raw
        target_len = len(self.headers)
        if len(raw) < target_len:
            raw = raw + ("",) * (target_len - len(raw))
        return raw[:target_len]


@dataclass(frozen=True)
class StatusTableRow:
    key: str
    value: str
    runtime_key_locked: bool = False
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    update_rule: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "update_rule", str(self.update_rule or "").strip())

    def to_json_dict(self) -> JsonObject:
        return {
            "key": self.key,
            "value": self.value,
            "runtimeKeyLocked": self.runtime_key_locked,
            STATUS_ROW_UPDATE_RULE_KEY: self.update_rule,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StatusTableDocument:
    schema_version: int = STATUS_TABLE_SCHEMA_VERSION
    kind: str = STATUS_TABLE_KIND
    mode: str = STATUS_TABLE_MODE_KEY_VALUE
    key_column: str = STATUS_KEY_COLUMN
    value_column: str = STATUS_VALUE_COLUMN
    rows: tuple[StatusTableRow, ...] = ()
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    @classmethod
    def from_rows(
        cls,
        *,
        key_column: str = STATUS_KEY_COLUMN,
        value_column: str = STATUS_VALUE_COLUMN,
        rows: tuple[StatusTableRow, ...] | list[StatusTableRow] | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> "StatusTableDocument":
        return cls(
            key_column=str(key_column or STATUS_KEY_COLUMN),
            value_column=str(value_column or STATUS_VALUE_COLUMN),
            rows=tuple(rows or ()),
            metadata=dict(metadata or {}),
        ).validated()

    @classmethod
    def from_data(
        cls,
        data: StatusTableData,
        *,
        locked_keys: set[str] | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> "StatusTableDocument":
        key_column = data.headers[0] if data.headers else STATUS_KEY_COLUMN
        value_column = data.headers[1] if len(data.headers) > 1 else STATUS_VALUE_COLUMN
        locked = locked_keys or set()
        rows = tuple(
            StatusTableRow(
                key=row[0] if row else "",
                value=row[1] if len(row) > 1 else "",
                runtime_key_locked=(row[0] if row else "") in locked,
            )
            for row in data.rows
        )
        return cls.from_rows(
            key_column=key_column,
            value_column=value_column,
            rows=rows,
            metadata=metadata,
        )

    @property
    def headers(self) -> tuple[str, str]:
        return (self.key_column, self.value_column)

    @property
    def data_rows(self) -> tuple[tuple[str, str], ...]:
        return tuple((row.key, row.value) for row in self.rows)

    def to_data(self) -> StatusTableData:
        return StatusTableData(headers=self.headers, rows=self.data_rows)

    def with_data(self, data: StatusTableData) -> "StatusTableDocument":
        rows_by_key = {row.key: row for row in self.rows}
        rows = tuple(
            StatusTableRow(
                key=row[0] if row else "",
                value=row[1] if len(row) > 1 else "",
                runtime_key_locked=(
                    rows_by_key[row[0]].runtime_key_locked
                    if row and row[0] in rows_by_key
                    else False
                ),
                metadata=(
                    dict(rows_by_key[row[0]].metadata)
                    if row and row[0] in rows_by_key
                    else {}
                ),
                update_rule=(
                    rows_by_key[row[0]].update_rule
                    if row and row[0] in rows_by_key
                    else ""
                ),
            )
            for row in data.rows
        )
        key_column = data.headers[0] if data.headers else self.key_column
        value_column = data.headers[1] if len(data.headers) > 1 else self.value_column
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=key_column,
            value_column=value_column,
            rows=rows,
            metadata=dict(self.metadata),
        ).validated()

    def with_key_value(self, key: str, value: str) -> "StatusTableDocument":
        expected = str(key)
        updated: list[StatusTableRow] = []
        matched = False
        for row in self.rows:
            if row.key == expected:
                updated.append(StatusTableRow(
                    row.key,
                    str(value),
                    row.runtime_key_locked,
                    dict(row.metadata),
                    row.update_rule,
                ))
                matched = True
            else:
                updated.append(row)
        if not matched:
            updated.append(StatusTableRow(expected, str(value), False, {}))
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(updated),
            metadata=dict(self.metadata),
        ).validated()

    def with_existing_values(
        self,
        updates: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    ) -> "StatusTableDocument":
        """Return a copy with values replaced for existing keys only."""
        materialized = [(str(key), str(value)) for key, value in updates]
        if not materialized:
            raise ValueError("Status table value updates must not be empty")

        keys = [key for key, _value in materialized]
        if len(set(keys)) != len(keys):
            raise ValueError("Status table value updates contain duplicate keys")

        existing_keys = {row.key for row in self.rows}
        missing = [key for key in keys if key not in existing_keys]
        if missing:
            raise FileNotFoundError(f"Status table key not found: {missing[0]}")

        values_by_key = dict(materialized)
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(
                StatusTableRow(
                    row.key,
                    values_by_key.get(row.key, row.value),
                    row.runtime_key_locked,
                    dict(row.metadata),
                    row.update_rule,
                )
                for row in self.rows
            ),
            metadata=dict(self.metadata),
        ).validated()

    def with_cleared_values(self) -> "StatusTableDocument":
        """Return a copy with every value cleared and all structure preserved."""

        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(
                StatusTableRow(
                    row.key,
                    "",
                    row.runtime_key_locked,
                    dict(row.metadata),
                    row.update_rule,
                )
                for row in self.rows
            ),
            metadata=dict(self.metadata),
        ).validated()

    def without_key(self, key: str) -> "StatusTableDocument":
        expected = str(key)
        if expected not in {row.key for row in self.rows}:
            raise FileNotFoundError(f"Status table key not found: {key}")
        return StatusTableDocument(
            schema_version=self.schema_version,
            kind=self.kind,
            mode=self.mode,
            key_column=self.key_column,
            value_column=self.value_column,
            rows=tuple(row for row in self.rows if row.key != expected),
            metadata=dict(self.metadata),
        ).validated()

    def row_for_key(self, key: str) -> StatusTableRow | None:
        expected = str(key)
        for row in self.rows:
            if row.key == expected:
                return row
        return None

    def validated(self) -> "StatusTableDocument":
        if self.schema_version != STATUS_TABLE_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported status table schemaVersion: "
                f"{self.schema_version}; expected {STATUS_TABLE_SCHEMA_VERSION}"
            )
        if self.kind != STATUS_TABLE_KIND:
            raise ValueError(f"Unsupported status table kind: {self.kind}")
        if self.mode != STATUS_TABLE_MODE_KEY_VALUE:
            raise ValueError(f"Unsupported status table mode: {self.mode}")
        seen: set[str] = set()
        for row in self.rows:
            if not row.key:
                raise ValueError("Status table row key must not be empty")
            if row.key in seen:
                raise ValueError(f"Status table key is duplicated: {row.key}")
            seen.add(row.key)
        return self

    def to_json_dict(self) -> JsonObject:
        return {
            "schemaVersion": self.schema_version,
            "kind": self.kind,
            "mode": self.mode,
            "keyColumn": self.key_column,
            "valueColumn": self.value_column,
            "rows": [row.to_json_dict() for row in self.rows],
            "metadata": dict(self.metadata),
        }


def parse_status_document(raw: str) -> StatusTableDocument:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Status table document JSON is invalid") from exc
    if not isinstance(data, dict):
        raise ValueError("Status table document must be an object")
    unknown_document_keys = set(data).difference(_STATUS_DOCUMENT_KEYS)
    if unknown_document_keys:
        raise ValueError(
            "Status table document contains unsupported fields: "
            + ", ".join(sorted(str(key) for key in unknown_document_keys))
        )
    schema_version = data.get("schemaVersion")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != STATUS_TABLE_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported status table schemaVersion: "
            f"{schema_version}; expected {STATUS_TABLE_SCHEMA_VERSION}"
        )
    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list):
        raise ValueError("Status table rows must be an array")
    rows: list[StatusTableRow] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            raise ValueError("Status table row must be an object")
        unknown_row_keys = set(item).difference(_STATUS_ROW_KEYS)
        if unknown_row_keys:
            raise ValueError(
                "Status table row contains unsupported fields: "
                + ", ".join(sorted(str(key) for key in unknown_row_keys))
            )
        raw_key = item.get("key")
        if not isinstance(raw_key, str):
            raise ValueError("Status table row key must be a string")
        raw_value = item.get("value", "")
        if not isinstance(raw_value, str):
            raise ValueError("Status table row value must be a string")
        raw_runtime_key_locked = item.get("runtimeKeyLocked", False)
        if not isinstance(raw_runtime_key_locked, bool):
            raise ValueError(
                "Status table row runtimeKeyLocked must be a boolean"
            )
        raw_update_rule = item.get(STATUS_ROW_UPDATE_RULE_KEY, "")
        if not isinstance(raw_update_rule, str):
            raise ValueError("Status table row updateRule must be a string")
        raw_metadata = item.get("metadata", {})
        if not isinstance(raw_metadata, dict):
            raise ValueError("Status table row metadata must be an object")
        rows.append(StatusTableRow(
            key=raw_key,
            value=raw_value,
            runtime_key_locked=raw_runtime_key_locked,
            update_rule=raw_update_rule,
            metadata=raw_metadata,
        ))
    raw_metadata = data.get("metadata", {})
    if not isinstance(raw_metadata, dict):
        raise ValueError("Status table metadata must be an object")
    document_strings = {
        "kind": data.get("kind", STATUS_TABLE_KIND),
        "mode": data.get("mode", STATUS_TABLE_MODE_KEY_VALUE),
        "keyColumn": data.get("keyColumn", STATUS_KEY_COLUMN),
        "valueColumn": data.get("valueColumn", STATUS_VALUE_COLUMN),
    }
    for field_name, field_value in document_strings.items():
        if not isinstance(field_value, str):
            raise ValueError(
                f"Status table document {field_name} must be a string"
            )
    return StatusTableDocument(
        schema_version=schema_version,
        kind=document_strings["kind"],
        mode=document_strings["mode"],
        key_column=document_strings["keyColumn"],
        value_column=document_strings["valueColumn"],
        rows=tuple(rows),
        metadata=raw_metadata,
    ).validated()


def serialize_status_document(document: StatusTableDocument) -> str:
    return json.dumps(document.validated().to_json_dict(), ensure_ascii=False, separators=(",", ":"))


def validate_status_kind(value: str | StatusKind) -> StatusKind:
    kind = str(value or STATUS_KIND_NORMAL)
    try:
        return StatusKind(kind)
    except ValueError as exc:
        raise ValueError(f"Unsupported status kind: {kind}") from exc


def validate_status_origin(value: str | StatusOrigin) -> StatusOrigin:
    origin = str(value)
    try:
        return StatusOrigin(origin)
    except ValueError as exc:
        raise ValueError(f"Unsupported status origin: {origin}") from exc


@dataclass(frozen=True)
class StoryStatusTable:
    id: int
    workspace_id: str
    story_id: int
    story_character_id: int | None
    name: str
    status_kind: StatusKind = STATUS_KIND_NORMAL
    description: str = ""
    document: StatusTableDocument = field(default_factory=StatusTableDocument)
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status_kind", validate_status_kind(self.status_kind))

    @property
    def headers(self) -> tuple[str, str]:
        return self.document.headers

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        return self.document.data_rows

    @property
    def data(self) -> StatusTableData:
        return self.document.to_data()

    def to_dict(self) -> dict[str, object]:
        return _status_table_as_dict(self)


@dataclass(frozen=True)
class SessionStatusTable:
    id: int
    session_id: str
    workspace_id: str
    story_id: int
    source_story_status_table_id: int | None
    origin: StatusOrigin
    name: str
    status_kind: StatusKind = STATUS_KIND_NORMAL
    description: str = ""
    document: StatusTableDocument = field(default_factory=StatusTableDocument)
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin", validate_status_origin(self.origin))
        object.__setattr__(self, "status_kind", validate_status_kind(self.status_kind))

    @property
    def headers(self) -> tuple[str, str]:
        return self.document.headers

    @property
    def rows(self) -> tuple[tuple[str, str], ...]:
        return self.document.data_rows

    @property
    def data(self) -> StatusTableData:
        return self.document.to_data()

    def to_dict(self) -> dict[str, object]:
        return _status_table_as_dict(self)


def _status_table_as_dict(
    table: StoryStatusTable | SessionStatusTable,
) -> dict[str, object]:
    data = asdict(table)
    data["document"] = table.document.to_json_dict()
    data["headers"] = list(table.headers)
    data["rows"] = [list(row) for row in table.rows]
    return data


__all__ = [
    name
    for name in globals()
    if name.startswith("STATUS_")
    or name.startswith("SessionStatus")
    or name.startswith("Status")
    or name.startswith("StoryStatus")
    or name in {
        "parse_session_status_metadata",
        "parse_status_document",
        "serialize_session_status_metadata",
        "serialize_status_document",
        "validate_status_kind",
        "validate_status_origin",
    }
]
