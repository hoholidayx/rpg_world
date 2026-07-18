from __future__ import annotations

from types import SimpleNamespace

import pytest

import rpg_core.agent.runtime.main_llm as main_llm_module
from llm_client.types import LLMBizCatalog, LLMProviderOption
from rpg_core.agent.runtime.main_llm import (
    InvalidMainLLMProviderKey,
    MainLLMSelectionService,
)
from rpg_data.repositories.story_repo import StoryRepository
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services.gateway import DataServiceGateway


@pytest.fixture
def main_llm_context(tmp_path, monkeypatch):
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    gateway = DataServiceGateway(tmp_path / "main_llm.sqlite3")
    database = gateway.database
    workspaces = WorkspaceRepository(database)
    stories = StoryRepository(database)

    with database.atomic():
        workspaces.create("llm_ws", "LLM Workspace", "data/llm_ws")
        story = stories.create("llm_ws", "LLM Story")
        session = gateway.catalog.create_session(
            "llm_ws",
            story.id,
            session_id="s_main_llm",
            title="Main LLM",
        )
    assert session is not None

    options = (
        LLMProviderOption("config_chat", "openai", "config-model", 128000),
        LLMProviderOption("story_chat", "openai", "story-model", 64000),
        LLMProviderOption("session_chat", "llama", "session.gguf", 8192),
    )
    remote_catalog = LLMBizCatalog(
        biz_key="agent.main",
        kind="chat",
        default_provider_key="config_chat",
        options=options,
    )

    class FakeManager:
        async def get_catalog(self, _biz_key):  # noqa: ANN001, ANN201
            return remote_catalog

    monkeypatch.setattr(
        main_llm_module.LLMClientManager,
        "get",
        classmethod(lambda cls: FakeManager()),
    )

    service = MainLLMSelectionService(gateway)
    yield SimpleNamespace(
        gateway=gateway,
        service=service,
        story=story,
        session=session,
        options=options,
    )
    gateway.close()


async def test_main_llm_selection_uses_config_story_session_precedence(main_llm_context) -> None:
    ctx = main_llm_context

    catalog = await ctx.service.get_provider_catalog()
    default_selection = await ctx.service.resolve_session(ctx.session.id)
    story_selection = await ctx.service.set_story_provider_key(
        ctx.story.workspace_id,
        ctx.story.id,
        "story_chat",
    )
    session_selection = await ctx.service.set_session_provider_key(
        ctx.session.id,
        "session_chat",
    )

    assert catalog.config_default_provider_key == "config_chat"
    assert catalog.options == ctx.options
    assert default_selection is not None
    assert default_selection.effective_provider_key == "config_chat"
    assert default_selection.effective_source == "config"
    assert story_selection is not None
    assert story_selection.effective_provider_key == "story_chat"
    assert story_selection.effective_source == "story"
    assert session_selection is not None
    assert session_selection.story_provider_key == "story_chat"
    assert session_selection.session_provider_key == "session_chat"
    assert session_selection.effective_provider_key == "session_chat"
    assert session_selection.effective_source == "session"
    assert session_selection.effective.context_window == 8192


async def test_clearing_main_llm_overrides_falls_back_one_scope_at_a_time(main_llm_context) -> None:
    ctx = main_llm_context
    await ctx.service.set_story_provider_key(ctx.story.workspace_id, ctx.story.id, "story_chat")
    await ctx.service.set_session_provider_key(ctx.session.id, "session_chat")

    session_cleared = await ctx.service.set_session_provider_key(ctx.session.id, None)
    story_cleared = await ctx.service.set_story_provider_key(
        ctx.story.workspace_id,
        ctx.story.id,
        None,
    )
    final_selection = await ctx.service.resolve_session(ctx.session.id)

    assert session_cleared is not None
    assert session_cleared.session_provider_key is None
    assert session_cleared.effective_provider_key == "story_chat"
    assert session_cleared.effective_source == "story"
    assert story_cleared is not None
    assert story_cleared.story_provider_key is None
    assert story_cleared.effective_provider_key == "config_chat"
    assert final_selection is not None
    assert final_selection.effective_source == "config"


async def test_invalid_persisted_overrides_are_reported_and_skipped(main_llm_context) -> None:
    ctx = main_llm_context
    ctx.gateway.catalog.set_story_main_llm_provider_key(
        ctx.story.workspace_id,
        ctx.story.id,
        "removed_story_chat",
    )
    ctx.gateway.catalog.set_session_main_llm_provider_key(
        ctx.session.id,
        "removed_session_chat",
    )

    fallback = await ctx.service.resolve_session(ctx.session.id)

    assert fallback is not None
    assert fallback.effective_provider_key == "config_chat"
    assert fallback.effective_source == "config"
    assert [(item.source, item.provider_key) for item in fallback.invalid_overrides] == [
        ("story", "removed_story_chat"),
        ("session", "removed_session_chat"),
    ]

    ctx.gateway.catalog.set_story_main_llm_provider_key(
        ctx.story.workspace_id,
        ctx.story.id,
        "story_chat",
    )
    story_fallback = await ctx.service.resolve_session(ctx.session.id)

    assert story_fallback is not None
    assert story_fallback.effective_provider_key == "story_chat"
    assert story_fallback.effective_source == "story"
    assert [(item.source, item.provider_key) for item in story_fallback.invalid_overrides] == [
        ("session", "removed_session_chat"),
    ]


@pytest.mark.parametrize("provider_key", ["", "  ", "not_selectable"])
async def test_main_llm_writes_reject_blank_or_non_whitelisted_keys(
    main_llm_context,
    provider_key: str,
) -> None:
    ctx = main_llm_context

    with pytest.raises(InvalidMainLLMProviderKey):
        await ctx.service.set_session_provider_key(ctx.session.id, provider_key)

    persisted = ctx.gateway.catalog.get_session(ctx.session.id)
    assert persisted is not None
    assert persisted.main_llm_provider_key is None


async def test_main_llm_selection_returns_none_for_unknown_catalog_targets(main_llm_context) -> None:
    ctx = main_llm_context

    assert await ctx.service.resolve_story("missing", ctx.story.id) is None
    assert await ctx.service.resolve_session("missing") is None
    assert await ctx.service.set_story_provider_key("missing", ctx.story.id, "not_selectable") is None
    assert await ctx.service.set_session_provider_key("missing", "not_selectable") is None
