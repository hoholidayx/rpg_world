"""Mode-aware candidate selection owned by summary/story-memory business flows."""

from __future__ import annotations

from rpg_core.context.rpg_context import Message
from rpg_core.session.manager import SessionManager
from rpg_core.turns import TurnMode

_ALLOWED_MEMORY_MODES = frozenset({TurnMode.IC.value, TurnMode.GM.value})


def select_summary_turn_groups(
    session: SessionManager,
    *,
    keep_recent_turns: int,
) -> list[list[Message]]:
    """Mark OOC summary rows and return eligible IC/GM groups."""
    included, excluded = _partition_mode_groups(session.summary_unprocessed_turn_groups())
    if excluded:
        session.mark_summary_messages_processed(
            [message for group in excluded for message in group],
            batch_id=None,
        )
    unprocessed_keys = {
        _message_key(message)
        for group in included
        for message in group
    }
    all_conversation = [message for message in session.history if not message.is_system()]
    all_allowed_groups, _ = _partition_mode_groups(
        SessionManager.iter_turn_groups(all_conversation)
    )
    keep = max(0, int(keep_recent_turns))
    eligible_groups = all_allowed_groups if keep <= 0 else all_allowed_groups[:-keep]
    return [
        [message for message in group if _message_key(message) in unprocessed_keys]
        for group in eligible_groups
        if any(_message_key(message) in unprocessed_keys for message in group)
    ]


def select_story_memory_turn_groups(
    session: SessionManager,
) -> list[list[Message]]:
    """Mark OOC story-memory rows and return IC/GM extraction groups."""
    included, excluded = _partition_mode_groups(
        session.story_turn_groups_since_last_extraction()
    )
    if excluded:
        session.mark_story_messages_processed(
            [message for group in excluded for message in group]
        )
    return included


def _partition_mode_groups(
    groups: list[list[Message]],
) -> tuple[list[list[Message]], list[list[Message]]]:
    included: list[list[Message]] = []
    excluded: list[list[Message]] = []
    for group in groups:
        modes = {str(message.mode or TurnMode.IC.value).strip().lower() for message in group}
        # Normal writes use one mode for the whole turn. Treat any mixed turn
        # containing OOC as excluded so OOC content can never leak to an LLM.
        if TurnMode.OOC.value in modes:
            excluded.append(group)
        elif modes and modes.issubset(_ALLOWED_MEMORY_MODES):
            included.append(group)
        else:
            # Persisted mode is constrained by SQLite; this remains a strict
            # boundary for in-memory/test messages assembled outside storage.
            raise ValueError(f"unsupported message mode(s): {sorted(modes)}")
    return included, excluded


def _message_key(message: Message) -> tuple[str, int]:
    if message.uid > 0:
        return ("uid", message.uid)
    return ("object", id(message))
