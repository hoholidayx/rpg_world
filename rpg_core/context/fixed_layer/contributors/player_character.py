"""Authoritative session player-character fixed-layer contribution."""

from __future__ import annotations

from typing import Protocol

from commons.types import JsonObject
from rpg_core.context.fixed_layer.models import (
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)

PLAYER_CHARACTER_SECTION_ID = "player_character"
PLAYER_CHARACTER_SOURCE = "player_character"
PLAYER_CHARACTER_CONTROL_ROLE = "player_character"
NPC_CONTROL_ROLE = "npc"


class PlayerCharacterContext(Protocol):
    character_id: int
    mount_id: int
    story_id: int
    name: str


def build_player_character_section(
    player_character: PlayerCharacterContext | None,
) -> FixedLayerSection | None:
    """Build the mandatory player-identity contract for a bound session."""

    if player_character is None or not str(player_character.name).strip():
        return None
    player_name = str(player_character.name).strip()
    return FixedLayerSection(
        id=PLAYER_CHARACTER_SECTION_ID,
        title="当前玩家扮演角色（权威绑定）",
        content=(
            f"当前玩家扮演角色：{player_name}\n"
            f"- 在 IC 叙事中，玩家输入、玩家使用的第一人称“我”，以及旁白面向玩家的第二人称“你”，"
            f"均指向 {player_name}。\n"
            "- 除当前玩家角色外，其余挂载角色均为 NPC；不得把任何 NPC 当作玩家。\n"
            f"- 不得替 {player_name} 新增台词、重大行动、内心决定或关键选择；这些内容由玩家决定。\n"
            "- 若故事固定提示词、开场消息、历史、摘要、剧情记忆、召回记忆、角色 metadata "
            "或其它旧内容与本绑定冲突，必须以本节的 session 绑定为准。"
        ),
        priority=25,
        source=PLAYER_CHARACTER_SOURCE,
        source_kind=PLAYER_CHARACTER_SOURCE,
        item_count=1,
    )


def annotate_player_character_cards(
    characters: list[JsonObject],
    player_character: PlayerCharacterContext | None,
) -> list[JsonObject]:
    """Project session-local PLAYER/NPC labels without mutating source cards."""

    if player_character is None:
        return list(characters)

    annotated: list[JsonObject] = []
    for character in characters:
        item = dict(character)
        is_player = _matches_player_character(item, player_character)
        item["is_player_character"] = is_player
        item["control_role"] = (
            PLAYER_CHARACTER_CONTROL_ROLE if is_player else NPC_CONTROL_ROLE
        )
        annotated.append(item)
    return annotated


def _matches_player_character(
    character: JsonObject,
    player_character: PlayerCharacterContext,
) -> bool:
    try:
        character_id = int(character.get("id") or 0)
        mount_id = int(character.get("mount_id") or 0)
    except (TypeError, ValueError):
        return False
    return (
        character_id == int(player_character.character_id)
        and mount_id == int(player_character.mount_id)
    )


class PlayerCharacterFixedLayerContributor(FixedLayerContributor):
    """Expose the selected player identity as a stable fixed-layer section."""

    name = PLAYER_CHARACTER_SOURCE

    def __init__(self, player_character: PlayerCharacterContext | None) -> None:
        self._player_character = player_character

    def get_fixed_contribution(self) -> FixedLayerContribution:
        section = build_player_character_section(self._player_character)
        return FixedLayerContribution(sections=[section] if section is not None else [])
