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
    TEMPLATE_COPY = "template_copy"
    SESSION_NATIVE = "session_native"


class StoryStatusMountOrigin(StrEnum):
    SYSTEM = "system_mount"
    STORY_TEMPLATE = "story_template"


class StatusUpdateFrequency(StrEnum):
    REALTIME = "realtime"
    EVENT_DRIVEN = "event_driven"
    DEFERRED = "deferred"
    MANUAL = "manual"


STATUS_TABLE_KIND = "status_table"
STATUS_TABLE_MODE_KEY_VALUE = "key_value"
STATUS_KIND_SCENE = StatusKind.SCENE
STATUS_KIND_NORMAL = StatusKind.NORMAL
STATUS_ORIGIN_TEMPLATE_COPY = StatusOrigin.TEMPLATE_COPY
STATUS_ORIGIN_SESSION_NATIVE = StatusOrigin.SESSION_NATIVE
STORY_STATUS_MOUNT_ORIGIN_SYSTEM = StoryStatusMountOrigin.SYSTEM
STORY_STATUS_MOUNT_ORIGIN_STORY_TEMPLATE = StoryStatusMountOrigin.STORY_TEMPLATE
STATUS_KEY_COLUMN = "属性"
STATUS_VALUE_COLUMN = "值"
STATUS_UPDATE_FREQUENCY_REALTIME = StatusUpdateFrequency.REALTIME
STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN = StatusUpdateFrequency.EVENT_DRIVEN
STATUS_UPDATE_FREQUENCY_DEFERRED = StatusUpdateFrequency.DEFERRED
STATUS_UPDATE_FREQUENCY_MANUAL = StatusUpdateFrequency.MANUAL
STATUS_UPDATE_FREQUENCIES = frozenset(StatusUpdateFrequency)
STATUS_ROW_UPDATE_FREQUENCY_KEY = "updateFrequency"
STATUS_ROW_UPDATE_RULE_KEY = "updateRule"
STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY = "deferredIntervalTurns"
STATUS_METADATA_STORY_MOUNT_KEY = "storyStatusMount"


@dataclass(frozen=True)
class SessionStatusResetResult:
    """Counts produced by resetting one session's status-table runtime."""

    session_id: str
    template_tables_cleared: int = 0
    template_tables_initialized: int = 0
    native_tables_reset: int = 0
    deferred_progress_cleared: int = 0


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
    deferred_progress_table_ids: tuple[int, ...] = ()
    story_mount_ids: tuple[int, ...] = ()


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
class StatusProgressWrite:
    """One caller-prepared deferred-progress ledger value."""

    table_id: int
    field_key: str
    last_processed_turn_id: int


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

    character_mount_id: int
    character_id: int
    character_name: str


@dataclass(frozen=True)
class StatusStoryMountIdentity:
    """Current Story mount association for a copied status table."""

    mount_id: int
    mount_origin: StoryStatusMountOrigin
    character: StatusCharacterIdentity | None = None


@dataclass(frozen=True)
class StatusContextCandidate:
    """Efficient persistence read model; Core decides Context visibility."""

    table: "SessionStatusTable"
    referenced_character: StatusCharacterIdentity | None = None
    current_story_mount: StatusStoryMountIdentity | None = None


@dataclass(frozen=True)
class StoryStatusMountSnapshot:
    """Denormalized mount snapshot stored in Session table metadata."""

    mount_id: int | None = None
    mount_origin: StoryStatusMountOrigin = STORY_STATUS_MOUNT_ORIGIN_SYSTEM
    character_mount_id: int | None = None
    character_id: int | None = None
    character_name: str | None = None

    @property
    def has_character_binding(self) -> bool:
        return (
            self.character_mount_id is not None
            or self.character_id is not None
            or bool((self.character_name or "").strip())
        )

    def to_json_dict(self) -> JsonObject:
        return {
            "mountId": self.mount_id,
            "mountOrigin": self.mount_origin,
            "characterMountId": self.character_mount_id,
            "characterId": self.character_id,
            "characterName": self.character_name,
        }


