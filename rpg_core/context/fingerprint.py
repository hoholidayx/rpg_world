"""Non-content request fingerprints for LLM cache diagnostics."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rpg_core.context.rpg_context import Message, Role


@dataclass(frozen=True)
class LLMMessageFingerprint:
    """Non-content identity for one provider-visible message."""

    index: int
    role: str
    payload_hash: str
    content_chars: int


@dataclass(frozen=True)
class LLMRequestFingerprint:
    """Stable hashes and size metadata for one provider-visible request."""

    context_hash: str
    system_hash: str
    tools_hash: str
    context_chars: int
    system_chars: int
    tools_chars: int
    message_count: int
    role_counts: tuple[tuple[str, int], ...]
    tool_names: tuple[str, ...]
    message_fingerprints: tuple[LLMMessageFingerprint, ...]


def build_request_fingerprint(
    messages: Sequence[Message | Mapping[str, object]],
    schemas: Sequence[Mapping[str, object]] | None,
) -> LLMRequestFingerprint:
    """Fingerprint final messages and schemas without exposing their bodies."""

    message_payloads = [_message_payload(message) for message in messages]
    system_payloads = [
        payload
        for payload in message_payloads
        if payload.get("role") == Role.SYSTEM.value
    ]
    schema_payloads = [dict(schema) for schema in schemas or ()]

    context_json = _canonical_json(message_payloads)
    system_json = _canonical_json(system_payloads)
    tools_json = _canonical_json(schema_payloads)
    role_counts = Counter(
        str(payload.get("role") or "unknown") for payload in message_payloads
    )
    ordered_role_counts = tuple(
        (role.value, role_counts.pop(role.value, 0)) for role in Role
    ) + tuple(sorted(role_counts.items()))

    tool_names = tuple(
        name
        for schema in schema_payloads
        if (name := _tool_name(schema))
    )
    message_fingerprints = tuple(
        LLMMessageFingerprint(
            index=index,
            role=str(payload.get("role") or "unknown"),
            payload_hash=_short_hash(_canonical_json(payload)),
            content_chars=_content_chars(payload),
        )
        for index, payload in enumerate(message_payloads)
    )
    return LLMRequestFingerprint(
        context_hash=_short_hash(context_json),
        system_hash=_short_hash(system_json),
        tools_hash=_short_hash(tools_json),
        context_chars=sum(_content_chars(payload) for payload in message_payloads),
        system_chars=sum(_content_chars(payload) for payload in system_payloads),
        tools_chars=len(tools_json),
        message_count=len(message_payloads),
        role_counts=ordered_role_counts,
        tool_names=tool_names,
        message_fingerprints=message_fingerprints,
    )


def request_fingerprint_log_values(
    fingerprint: LLMRequestFingerprint,
) -> tuple[object, ...]:
    """Return the shared, content-free values used by verbose request logs."""

    message_shape = [
        {
            "index": item.index,
            "role": item.role,
            "hash": item.payload_hash,
            "chars": item.content_chars,
        }
        for item in fingerprint.message_fingerprints
    ]
    return (
        fingerprint.context_hash,
        fingerprint.context_chars,
        fingerprint.system_hash,
        fingerprint.system_chars,
        fingerprint.tools_hash,
        fingerprint.tools_chars,
        fingerprint.message_count,
        dict(fingerprint.role_counts),
        list(fingerprint.tool_names),
        message_shape,
    )


def _message_payload(message: Message | Mapping[str, object]) -> dict[str, object]:
    if isinstance(message, Message):
        return message.to_provider_dict()
    return dict(message)


def _content_chars(payload: Mapping[str, object]) -> int:
    content = payload.get("content")
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    return len(_canonical_json(content))


def _tool_name(schema: Mapping[str, object]) -> str:
    function = schema.get("function")
    if not isinstance(function, Mapping):
        return ""
    return str(function.get("name") or "")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
