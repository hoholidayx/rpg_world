from __future__ import annotations

from types import SimpleNamespace

import pytest

import rpg_world.rpg_core.context.builder as builder_module
from rpg_world.rpg_core.context.builder import RPGContextBuilder
from rpg_world.rpg_core.context.config import ExtensionModuleDef, RPGContextConfig
from rpg_world.rpg_core.context.rpg_context import Message, Role, RPGContext, LayerType
from rpg_world.rpg_core.tests.conftest import FakeTokenCounter


class FakeManager:
    def __init__(self, entries) -> None:
        self.entries = entries

    def list_enabled_entries(self):
        return list(self.entries)

    def list_enabled_characters(self):
        return list(self.entries)


class FakePersistentStore:
    def __init__(self, sections):
        self.sections = sections

    def get_sections(self):
        return list(self.sections)


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
        return f"fixed|{context['system_prompt']}|{len(context['lorebook_entries'])}|{len(context['characters'])}"
    if template_name == "modules/persistent_memory.jinja":
        return "pm|" + ",".join(context["persistent_memory"])
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
    return template_name


@pytest.fixture(autouse=True)
def _patch_renderer(monkeypatch):
    monkeypatch.setattr(builder_module, "render_jinja_template", _fake_render)


def test_build_context_layers_and_user_extensions(fake_token_counter):
    config = RPGContextConfig(
        hot_history_rounds=1,
        user_extension=[
            ExtensionModuleDef(name="prefix", template="modules/user_reply_prefix.jinja", position="before"),
            ExtensionModuleDef(name="suffix", template="modules/user_reply_suffix.jinja", position="after"),
        ],
    )
    builder = RPGContextBuilder(config=config, world_name="Test World")
    builder.set_summary_store(FakeSummaryStore(("overall summary", 1)))
    builder.set_persistent_memory_store(FakePersistentStore(["p1", "p2"]))
    builder.set_story_memory_store(FakeStoryStore([{"text": "story 1"}]))
    builder.set_recalled_memory_store(FakeRecalledStore(["recall 1"]))
    builder.set_batch_summary_store(FakeSummaryStore(("overall summary", 1)))

    messages = [
        Message(Role.SYSTEM, "system"),
        Message(Role.USER, "u1"),
        Message(Role.ASSISTANT, "a1"),
        Message(Role.USER, "u2"),
        Message(Role.ASSISTANT, "a2"),
        Message(Role.USER, "current"),
    ]

    ctx = builder.build(
        system_prompt="prompt",
        messages=messages,
        character_mgr=FakeManager([{"name": "Alice"}]),
        lorebook_mgr=FakeManager([{"name": "Lore"}]),
        status_mgr=SimpleNamespace(
            list_types=lambda: ["全局状态"],
            list_tables=lambda type_name: ["当前场景", "世界状态"],
            get_table=lambda type_name, table_name: {
                "name": table_name,
                "headers": ["属性", "值"],
                "rows": [["k", "v"]],
            },
        ),
        scene_tracker=FakeStatusTracker(),
    )

    assert isinstance(ctx, RPGContext)
    assert ctx.fixed_layer.startswith("fixed|prompt|1|1")
    assert ctx.persistent_memory == "pm|p1,p2"
    assert ctx.summary == "summary|overall summary"
    assert [m.content for m in ctx.hot_history] == ["u2", "a2"]
    assert ctx.story_memory == "story|story 1"
    assert ctx.recalled_memory == "recalled|recall 1"
    assert ctx.status_tables == "tables|世界状态"
    assert ctx.user_before == "prefix"
    assert ctx.user_after == "suffix"

    rendered = ctx.to_message_objects()
    assert rendered[-1].role is Role.USER
    assert "prefix" in rendered[-1].content
    assert "current" in rendered[-1].content
    assert "suffix" in rendered[-1].content

    summary = ctx.layer_summary(fake_token_counter)
    assert summary[-1].type == LayerType.USER_MESSAGE
    assert summary[-1].status == "active"
    assert summary[0].description.startswith("system prompt")
    assert summary[3].description == "1 轮对话 (user/assistant)"


def test_context_to_markdown_and_empty_layers(fake_token_counter):
    ctx = RPGContext(fixed_layer="fixed", user_input="hi")
    md = ctx.to_markdown(fake_token_counter)

    assert "## 上下文概览" in md
    assert "## 分层明细" in md
    assert "Fixed Layer" in md
    assert "User Message" in md
    assert "总 token" in md
    assert "| Layer | Status | Tokens | Description |" not in md
