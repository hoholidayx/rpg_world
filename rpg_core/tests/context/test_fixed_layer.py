from __future__ import annotations

from types import SimpleNamespace

import pytest

from rpg_core.context.fixed_layer import (
    FIXED_LAYER_CHARACTER_SECTION_ID,
    FIXED_LAYER_CORE_SECTION_ID,
    FIXED_LAYER_LOREBOOK_SECTION_ID,
    FIXED_LAYER_SOURCE_RP_MODULE,
    FixedLayerAssembler,
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)
from rpg_core.context.fixed_layer.contributors import (
    CharacterFixedLayerContributor,
    CoreRPContractContributor,
    LorebookFixedLayerContributor,
    PLAYER_CHARACTER_SECTION_ID,
    PlayerCharacterFixedLayerContributor,
    StaticFixedLayerContributor,
    STORY_PROMPT_SECTION_ID,
    StoryPromptFixedLayerContributor,
    TEXT_OUTPUT_FORMAT_SECTION_ID,
    TextOutputFormatFixedLayerContributor,
)


class FakeLorebookManager:
    def __init__(self, entries: list[dict[str, object]]) -> None:
        self._entries = entries

    def list_enabled_entries(self) -> list[dict[str, object]]:
        return list(self._entries)


class FakeCharacterManager:
    def __init__(self, characters: list[dict[str, object]]) -> None:
        self._characters = characters

    def list_enabled_characters(self) -> list[dict[str, object]]:
        return list(self._characters)


class FakeStoryCatalog:
    def __init__(self, story_prompt: str | None) -> None:
        self._story_prompt = story_prompt

    def get_session_story(self, _session_id: str):  # noqa: ANN201
        if self._story_prompt is None:
            return None
        return SimpleNamespace(story_prompt=self._story_prompt)


class BrokenContributor(FixedLayerContributor):
    name = "broken"

    def get_fixed_contribution(self) -> FixedLayerContribution:
        raise RuntimeError("boom")


def test_fixed_layer_assembler_merges_core_knowledge_and_module_sections():
    lorebook_entries = [{
        "name": "北境",
        "description": "寒风终年不散。",
        "tags": ["region"],
        "content": "王国北侧的荒原地带。",
    }]
    characters = [{
        "name": "Alice",
        "personality": "curious",
        "content": "A young wizard.",
        "details": [{"name": "外貌", "content": "银白色长发。"}],
    }]
    module_section = FixedLayerSection(
        id="module_hint",
        title="模块提示",
        content="使用特定模块规则。",
        priority=50,
        source=FIXED_LAYER_SOURCE_RP_MODULE,
        source_kind=FIXED_LAYER_SOURCE_RP_MODULE,
        item_count=1,
    )

    fixed_layer = FixedLayerAssembler(
        world_name="测试世界",
        contributors=[
            CoreRPContractContributor("测试世界"),
            StoryPromptFixedLayerContributor("s1", catalog=FakeStoryCatalog("故事只发生在雾港。")),
            LorebookFixedLayerContributor(FakeLorebookManager(lorebook_entries)),
            CharacterFixedLayerContributor(FakeCharacterManager(characters)),
            StaticFixedLayerContributor([module_section]),
            TextOutputFormatFixedLayerContributor(),
        ],
    ).assemble()

    assert [section.id for section in fixed_layer.sections] == [
        FIXED_LAYER_CORE_SECTION_ID,
        STORY_PROMPT_SECTION_ID,
        FIXED_LAYER_LOREBOOK_SECTION_ID,
        FIXED_LAYER_CHARACTER_SECTION_ID,
        "module_hint",
        TEXT_OUTPUT_FORMAT_SECTION_ID,
    ]
    assert fixed_layer.sections[1].content == "故事只发生在雾港。"
    assert fixed_layer.sections[2].item_count == 1
    assert fixed_layer.sections[3].item_count == 1
    assert fixed_layer.lorebook_entries == lorebook_entries
    assert fixed_layer.characters == characters
    core_content = fixed_layer.sections[0].content
    assert "本轮回复前的权威运行时快照" in core_content
    assert "输出任何 RP 正文前调用对应状态工具" in core_content
    assert "工具调用轮不得夹带 RP 正文" in core_content
    assert "不得询问玩家是否需要标记、记录或更新状态" in core_content
    assert "状态表、当前场景和既有历史都是权威事实" not in core_content


