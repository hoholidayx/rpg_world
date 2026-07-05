"""Pure data models exposed by the RPG World data module."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Mapping

__all__ = [
    "Character",
    "CharacterDetail",
    "LorebookEntry",
    "Session",
    "SessionCharacter",
    "SessionCharacterDetail",
    "SessionLorebookEntry",
    "SessionMessage",
    "SessionPlayerCharacterSnapshot",
    "SessionProfile",
    "SessionStoryMemory",
    "SessionStatusTable",
    "Story",
    "StoryCharacter",
    "StoryLorebookEntry",
    "StoryLorebookEntryDetail",
    "StoryStatusTable",
    "StatusRowRef",
    "StatusTableData",
    "StatusTableDocument",
    "StatusTableRow",
    "StatusTableTemplate",
    "STATUS_KIND_NORMAL",
    "STATUS_KIND_SCENE",
    "STATUS_ORIGIN_SESSION_NATIVE",
    "STATUS_ORIGIN_TEMPLATE_COPY",
    "STATUS_KEY_COLUMN",
    "STATUS_TABLE_KIND",
    "STATUS_TABLE_MODE_KEY_VALUE",
    "STATUS_VALUE_COLUMN",
    "PLAYER_CHARACTER_STATUS_BOUND",
    "PLAYER_CHARACTER_STATUS_INVALID",
    "Workspace",
    "parse_status_document",
    "serialize_status_document",
    "validate_status_kind",
]

STATUS_TABLE_KIND = "status_table"
STATUS_TABLE_MODE_KEY_VALUE = "key_value"
PLAYER_CHARACTER_STATUS_BOUND = "bound"
PLAYER_CHARACTER_STATUS_INVALID = "invalid"
STATUS_KIND_SCENE = "scene"
STATUS_KIND_NORMAL = "normal"
STATUS_ORIGIN_TEMPLATE_COPY = "template_copy"
STATUS_ORIGIN_SESSION_NATIVE = "session_native"
STATUS_KEY_COLUMN = "属性"
STATUS_VALUE_COLUMN = "值"


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    root_path: str
    description: str = ""
    enabled: bool = True
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Story:
    id: int
    workspace_id: str
    title: str
    summary: str = ""
    # Story-level fixed system prompt; planned to be integrated into fix layer later.
    story_prompt: str = ""
    first_message: str = ""
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Session:
    id: str
    workspace_id: str
    story_id: int
    state_json: str = "{}"
    story_memory_last_turn_id: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    title: str = ""
    description: str = ""
    player_character_id: int | None = None
    player_character_snapshot_json: str = "{}"
    profile_metadata_json: str = "{}"
    profile_created_at: str = ""
    profile_updated_at: str = ""


@dataclass(frozen=True)
class SessionProfile:
    session_id: str
    title: str = ""
    description: str = ""
    player_character_id: int | None = None
    player_character_snapshot_json: str = "{}"
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionPlayerCharacterSnapshot:
    character_id: int
    mount_id: int
    story_id: int
    name: str
    avatar_url: str = ""
    role_label: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionMessage:
    id: int
    session_id: str
    role: str
    content: str = ""
    turn_id: int = 0
    seq_in_turn: int = 0
    tool_call_id: str = ""
    tool_calls_json: str = ""
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_message_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "role": self.role,
            "content": self.content,
        }
        if self.id:
            data["uid"] = self.id
        if self.turn_id:
            data["turn_id"] = self.turn_id
        if self.seq_in_turn:
            data["seq_in_turn"] = self.seq_in_turn
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.tool_calls_json:
            import json

            data["tool_calls"] = json.loads(self.tool_calls_json)
        return data


@dataclass(frozen=True)
class SessionStoryMemory:
    id: int
    session_id: str
    turn_id: int
    text: str = ""
    dream_processed: bool = False
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_context_dict(self) -> dict[str, object]:
        import json

        try:
            metadata = json.loads(self.metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return {
            "id": self.id,
            "turn_id": self.turn_id,
            "text": self.text,
            "dream_processed": self.dream_processed,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }


@dataclass(frozen=True)
class Character:
    id: int
    workspace_id: str
    name: str
    personality: str = ""
    content: str = ""
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class CharacterDetail:
    id: int
    character_id: int
    name: str
    content: str = ""
    tags_json: str = "[]"
    sort_order: int = 0
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class LorebookEntry:
    id: int
    workspace_id: str
    name: str
    content: str = ""
    description: str = ""
    tags_json: str = "[]"
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionLorebookEntry:
    id: int
    mount_id: int
    workspace_id: str
    story_id: int
    name: str
    content: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class SessionCharacterDetail:
    id: int
    character_id: int
    name: str
    content: str = ""
    tags: tuple[str, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class SessionCharacter:
    id: int
    mount_id: int
    workspace_id: str
    story_id: int
    name: str
    personality: str = ""
    content: str = ""
    details: tuple[SessionCharacterDetail, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class StoryCharacter:
    id: int
    workspace_id: str
    story_id: int
    character_id: int
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryCharacterDetail:
    mount: StoryCharacter
    character: Character


@dataclass(frozen=True)
class StoryLorebookEntry:
    id: int
    workspace_id: str
    story_id: int
    lorebook_entry_id: int
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class StoryLorebookEntryDetail:
    mount: StoryLorebookEntry
    entry: LorebookEntry


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
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "value": self.value,
            "runtimeKeyLocked": self.runtime_key_locked,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StatusTableDocument:
    schema_version: int = 1
    kind: str = STATUS_TABLE_KIND
    mode: str = STATUS_TABLE_MODE_KEY_VALUE
    key_column: str = STATUS_KEY_COLUMN
    value_column: str = STATUS_VALUE_COLUMN
    rows: tuple[StatusTableRow, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_rows(
        cls,
        *,
        key_column: str = STATUS_KEY_COLUMN,
        value_column: str = STATUS_VALUE_COLUMN,
        rows: tuple[StatusTableRow, ...] | list[StatusTableRow] | None = None,
        metadata: Mapping[str, object] | None = None,
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
        metadata: Mapping[str, object] | None = None,
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
        locked_by_key = {row.key: row.runtime_key_locked for row in self.rows}
        metadata_by_key = {row.key: dict(row.metadata) for row in self.rows}
        rows = tuple(
            StatusTableRow(
                key=row[0] if row else "",
                value=row[1] if len(row) > 1 else "",
                runtime_key_locked=locked_by_key.get(row[0] if row else "", False),
                metadata=metadata_by_key.get(row[0] if row else "", {}),
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
                updated.append(StatusTableRow(row.key, str(value), row.runtime_key_locked, dict(row.metadata)))
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
        return self

    def to_json_dict(self) -> dict[str, object]:
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


def serialize_status_document(document: StatusTableDocument) -> str:
    return json.dumps(document.validated().to_json_dict(), ensure_ascii=False, separators=(",", ":"))


def validate_status_kind(value: str) -> str:
    kind = str(value or STATUS_KIND_NORMAL)
    if kind not in {STATUS_KIND_SCENE, STATUS_KIND_NORMAL}:
        raise ValueError(f"Unsupported status kind: {kind}")
    return kind


@dataclass(frozen=True)
class StatusTableTemplate:
    id: int
    workspace_id: str
    name: str
    status_kind: str = STATUS_KIND_NORMAL
    description: str = ""
    document: StatusTableDocument = field(default_factory=StatusTableDocument)
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

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
    table_name: str
    status_kind: str = STATUS_KIND_NORMAL
    description: str = ""
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SessionStatusTable:
    id: int
    session_id: str
    workspace_id: str
    story_id: int
    source_table_id: int | None
    origin: str
    name: str
    status_kind: str = STATUS_KIND_NORMAL
    description: str = ""
    document: StatusTableDocument = field(default_factory=StatusTableDocument)
    sort_order: int = 0
    metadata_json: str = "{}"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

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


def _status_table_as_dict(table: object) -> dict[str, object]:
    data = asdict(table)
    data["document"] = table.document.to_json_dict()  # type: ignore[attr-defined]
    data["headers"] = list(table.headers)  # type: ignore[attr-defined]
    data["rows"] = [list(row) for row in table.rows]  # type: ignore[attr-defined]
    return data
