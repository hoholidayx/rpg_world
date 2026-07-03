"""RPGContext — 结构化分层上下文容器。

Builder 只负责收集结构化层数据；Jinja 渲染只发生在发送给 LLM 或展示前的
显式边界，避免在构建阶段提前把层内容压平成字符串。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from commons.types import JsonObject
from rpg_core.context.config import ExtensionModuleDef
from rpg_core.context.fixed_layer import FixedLayerSection


class Role(StrEnum):
    """Message role constants — eliminates hardcoded role strings."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LayerType:
    """Layer type constants — each maps to one entry in the RPG context."""

    FIXED = "fixed_layer"
    PERSISTENT_MEMORY = "persistent_memory"
    SUMMARY = "summary"
    HOT_HISTORY = "hot_history"
    STORY_MEMORY = "story_memory"
    RECALLED_MEMORY = "recalled_memory"
    STATUS_TABLES = "status_tables"
    RP_MODULES = "rp_modules"
    USER_MESSAGE = "user_message"


class MsgKey:
    """Message dict field-name constants, avoids magic strings."""

    ROLE = "role"
    CONTENT = "content"
    UID = "uid"
    TURN_ID = "turn_id"
    SEQ_IN_TURN = "seq_in_turn"


class Message:
    """Typed wrapper for OpenAI-compatible message dicts."""

    __slots__ = ("_role", "_content", "_uid", "_turn_id", "_seq_in_turn", "_tool_call_id", "_tool_calls")

    def __init__(
        self,
        role: Role | str,
        content: str,
        uid: int = 0,
        turn_id: int = 0,
        seq_in_turn: int = 0,
        tool_call_id: str = "",
        tool_calls: list[JsonObject] | None = None,
    ) -> None:
        self._role = Role(role) if isinstance(role, str) else role
        self._content = content
        self._uid = int(uid)
        self._turn_id = int(turn_id)
        self._seq_in_turn = int(seq_in_turn)
        self._tool_call_id = tool_call_id
        self._tool_calls = tool_calls or None

    @property
    def role(self) -> Role:
        return self._role

    @property
    def content(self) -> str:
        return self._content

    @property
    def uid(self) -> int:
        return self._uid

    @property
    def turn_id(self) -> int:
        return self._turn_id

    @property
    def seq_in_turn(self) -> int:
        return self._seq_in_turn

    @property
    def tool_call_id(self) -> str:
        return self._tool_call_id

    @tool_call_id.setter
    def tool_call_id(self, value: str) -> None:
        self._tool_call_id = value

    @property
    def tool_calls(self) -> list[JsonObject] | None:
        return self._tool_calls

    @tool_calls.setter
    def tool_calls(self, value: list[JsonObject] | None) -> None:
        self._tool_calls = value

    def is_user(self) -> bool:
        return self._role is Role.USER

    def is_system(self) -> bool:
        return self._role is Role.SYSTEM

    def is_assistant(self) -> bool:
        return self._role is Role.ASSISTANT

    def is_tool(self) -> bool:
        return self._role is Role.TOOL

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {MsgKey.ROLE: self._role.value, MsgKey.CONTENT: self._content}
        if self._uid:
            d[MsgKey.UID] = self._uid
        if self._turn_id:
            d[MsgKey.TURN_ID] = self._turn_id
        if self._seq_in_turn:
            d[MsgKey.SEQ_IN_TURN] = self._seq_in_turn
        if self._tool_call_id:
            d["tool_call_id"] = self._tool_call_id
        if self._tool_calls:
            d["tool_calls"] = self._tool_calls
        return d

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Message:
        raw_tool_calls = d.get("tool_calls")
        return cls(
            role=str(d[MsgKey.ROLE]),
            content=str(d.get(MsgKey.CONTENT) or ""),
            uid=int(d.get(MsgKey.UID, 0) or 0),
            turn_id=int(d.get(MsgKey.TURN_ID, 0) or 0),
            seq_in_turn=int(d.get(MsgKey.SEQ_IN_TURN, 0) or 0),
            tool_call_id=str(d.get("tool_call_id", "") or ""),
            tool_calls=cast(list[JsonObject], raw_tool_calls) if isinstance(raw_tool_calls, list) else None,
        )

    def __repr__(self) -> str:
        return f"Message(role={self._role.value!r}, content={self._content[:40]!r}...)"


