from __future__ import annotations

from types import SimpleNamespace

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


def test_story_prompt_contributor_skips_blank_or_missing_story():
    blank = StoryPromptFixedLayerContributor("s1", catalog=FakeStoryCatalog("  ")).get_fixed_contribution()
    missing = StoryPromptFixedLayerContributor("s1", catalog=FakeStoryCatalog(None)).get_fixed_contribution()

    assert blank.sections == []
    assert missing.sections == []


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
