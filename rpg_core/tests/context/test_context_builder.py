from __future__ import annotations

from types import SimpleNamespace

import pytest

import rpg_core.context.renderer as renderer_module
from rpg_core.context.builder import RPGContextBuilder
from rpg_core.context.config import ExtensionModuleDef, RPGContextConfig
from rpg_core.context.fixed_layer import FixedLayerSection
from rpg_core.context.models import (
    FixedLayerData,
    HotHistoryLayer,
    LayerType,
    Message,
    PersistentMemoryFact,
    PersistentMemoryLayer,
    RecalledMemoryLayer,
    RPGContext,
    RPModuleRuntimeSection,
    RPModulesLayer,
    Role,
    StatusTablesLayer,
    StoryMemoryLayer,
    SummaryLayer,
    UserMessageLayer,
)


class FakePersistentStore:
    def __init__(self, memories):
        self.memories = memories

    async def load_snapshot(self):
        return tuple(self.memories)


class FakeStoryStore:
    def __init__(self, details):
        self.details = details

    def get_all(self):
        return list(self.details)


class FakeSummaryStore:
    def __init__(self, overall):
        self.overall = overall

    def load_overall(self):
        return self.overall


class FakeRecalledStore:
    def __init__(self, items):
        self.items = items

    def get_items(self):
        return list(self.items)


class FakeStatusTracker:
    table_key = ("全局状态", "当前场景")


def _fake_render(template_name: str, **context: object) -> str:
    if template_name == "layers/fixed_layer.jinja":
        section_ids = ",".join(section.id for section in context["fixed_sections"])
        return f"fixed|{section_ids}"
    if template_name == "modules/persistent_memory.jinja":
        return "pm|" + ",".join(item.text for item in context["persistent_memory"])
    if template_name == "modules/overall_summary.jinja":
        return f"summary|{context['text']}"
    if template_name == "modules/story_memory.jinja":
        return "story|" + ",".join(item.get("text", "") for item in context["story_details"])
    if template_name == "modules/recalled_memory.jinja":
        return "recalled|" + ",".join(context["recalled_items"])
    if template_name == "modules/status_tables.jinja":
        return "tables|" + ",".join(table["name"] for table in context["status_tables"])
    if template_name == "modules/user_reply_prefix.jinja":
        return "prefix"
    if template_name == "modules/user_reply_suffix.jinja":
        return "suffix"
    if template_name in {"modules/fixed_layer_sections.jinja", "modules/rp_modules.jinja"}:
        return "\n".join(f"[{section.id}]\n{section.content}\n[/{section.id}]" for section in context["sections"])
    if template_name == "layers/user_message.jinja":
        parts = []
        if context["user_before"]:
            parts.append("[user_prefix]" + "\n\n".join(context["user_before"]) + "[/user_prefix]")
        if context["user_input"]:
            parts.append(context["user_input"])
        if context["user_after"]:
            parts.append("[user_suffix]" + "\n\n".join(context["user_after"]) + "[/user_suffix]")
        return "\n\n".join(parts)
    return template_name


@pytest.fixture(autouse=True)
def _patch_renderer(monkeypatch):
    monkeypatch.setattr(renderer_module, "render_jinja_template", _fake_render)


