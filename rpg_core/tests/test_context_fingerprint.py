from __future__ import annotations

from rpg_core.context.fingerprint import build_request_fingerprint
from rpg_core.context.rpg_context import Message, Role


def _schema(description: str = "update state") -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "status_table_set_values",
            "description": description,
            "parameters": {"properties": {}, "type": "object"},
        },
    }


def test_request_fingerprint_is_deterministic_and_component_scoped() -> None:
    messages = [
        Message(Role.SYSTEM, "stable system"),
        Message(Role.USER, "current action"),
    ]
    baseline = build_request_fingerprint(messages, [_schema()])
    equivalent = build_request_fingerprint(
        [
            {"content": "stable system", "role": "system"},
            {"content": "current action", "role": "user"},
        ],
        [_schema()],
    )

    assert equivalent == baseline
    assert len(baseline.context_hash) == 16
    assert baseline.context_chars == len("stable systemcurrent action")
    assert baseline.system_chars == len("stable system")
    assert baseline.message_count == 2
    assert dict(baseline.role_counts) == {
        "system": 1,
        "user": 1,
        "assistant": 0,
        "tool": 0,
    }
    assert baseline.tool_names == ("status_table_set_values",)

    user_changed = build_request_fingerprint(
        [Message(Role.SYSTEM, "stable system"), Message(Role.USER, "new action")],
        [_schema()],
    )
    assert user_changed.context_hash != baseline.context_hash
    assert user_changed.system_hash == baseline.system_hash
    assert user_changed.tools_hash == baseline.tools_hash

    system_changed = build_request_fingerprint(
        [Message(Role.SYSTEM, "changed system"), Message(Role.USER, "current action")],
        [_schema()],
    )
    assert system_changed.context_hash != baseline.context_hash
    assert system_changed.system_hash != baseline.system_hash
    assert system_changed.tools_hash == baseline.tools_hash

    tools_changed = build_request_fingerprint(messages, [_schema("changed schema")])
    assert tools_changed.context_hash == baseline.context_hash
    assert tools_changed.system_hash == baseline.system_hash
    assert tools_changed.tools_hash != baseline.tools_hash
