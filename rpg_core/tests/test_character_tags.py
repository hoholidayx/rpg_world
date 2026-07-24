from __future__ import annotations

import pytest

from rpg_core.character_tags import (
    CHARACTER_DETAIL_TAG_NPC_PORTRAYAL,
    normalize_character_detail_tags,
    split_player_character_details,
)


def test_portrayal_kind_automatically_receives_npc_scope() -> None:
    assert normalize_character_detail_tags(
        ["kind:personality", "custom", "kind:personality"]
    ) == (
        "kind:personality",
        "custom",
        CHARACTER_DETAIL_TAG_NPC_PORTRAYAL,
    )


def test_unknown_reserved_character_tag_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported reserved"):
        normalize_character_detail_tags(["kind:custom"])


def test_player_character_details_split_reference_from_portrayal() -> None:
    appearance = {
        "name": "外貌",
        "content": "银白短发",
        "tags": ["kind:appearance"],
    }
    personality = {
        "name": "性格",
        "content": "谨慎",
        "tags": ["kind:personality", "scope:npc_portrayal"],
    }

    reference, portrayal = split_player_character_details(
        [appearance, personality]
    )

    assert reference == [appearance]
    assert portrayal == [personality]