async def test_build_context_layers_and_user_extensions():
    config = RPGContextConfig(
        hot_history_rounds=1,
        user_extension=[
            ExtensionModuleDef(name="prefix", template="modules/user_reply_prefix.jinja", position="before"),
            ExtensionModuleDef(name="suffix", template="modules/user_reply_suffix.jinja", position="after"),
        ],
    )
    builder = RPGContextBuilder(config=config, world_name="Test World")
    builder.set_summary_store(FakeSummaryStore(("overall summary", 1)))
    builder.set_persistent_memory_store(FakePersistentStore([
        SimpleNamespace(memory_id="m1", revision_number=1, text="p1", memory_kind="event", epistemic_status="confirmed", salience=0.8),
        SimpleNamespace(memory_id="m2", revision_number=2, text="p2", memory_kind="clue", epistemic_status="reported", salience=0.7),
    ]))
    builder.set_story_memory_store(FakeStoryStore([{"text": "story 1"}]))
    builder.set_recalled_memory_store(FakeRecalledStore(["recall 1"]))
    builder.set_batch_summary_store(FakeSummaryStore(("overall summary", 1)))
    persistent_memory_snapshot = await builder.load_persistent_memory_snapshot()

    messages = [
        Message(Role.SYSTEM, "system"),
        Message(Role.USER, "u1"),
        Message(Role.ASSISTANT, "a1"),
        Message(Role.USER, "u2"),
        Message(Role.ASSISTANT, "a2"),
        Message(Role.USER, "current"),
    ]

    ctx = builder.build(
        fixed_layer=FixedLayerData(
            world_name="Test World",
            sections=[FixedLayerSection(id="core", title="核心", content="prompt", priority=0)],
            lorebook_entries=[{"name": "Lore"}],
            characters=[{"name": "Alice"}],
        ),
        history_messages=messages[:-1],
        current_user_message=messages[-1],
        summarized_message_count=1,
        status_mgr=SimpleNamespace(
            list_context_tables=lambda: [{
                "name": "世界状态",
                "headers": ["属性", "值"],
                "rows": [["k", "v"]],
            }],
        ),
        scene_tracker=FakeStatusTracker(),
        persistent_memory_snapshot=persistent_memory_snapshot,
    )

    assert isinstance(ctx, RPGContext)
    assert isinstance(ctx.get_layer(LayerType.FIXED), FixedLayerData)
    assert ctx.fixed_layer.sections[0].id == "core"
    assert [item.text for item in ctx.persistent_memory.memories] == ["p1", "p2"]
    assert ctx.summary.text == "overall summary"
    assert [m.content for m in ctx.hot_history.messages] == ["u2", "a2"]
    assert ctx.story_memory.details == [{"text": "story 1"}]
    assert ctx.recalled_memory.items == ["recall 1"]
    assert [table["name"] for table in ctx.status_tables.tables] == ["世界状态"]
    assert ctx.user_message.before[0].template == "modules/user_reply_prefix.jinja"
    assert ctx.user_message.after[0].template == "modules/user_reply_suffix.jinja"
    assert ctx.render_layer(LayerType.FIXED) == "fixed|core"
    assert ctx.render_layer(LayerType.PERSISTENT_MEMORY) == "pm|p1,p2"
    assert ctx.render_layer(LayerType.STATUS_TABLES) == "tables|世界状态"

    rendered = ctx.to_message_objects()
    assert rendered[-1].role is Role.USER
    assert "prefix" in rendered[-1].content
    assert "current" in rendered[-1].content
    assert "suffix" in rendered[-1].content


def test_build_keeps_last_assistant_when_current_user_is_absent():
    builder = RPGContextBuilder(
        config=RPGContextConfig(hot_history_rounds=5),
        world_name="Test World",
    )
    history = [
        Message(Role.USER, "u1", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "a1", turn_id=1, seq_in_turn=2),
    ]

    ctx = builder.build(history_messages=history)

    assert [message.content for message in ctx.hot_history.messages] == ["u1", "a1"]


def test_summary_layer_depends_on_filtered_message_count_only():
    builder = RPGContextBuilder(
        config=RPGContextConfig(hot_history_rounds=50),
        world_name="Test World",
    )
    builder.set_batch_summary_store(FakeSummaryStore(("overall summary", 999)))

    inactive = builder.build(
        history_messages=[Message(Role.ASSISTANT, "latest")],
        summarized_message_count=0,
    )
    active = builder.build(
        history_messages=[Message(Role.ASSISTANT, "latest")],
        summarized_message_count=1,
    )

    assert inactive.summary.text is None
    assert active.summary.text == "overall summary"

def test_context_to_message_objects_renders_required_layers():
    ctx = RPGContext(
        fixed_layer=FixedLayerData(sections=[FixedLayerSection(id="core", title="核心", content="fixed")]),
        user_message=UserMessageLayer(user_input="hi"),
    )
    rendered = ctx.to_message_objects()

    assert [m.role for m in rendered] == [Role.SYSTEM, Role.USER]
    assert rendered[0].content == "fixed|core"
    assert rendered[1].content == "hi"