@dataclass(frozen=True)
class SessionStatusMetadata:
    """Typed access to known metadata while preserving extension fields."""

    values: Mapping[str, JsonValue] = field(default_factory=dict)
    story_mount: StoryStatusMountSnapshot | None = None

    def with_story_mount(
        self,
        story_mount: StoryStatusMountSnapshot,
    ) -> "SessionStatusMetadata":
        values = dict(self.values)
        values[STATUS_METADATA_STORY_MOUNT_KEY] = story_mount.to_json_dict()
        return replace(self, values=values, story_mount=story_mount)


def parse_session_status_metadata(raw: str) -> SessionStatusMetadata:
    try:
        loaded: object = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        loaded = {}
    values = _json_object(loaded)
    raw_mount = values.get(STATUS_METADATA_STORY_MOUNT_KEY)
    if not isinstance(raw_mount, dict):
        return SessionStatusMetadata(values=values)
    raw_origin = raw_mount.get("mountOrigin")
    try:
        mount_origin = validate_story_status_mount_origin(
            str(raw_origin or STORY_STATUS_MOUNT_ORIGIN_SYSTEM)
        )
    except ValueError:
        mount_origin = STORY_STATUS_MOUNT_ORIGIN_SYSTEM
    return SessionStatusMetadata(
        values=values,
        story_mount=StoryStatusMountSnapshot(
            mount_id=_optional_positive_int(raw_mount.get("mountId")),
            mount_origin=mount_origin,
            character_mount_id=_optional_positive_int(
                raw_mount.get("characterMountId")
            ),
            character_id=_optional_positive_int(raw_mount.get("characterId")),
            character_name=_optional_text(raw_mount.get("characterName")),
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
    update_frequency: StatusUpdateFrequency = STATUS_UPDATE_FREQUENCY_REALTIME
    update_rule: str = ""
    deferred_interval_turns: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "update_frequency",
            validate_status_update_policy(
                self.update_frequency,
                update_rule=self.update_rule,
                deferred_interval_turns=self.deferred_interval_turns,
            ),
        )
        object.__setattr__(self, "update_rule", self.update_rule.strip())

    def to_json_dict(self) -> JsonObject:
        return {
            "key": self.key,
            "value": self.value,
            "runtimeKeyLocked": self.runtime_key_locked,
            "metadata": dict(self.metadata),
            STATUS_ROW_UPDATE_FREQUENCY_KEY: self.update_frequency,
            STATUS_ROW_UPDATE_RULE_KEY: self.update_rule,
            STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY: self.deferred_interval_turns,
        }


@dataclass(frozen=True)
class StatusDeferredProgress:
    session_status_table_id: int
    field_key: str
    last_processed_turn_id: int = 0


@dataclass(frozen=True)
class StatusTableDocument:
    schema_version: int = 1
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
                update_frequency=(
                    rows_by_key[row[0]].update_frequency
                    if row and row[0] in rows_by_key
                    else STATUS_UPDATE_FREQUENCY_REALTIME
                ),
                update_rule=(
                    rows_by_key[row[0]].update_rule
                    if row and row[0] in rows_by_key
                    else ""
                ),
                deferred_interval_turns=(
                    rows_by_key[row[0]].deferred_interval_turns
                    if row and row[0] in rows_by_key
                    else None
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
                    row.update_frequency,
                    row.update_rule,
                    row.deferred_interval_turns,
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
                    row.update_frequency,
                    row.update_rule,
                    row.deferred_interval_turns,
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
                    row.update_frequency,
                    row.update_rule,
                    row.deferred_interval_turns,
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
            validate_status_update_policy(
                row.update_frequency,
                update_rule=row.update_rule,
                deferred_interval_turns=row.deferred_interval_turns,
            )
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
    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list):
        raw_rows = []
    rows: list[StatusTableRow] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        raw_metadata = item.get("metadata", {})
        rows.append(StatusTableRow(
            key=str(item.get("key", "")),
            value=str(item.get("value", "")),
            runtime_key_locked=bool(item.get("runtimeKeyLocked", False)),
            metadata=raw_metadata if isinstance(raw_metadata, dict) else {},
            update_frequency=str(
                item.get(STATUS_ROW_UPDATE_FREQUENCY_KEY)
                or STATUS_UPDATE_FREQUENCY_REALTIME
            ),
            update_rule=str(item.get(STATUS_ROW_UPDATE_RULE_KEY) or ""),
            deferred_interval_turns=_parse_deferred_interval_turns(
                item.get(STATUS_ROW_DEFERRED_INTERVAL_TURNS_KEY)
            ),
        ))
    raw_metadata = data.get("metadata", {})
    return StatusTableDocument(
        schema_version=int(data.get("schemaVersion") or 1),
        kind=str(data.get("kind") or STATUS_TABLE_KIND),
        mode=str(data.get("mode") or STATUS_TABLE_MODE_KEY_VALUE),
        key_column=str(data.get("keyColumn") or STATUS_KEY_COLUMN),
        value_column=str(data.get("valueColumn") or STATUS_VALUE_COLUMN),
        rows=tuple(rows),
        metadata=raw_metadata if isinstance(raw_metadata, dict) else {},
    ).validated()


def _parse_deferred_interval_turns(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("deferredIntervalTurns must be a positive integer")
    return value


def serialize_status_document(document: StatusTableDocument) -> str:
    return json.dumps(document.validated().to_json_dict(), ensure_ascii=False, separators=(",", ":"))


def validate_status_kind(value: str | StatusKind) -> StatusKind:
    kind = str(value or STATUS_KIND_NORMAL)
    try:
        return StatusKind(kind)
    except ValueError as exc:
        raise ValueError(f"Unsupported status kind: {kind}") from exc


def validate_status_update_policy(
    frequency: str | StatusUpdateFrequency,
    *,
    update_rule: str = "",
    deferred_interval_turns: int | None = None,
) -> StatusUpdateFrequency:
    normalized = str(frequency or STATUS_UPDATE_FREQUENCY_REALTIME).strip().lower()
    try:
        parsed_frequency = StatusUpdateFrequency(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported status update frequency: {normalized}"
        ) from exc
    rule = str(update_rule or "").strip()
    if normalized == STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN and not rule:
        raise ValueError("event_driven status fields require updateRule")
    if normalized != STATUS_UPDATE_FREQUENCY_EVENT_DRIVEN and rule:
        raise ValueError("updateRule is only supported for event_driven status fields")
    if deferred_interval_turns is not None:
        if (
            isinstance(deferred_interval_turns, bool)
            or not isinstance(deferred_interval_turns, int)
            or deferred_interval_turns <= 0
        ):
            raise ValueError("deferredIntervalTurns must be a positive integer")
        if normalized != STATUS_UPDATE_FREQUENCY_DEFERRED:
            raise ValueError(
                "deferredIntervalTurns is only supported for deferred status fields"
            )
    return parsed_frequency


def validate_story_status_mount_origin(
    value: str | StoryStatusMountOrigin,
) -> StoryStatusMountOrigin:
    origin = str(value or STORY_STATUS_MOUNT_ORIGIN_SYSTEM)
    try:
        return StoryStatusMountOrigin(origin)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported story status mount origin: {origin}"
        ) from exc


def validate_status_origin(value: str | StatusOrigin) -> StatusOrigin:
    origin = str(value)
    try:
        return StatusOrigin(origin)
    except ValueError as exc:
        raise ValueError(f"Unsupported status origin: {origin}") from exc


@dataclass(frozen=True)
class StatusTableTemplate:
    id: int
    workspace_id: str
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
class StoryStatusTable:
    id: int
    workspace_id: str
    story_id: int
    status_table_id: int
    story_character_mount_id: int | None
    table_name: str
    mount_origin: StoryStatusMountOrigin = STORY_STATUS_MOUNT_ORIGIN_SYSTEM
    status_kind: StatusKind = STATUS_KIND_NORMAL
    description: str = ""
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mount_origin",
            validate_story_status_mount_origin(self.mount_origin),
        )
        object.__setattr__(self, "status_kind", validate_status_kind(self.status_kind))


@dataclass(frozen=True)
class SessionStatusTable:
    id: int
    session_id: str
    workspace_id: str
    story_id: int
    source_table_id: int | None
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
    table: StatusTableTemplate | SessionStatusTable,
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
    or name.startswith("STORY_STATUS_")
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
        "validate_status_update_policy",
        "validate_story_status_mount_origin",
    }
]