@dataclass(frozen=True)
class FixedLayerData:
    world_name: str = ""
    sections: list[FixedLayerSection] = field(default_factory=list)
    lorebook_entries: list[JsonObject] = field(default_factory=list)
    characters: list[JsonObject] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.sections or self.lorebook_entries or self.characters)


@dataclass(frozen=True)
class PersistentMemoryLayer:
    sections: list[dict[str, str]] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.sections)


@dataclass(frozen=True)
class SummaryLayer:
    text: str | None = None

    @property
    def active(self) -> bool:
        return bool(self.text and self.text.strip())


@dataclass(frozen=True)
class HotHistoryLayer:
    messages: list[Message] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.messages)


@dataclass(frozen=True)
class StoryMemoryLayer:
    details: list[JsonObject] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.details)


@dataclass(frozen=True)
class RecalledMemoryLayer:
    items: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.items)


@dataclass(frozen=True)
class StatusTablesLayer:
    tables: list[JsonObject] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.tables)


@dataclass(frozen=True)
class RPModuleRuntimeSection:
    id: str
    title: str
    content: str
    priority: int = 100
    source: str = "rp_module"


@dataclass(frozen=True)
class RPModulesLayer:
    sections: list[RPModuleRuntimeSection] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return any(section.content.strip() for section in self.sections)


@dataclass(frozen=True)
class UserExtensionBlock:
    name: str
    template: str
    data: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_def(cls, definition: ExtensionModuleDef, data: dict[str, str]) -> "UserExtensionBlock":
        return cls(name=definition.name, template=definition.template, data=dict(data))


@dataclass(frozen=True)
class UserMessageLayer:
    before: list[UserExtensionBlock] = field(default_factory=list)
    user_input: str = ""
    after: list[UserExtensionBlock] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.before or self.user_input or self.after)


StructuredLayer = (
    FixedLayerData
    | PersistentMemoryLayer
    | SummaryLayer
    | HotHistoryLayer
    | StoryMemoryLayer
    | RecalledMemoryLayer
    | StatusTablesLayer
    | RPModulesLayer
    | UserMessageLayer
)


@dataclass
class RPGContext:
    """完整 RPG 上下文容器，保存结构化层数据。"""

    fixed_layer: FixedLayerData = field(default_factory=FixedLayerData)
    persistent_memory: PersistentMemoryLayer = field(default_factory=PersistentMemoryLayer)
    summary: SummaryLayer = field(default_factory=SummaryLayer)
    hot_history: HotHistoryLayer = field(default_factory=HotHistoryLayer)
    story_memory: StoryMemoryLayer = field(default_factory=StoryMemoryLayer)
    recalled_memory: RecalledMemoryLayer = field(default_factory=RecalledMemoryLayer)
    status_tables: StatusTablesLayer = field(default_factory=StatusTablesLayer)
    rp_modules: RPModulesLayer = field(default_factory=RPModulesLayer)
    user_message: UserMessageLayer = field(default_factory=UserMessageLayer)

    def to_message_objects(self) -> list[Message]:
        """Render active structured layers into Message objects."""
        from rpg_core.context.renderer import ContextRenderer

        return ContextRenderer(self).to_message_objects()

    def get_layer(self, type_: str) -> StructuredLayer | None:
        """Get structured layer data by type string."""
        mapping: dict[str, StructuredLayer] = {
            LayerType.FIXED: self.fixed_layer,
            LayerType.PERSISTENT_MEMORY: self.persistent_memory,
            LayerType.SUMMARY: self.summary,
            LayerType.HOT_HISTORY: self.hot_history,
            LayerType.STORY_MEMORY: self.story_memory,
            LayerType.RECALLED_MEMORY: self.recalled_memory,
            LayerType.STATUS_TABLES: self.status_tables,
            LayerType.RP_MODULES: self.rp_modules,
            LayerType.USER_MESSAGE: self.user_message,
        }
        return mapping.get(type_)

    def render_layer(self, type_: str) -> str | None:
        """Render one structured layer explicitly."""
        from rpg_core.context.renderer import ContextRenderer

        return ContextRenderer(self).render_layer(type_)