def test_story_prompt_contributor_skips_blank_or_missing_story():
    blank = StoryPromptFixedLayerContributor("s1", catalog=FakeStoryCatalog("  ")).get_fixed_contribution()
    missing = StoryPromptFixedLayerContributor("s1", catalog=FakeStoryCatalog(None)).get_fixed_contribution()

    assert blank.sections == []
    assert missing.sections == []


def test_story_prompt_contributor_prefers_explicit_turn_snapshot() -> None:
    class UnexpectedCatalogRead:
        @staticmethod
        def get_session_story(_session_id: str):  # noqa: ANN205
            raise AssertionError("frozen turn prompt must not reread the Story")

    contribution = StoryPromptFixedLayerContributor(
        "s1",
        catalog=UnexpectedCatalogRead(),
        content="  本轮已经渲染的 Prompt。  ",
    ).get_fixed_contribution()

    assert contribution.sections[0].content == "本轮已经渲染的 Prompt。"


def test_story_prompt_contributor_requires_explicit_catalog_reader() -> None:
    with pytest.raises(TypeError):
        StoryPromptFixedLayerContributor("s1")  # type: ignore[call-arg]


def test_player_character_section_and_card_labels_are_session_local() -> None:
    player = SimpleNamespace(
        character_id=2,
        mount_id=20,
        story_id=1,
        name="Alice",
    )
    characters = [
        {"id": 1, "mount_id": 10, "name": "Bob"},
        {"id": 2, "mount_id": 20, "name": "Alice"},
    ]

    fixed_layer = FixedLayerAssembler(
        world_name="测试世界",
        contributors=[
            PlayerCharacterFixedLayerContributor(player),
            CharacterFixedLayerContributor(
                FakeCharacterManager(characters),
                player_character=player,
            ),
        ],
    ).assemble()

    assert [section.id for section in fixed_layer.sections] == [
        PLAYER_CHARACTER_SECTION_ID,
        FIXED_LAYER_CHARACTER_SECTION_ID,
    ]
    player_section, character_section = fixed_layer.sections
    assert "当前玩家扮演角色：Alice" in player_section.content
    assert "必须以本节的 session 绑定为准" in player_section.content
    assert "Bob [NPC｜非玩家角色]" in character_section.content
    assert "Alice [PLAYER_CHARACTER｜玩家当前扮演]" in character_section.content
    assert fixed_layer.characters[0]["control_role"] == "npc"
    assert fixed_layer.characters[1]["is_player_character"] is True


def test_fixed_layer_assembler_keeps_domain_structure_when_contributor_disabled():
    fixed_layer = FixedLayerAssembler(
        world_name="测试世界",
        contributors=[
            CoreRPContractContributor("测试世界"),
            LorebookFixedLayerContributor(FakeLorebookManager([{"name": "Lore"}]), enabled=False),
            CharacterFixedLayerContributor(FakeCharacterManager([{"name": "Alice"}]), enabled=False),
        ],
    ).assemble()

    assert [section.id for section in fixed_layer.sections] == [FIXED_LAYER_CORE_SECTION_ID]
    assert fixed_layer.lorebook_entries == []
    assert fixed_layer.characters == []


def test_fixed_layer_assembler_skips_failing_contributor_without_breaking_others():
    lorebook_entries = [{
        "name": "北境",
        "description": "",
        "tags": [],
        "content": "王国北侧的荒原地带。",
    }]

    fixed_layer = FixedLayerAssembler(
        world_name="测试世界",
        contributors=[
            CoreRPContractContributor("测试世界"),
            BrokenContributor(),
            LorebookFixedLayerContributor(FakeLorebookManager(lorebook_entries)),
        ],
    ).assemble()

    assert [section.id for section in fixed_layer.sections] == [
        FIXED_LAYER_CORE_SECTION_ID,
        FIXED_LAYER_LOREBOOK_SECTION_ID,
    ]
    assert fixed_layer.lorebook_entries == lorebook_entries
    assert fixed_layer.characters == []