def test_context_includes_dynamic_rp_modules_before_user():
    ctx = RPGContext(
        fixed_layer=FixedLayerData(sections=[FixedLayerSection(id="core", title="核心", content="fixed")]),
        status_tables=StatusTablesLayer(tables=[{"name": "状态", "headers": ["k"], "rows": [["v"]]}]),
        rp_modules=RPModulesLayer(sections=[
            RPModuleRuntimeSection(id="combat", title="战斗", content="combat turn"),
        ]),
        user_message=UserMessageLayer(user_input="hi"),
    )

    rendered = ctx.to_message_objects()

    assert [m.role for m in rendered] == [
        Role.SYSTEM,
        Role.SYSTEM,
        Role.SYSTEM,
        Role.USER,
    ]
    assert [m.content for m in rendered[:-1]] == [
        "fixed|core",
        "tables|状态",
        "[combat]\ncombat turn\n[/combat]",
    ]
    assert rendered[-1].content == "hi"


def test_context_dynamic_system_layers_follow_cache_optimized_order():
    ctx = RPGContext(
        fixed_layer=FixedLayerData(
            sections=[FixedLayerSection(id="core", title="核心", content="fixed")]
        ),
        story_memory=StoryMemoryLayer(details=[{"text": "story detail"}]),
        status_tables=StatusTablesLayer(
            tables=[{"name": "状态", "headers": ["k"], "rows": [["v"]]}]
        ),
        recalled_memory=RecalledMemoryLayer(items=["recalled detail"]),
        rp_modules=RPModulesLayer(
            sections=[
                RPModuleRuntimeSection(
                    id="combat",
                    title="战斗",
                    content="combat turn",
                )
            ]
        ),
        user_message=UserMessageLayer(user_input="hi"),
    )

    rendered = ctx.to_message_objects()
    assert [message.content for message in rendered] == [
        "fixed|core",
        "story|story detail",
        "tables|状态",
        "recalled|recalled detail",
        "[combat]\ncombat turn\n[/combat]",
        "hi",
    ]


def test_context_preserves_canonical_layers_and_history_message_order():
    ctx = RPGContext(
        fixed_layer=FixedLayerData(
            sections=[FixedLayerSection(id="core", title="核心", content="fixed")]
        ),
        persistent_memory=PersistentMemoryLayer(
            memories=[PersistentMemoryFact(
                memory_id="m1",
                revision_number=1,
                text="persistent",
                memory_kind="event",
                epistemic_status="confirmed",
                salience=0.9,
            )]
        ),
        summary=SummaryLayer(text="summary"),
        hot_history=HotHistoryLayer(messages=[
            Message(Role.USER, "u1"),
            Message(Role.ASSISTANT, "a1"),
            Message(Role.SYSTEM, "legacy system"),
        ]),
        story_memory=StoryMemoryLayer(details=[{"text": "story detail"}]),
        status_tables=StatusTablesLayer(
            tables=[{"name": "状态", "headers": ["k"], "rows": [["v"]]}]
        ),
        recalled_memory=RecalledMemoryLayer(items=["recalled detail"]),
        rp_modules=RPModulesLayer(sections=[
            RPModuleRuntimeSection(
                id="combat",
                title="战斗",
                content="combat turn",
            ),
        ]),
        user_message=UserMessageLayer(user_input="hi"),
    )

    rendered = ctx.to_message_objects()

    assert [message.role for message in rendered] == [
        Role.SYSTEM,
        Role.SYSTEM,
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.SYSTEM,
        Role.SYSTEM,
        Role.SYSTEM,
        Role.SYSTEM,
        Role.SYSTEM,
        Role.USER,
    ]
    assert [message.content for message in rendered] == [
        "fixed|core",
        "pm|persistent",
        "summary|summary",
        "u1",
        "a1",
        "legacy system",
        "story|story detail",
        "tables|状态",
        "recalled|recalled detail",
        "[combat]\ncombat turn\n[/combat]",
        "hi",
    ]
