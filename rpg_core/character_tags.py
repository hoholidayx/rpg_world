"""Character-detail tag policy and mode-stable card projection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from commons.types import JsonObject

CHARACTER_DETAIL_TAG_APPEARANCE = "kind:appearance"
CHARACTER_DETAIL_TAG_BACKGROUND = "kind:background"
CHARACTER_DETAIL_TAG_RELATIONSHIP = "kind:relationship"
CHARACTER_DETAIL_TAG_ABILITY = "kind:ability"
CHARACTER_DETAIL_TAG_PERSONALITY = "kind:personality"
CHARACTER_DETAIL_TAG_SPEECH = "kind:speech"
CHARACTER_DETAIL_TAG_BEHAVIOR = "kind:behavior"
CHARACTER_DETAIL_TAG_PSYCHOLOGY = "kind:psychology"
CHARACTER_DETAIL_TAG_NPC_PORTRAYAL = "scope:npc_portrayal"

OBJECTIVE_CHARACTER_DETAIL_TAGS = frozenset({
    CHARACTER_DETAIL_TAG_APPEARANCE,
    CHARACTER_DETAIL_TAG_BACKGROUND,
    CHARACTER_DETAIL_TAG_RELATIONSHIP,
    CHARACTER_DETAIL_TAG_ABILITY,
})
PORTRAYAL_CHARACTER_DETAIL_TAGS = frozenset({
    CHARACTER_DETAIL_TAG_PERSONALITY,
    CHARACTER_DETAIL_TAG_SPEECH,
    CHARACTER_DETAIL_TAG_BEHAVIOR,
    CHARACTER_DETAIL_TAG_PSYCHOLOGY,
})
RESERVED_CHARACTER_DETAIL_TAGS = frozenset({
    *OBJECTIVE_CHARACTER_DETAIL_TAGS,
    *PORTRAYAL_CHARACTER_DETAIL_TAGS,
    CHARACTER_DETAIL_TAG_NPC_PORTRAYAL,
})


def normalize_character_detail_tags(tags: Iterable[object]) -> tuple[str, ...]:
    """Normalize tags and enforce the reserved portrayal-scope invariant."""

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = str(raw or "").strip()
        if not tag or tag in seen:
            continue
        if (
            (tag.startswith("kind:") or tag.startswith("scope:"))
            and tag not in RESERVED_CHARACTER_DETAIL_TAGS
        ):
            raise ValueError(f"unsupported reserved character detail tag: {tag}")
        normalized.append(tag)
        seen.add(tag)
    if PORTRAYAL_CHARACTER_DETAIL_TAGS.intersection(seen):
        if CHARACTER_DETAIL_TAG_NPC_PORTRAYAL not in seen:
            normalized.append(CHARACTER_DETAIL_TAG_NPC_PORTRAYAL)
    return tuple(normalized)


def is_npc_portrayal_detail(detail: Mapping[str, object]) -> bool:
    raw_tags = detail.get("tags")
    if not isinstance(raw_tags, (list, tuple)):
        return False
    return CHARACTER_DETAIL_TAG_NPC_PORTRAYAL in {
        str(tag).strip() for tag in raw_tags
    }


def split_player_character_details(
    details: Iterable[Mapping[str, object]],
) -> tuple[list[JsonObject], list[JsonObject]]:
    """Return stable player facts and withheld NPC-portrayal details."""

    reference: list[JsonObject] = []
    portrayal: list[JsonObject] = []
    for detail in details:
        item = dict(detail)
        (portrayal if is_npc_portrayal_detail(item) else reference).append(item)
    return reference, portrayal


__all__ = [
    "CHARACTER_DETAIL_TAG_NPC_PORTRAYAL",
    "OBJECTIVE_CHARACTER_DETAIL_TAGS",
    "PORTRAYAL_CHARACTER_DETAIL_TAGS",
    "RESERVED_CHARACTER_DETAIL_TAGS",
    "is_npc_portrayal_detail",
    "normalize_character_detail_tags",
    "split_player_character_details",
]
