from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
from dataclasses import replace

import pytest

from commons.errors import MainContextWindowThresholdExceededError
from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_MEMORY_SUB_AGENT_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
    MEMORY_EMBED_BIZ_KEY,
    MEMORY_QUERY_PLANNER_BIZ_KEY,
    MEMORY_RERANK_BIZ_KEY,
)
from llm_client.types import ProviderChunk
from rpg_core.agent.protocol import StreamEventKind
from rpg_core.agent.runtime.main_llm import MainLLMSelectionService
from rpg_core.session.reset import SessionResetService
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionRoleService,
)
from rpg_core.status.manager import StatusManager
from rpg_core.tests.integration.scripted_llm import (
    CONFIG_PROVIDER_KEY,
    SESSION_PROVIDER_KEY,
    STORY_PROVIDER_KEY,
    response,
    tool_call,
)
from rp_memory.dream.application import DreamApplicationService
from rp_memory.dream.proposal import DreamProposalItemInput
from rp_memory.dream.types import DreamDepth, DreamScope
from rp_memory.dream.types import DreamEvidence, DreamProposalAction
from rp_memory.memory_types import EpistemicStatus, MemoryKind
from rp_memory.story_memory_service import StoryMemoryApplicationService

pytestmark = pytest.mark.integration


def _story_memory(gateway):  # noqa: ANN001, ANN202
    return StoryMemoryApplicationService(gateway.story_memory)


def _dream(gateway):  # noqa: ANN001, ANN202
    return DreamApplicationService(gateway.dream_memory)


@pytest.mark.asyncio
async def test_role_guard_bind_and_first_message_are_end_to_end_and_idempotent(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_role"
    first_message_template = "你——{USER_PLAY_ROLE_NAME}——在测试大厅醒来。"
    rendered_first_message = "你——Integration Tester——在测试大厅醒来。"
    agent = await integration_agent_factory(
        session_id,
        bind_role=False,
        first_message=first_message_template,
    )
    story = integration_data_gateway.catalog.get_session_story(session_id)
    assert story is not None
    integration_data_gateway.catalog.update_story(
        str(story.workspace_id),
        int(story.id),
        story_prompt="当前玩家是 {USER_PLAY_ROLE_NAME}。",
    )

    blocked = await agent.send("在吗？")

    assert "请选择你要扮演的角色" in blocked.text
    assert scripted_llm_manager.main_provider().calls == []
    assert integration_data_gateway.messages.count(session_id) == 0
    assert integration_data_gateway.backup.messages.count(session_id) == 0

    bound = await agent.execute_command("/role_bind 1")
    rebound = await agent.execute_command("/role_bind 1")

    assert bound.handled is True
    assert bound.reply == (
        "已绑定/切换扮演角色：Integration Tester。\n\n"
        + rendered_first_message
    )
    assert rebound.handled is True and "已绑定/切换扮演角色" in rebound.reply
    first_rows = integration_data_gateway.messages.list(session_id)
    first_backup = integration_data_gateway.backup.messages.list(session_id)
    assert [(row.role, row.content, row.turn_id, row.seq_in_turn) for row in first_rows] == [
        ("assistant", rendered_first_message, 1, 1),
    ]
    assert [(row.role, row.content) for row in first_backup] == [
        ("assistant", rendered_first_message)
    ]

    reply = await agent.send("现在开始")

    assert reply.text == "config-model response"
    main_system = scripted_llm_manager.main_provider().calls[-1].messages[0]["content"]
    assert "当前玩家扮演角色：Integration Tester" in main_system
    assert "当前玩家是 Integration Tester。" in main_system
    assert "Integration Tester [PLAYER_CHARACTER｜玩家当前扮演]" in main_system
    rows = integration_data_gateway.messages.list(session_id)
    assert [(row.turn_id, row.seq_in_turn) for row in rows] == [(1, 1), (2, 1), (2, 2)]
    assert integration_data_gateway.backup.messages.count(session_id) == 3


@pytest.mark.asyncio
async def test_clear_fully_resets_runtime_and_status_but_preserves_session_identity(
    integration_agent_factory,
    integration_data_gateway,
):
    from rpg_data import models

    session_id = "integration_clear"
    first_message = "欢迎 {USER_PLAY_ROLE_NAME}。"
    agent = await integration_agent_factory(
        session_id,
        with_status=True,
        first_message=first_message,
    )
    await agent.send("before clear")
    media_job = integration_data_gateway.media.create_job(
        session_id=session_id,
        provider_key="integration-local",
        source_start_turn_id=1,
        source_end_turn_id=1,
        source_fingerprint="a" * 64,
        source_snapshot_json='{"messages":[]}',
        visual_brief_json='{"sceneDescription":"clear integration"}',
    )
    claimed_media_job = integration_data_gateway.media.claim_next_job()
    assert claimed_media_job is not None and claimed_media_job.id == media_job.id
    media_session = integration_data_gateway.catalog.get_session(session_id)
    assert media_session is not None
    completed_media = integration_data_gateway.media.complete_job(
        job_id=media_job.id,
        write=models.MediaJobCompletionWrite(
            workspace_id=media_session.workspace_id,
            story_id=media_session.story_id,
            sha256="b" * 64,
            canonical_ext="png",
            mime_type="image/png",
            byte_size=64,
            relative_path=f"assets/images/{'b' * 64}.png",
            provider_asset_id="",
            metadata_json="{}",
            library_title="Generated image",
            library_description="clear integration",
            library_tags=("generated",),
        ),
    )
    assert completed_media is not None
    integration_data_gateway.media.set_background(
        session_id,
        completed_media.asset.id,
        source_mode=models.MEDIA_BACKGROUND_SOURCE_MANUAL,
    )
    selection = MainLLMSelectionService(integration_data_gateway)
    selected = await selection.set_session_provider_key(session_id, SESSION_PROVIDER_KEY)
    assert selected is not None
    module_override = integration_data_gateway.rp_modules.upsert_session_override(
        session_id,
        "narrative_outcome",
        enabled=False,
        config={},
    )
    assert module_override is not None
    _story_memory(integration_data_gateway).add_detail(
        session_id,
        "旧剧情记忆",
        turn_id=2,
    )
    integration_data_gateway.narrative_outcomes.append(models.NarrativeOutcomeCreate(
        session_id=session_id,
        turn_id=99,
        outcome_code="success",
        reason="旧裁定",
        actor="",
        sample_value=20,
        effective_weights=models.NarrativeOutcomeWeights(),
        effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
    ))

    template_copy = next(
        table
        for table in integration_data_gateway.status.list_tables(session_id)
        if table.source_table_id is not None
    )
    old_session_document = template_copy.document.with_existing_values([
        (template_copy.document.rows[0].key, "旧会话值")
    ])
    integration_data_gateway.status.save_table(template_copy.id, old_session_document)
    source_template = integration_data_gateway.status.get_template(
        int(template_copy.source_table_id)
    )
    assert source_template is not None
    current_template_document = source_template.document.with_existing_values([
        (source_template.document.rows[0].key, "当前 Story 模板值")
    ])
    integration_data_gateway.status.update_template(
        source_template.id,
        document=current_template_document,
    )
    deferred_document = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow(
            "长期进度",
            "旧值",
            update_frequency=models.STATUS_UPDATE_FREQUENCY_DEFERRED,
            deferred_interval_turns=2,
        )
    ])
    native_table = integration_data_gateway.status.create_table(
        session_id,
        "会话原生状态",
        document=deferred_document,
    )
    StatusManager(
        session_id,
        integration_data_gateway.status,
    ).commit_deferred_update(
        native_table.id,
        deferred_document.with_existing_values([("长期进度", "已推进")]),
        processed_keys=["长期进度"],
        last_processed_turn_id=2,
        base_document=deferred_document,
    )

    runtime_dir = integration_data_gateway.catalog.get_session_runtime_dir(session_id)
    summary_dir = runtime_dir / "summaries"
    (summary_dir / "old-summary.md").write_text("old summary", encoding="utf-8")
    nested_file = runtime_dir / "unknown" / "nested.bin"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_bytes(b"old runtime data")
    vector_db = runtime_dir / "memory_vectors.db"
    # RAG is disabled by default, so seed an existing derived index explicitly.
    with sqlite3.connect(vector_db) as connection:
        connection.execute("CREATE TABLE clear_marker (value TEXT)")
        connection.execute("INSERT INTO clear_marker VALUES ('old')")
    assert vector_db.is_file()

    backup_count = integration_data_gateway.backup.messages.count(session_id)
    role_service = SessionRoleService(integration_data_gateway.sessions)
    state_before = role_service.get_state(session_id)
    assert state_before.status is PlayerCharacterBindingStatus.BOUND

    result = await agent.execute_command("/clear")

    assert result.handled is True
    assert "游玩数据已清空" in result.reply
    assert "欢迎 Integration Tester。" in result.reply
    assert [(message.turn_id, message.content) for message in agent.history] == [
        (1, "欢迎 Integration Tester。")
    ]
    assert integration_data_gateway.messages.count(session_id) == 1
    assert _story_memory(integration_data_gateway).list(session_id) == []
    assert integration_data_gateway.narrative_outcomes.get_for_turn(session_id, 99) is None
    assert integration_data_gateway.media.list_jobs(session_id) == []
    assert integration_data_gateway.media.list_gallery(session_id) == []
    assert integration_data_gateway.media.get_background(session_id) is None
    assert (
        integration_data_gateway.media.get_library_asset_by_asset_id(
            completed_media.asset.id
        )
        is not None
    )
    assert (
        integration_data_gateway.media.get_workspace_blob_by_hash(
            "integration_workspace",
            "b" * 64,
        )
        is not None
    )
    assert integration_data_gateway.backup.messages.count(session_id) == backup_count + 1
    assert integration_data_gateway.status.list_deferred_progress(session_id) == []
    rebuilt = integration_data_gateway.status.get_table(session_id, template_copy.name)
    assert rebuilt.document.rows[0].value == "当前 Story 模板值"
    native_after = integration_data_gateway.status.get_table_by_id(native_table.id)
    assert native_after.id == native_table.id
    assert native_after.origin == models.STATUS_ORIGIN_SESSION_NATIVE
    assert native_after.document.rows[0].key == "长期进度"
    assert native_after.document.rows[0].value == ""
    assert (
        native_after.document.rows[0].update_frequency
        == models.STATUS_UPDATE_FREQUENCY_DEFERRED
    )
    assert not nested_file.exists()
    assert list(summary_dir.glob("*.md")) == []
    assert json.loads((runtime_dir / "rpg_summaries.json").read_text(encoding="utf-8")) == []
    assert not vector_db.exists()

    state_after = role_service.get_state(session_id)
    assert state_after == state_before
    session = integration_data_gateway.catalog.get_session(session_id)
    assert session is not None
    assert session.id == session_id
    assert session.main_llm_provider_key == SESSION_PROVIDER_KEY
    preserved_override = integration_data_gateway.rp_modules.get_session_override(
        session_id,
        "narrative_outcome",
    )
    assert preserved_override is not None
    assert preserved_override.module_name == module_override.module_name
    assert preserved_override.enabled == module_override.enabled
    assert preserved_override.config == module_override.config

    reply = await agent.send("after clear")
    assert reply.text == "session-model response"
    rows = integration_data_gateway.messages.list(session_id)
    assert [(row.turn_id, row.role) for row in rows] == [
        (1, "assistant"),
        (2, "user"),
        (2, "assistant"),
    ]
    assert rows[0].content == "欢迎 Integration Tester。"
    assert integration_data_gateway.backup.messages.count(session_id) == backup_count + 3


@pytest.mark.asyncio
async def test_clear_restores_runtime_and_history_when_database_reset_fails(
    integration_agent_factory,
    integration_data_gateway,
    monkeypatch,
):
    session_id = "integration_clear_rollback"
    agent = await integration_agent_factory(session_id)
    await agent.send("keep this turn")
    runtime_dir = integration_data_gateway.catalog.get_session_runtime_dir(session_id)
    marker = runtime_dir / "keep-me.txt"
    marker.write_text("old runtime", encoding="utf-8")
    rows_before = integration_data_gateway.messages.list(session_id)

    def fail_reset(_service: SessionResetService, _session_id: str):  # noqa: ANN202
        raise RuntimeError("database reset failed")

    monkeypatch.setattr(SessionResetService, "reset", fail_reset)

    result = await agent.execute_command("/clear")

    assert result.handled is True
    assert "执行失败" in result.reply
    assert "database reset failed" in result.reply
    assert marker.read_text(encoding="utf-8") == "old runtime"
    assert integration_data_gateway.messages.list(session_id) == rows_before
    assert len(agent.history) == len(rows_before)

    followup = await agent.send("still usable")
    assert followup.text == "config-model response"
    assert integration_data_gateway.messages.latest_turn_id(session_id) == 2


@pytest.mark.asyncio
async def test_clear_uses_the_same_reset_through_stream_command_bypass(
    integration_agent,
    integration_data_gateway,
):
    await integration_agent.send("stream clear target")

    events = [event async for event in integration_agent.send_stream("/clear")]

    assert [event.kind for event in events] == [
        StreamEventKind.TEXT,
        StreamEventKind.DONE,
    ]
    assert "游玩数据已清空" in events[-1].content
    assert integration_agent.history == []
    assert integration_data_gateway.messages.count("integration_smoke") == 0


@pytest.mark.asyncio
async def test_main_llm_runtime_priority_context_window_and_subagent_route_independence(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_llm_priority"
    agent = await integration_agent_factory(session_id, with_status=True)
    session = integration_data_gateway.catalog.get_session(session_id)
    story = integration_data_gateway.catalog.get_session_story(session_id)
    assert session is not None and story is not None
    selection = MainLLMSelectionService(integration_data_gateway)

    default_reply = await agent.send("config")
    story_selected = await selection.set_story_provider_key(
        str(story.workspace_id),
        int(story.id),
        STORY_PROVIDER_KEY,
    )
    story_reply = await agent.send("story")
    session_selected = await selection.set_session_provider_key(session_id, SESSION_PROVIDER_KEY)
    session_reply = await agent.send("session")
    preview = await agent.get_context_payload()
    session_cleared = await selection.set_session_provider_key(session_id, None)
    fallback_reply = await agent.send("fallback")

    assert default_reply.text == "config-model response"
    assert story_selected is not None and story_selected.effective_source == "story"
    assert story_reply.text == "story-model response"
    assert session_selected is not None and session_selected.effective_source == "session"
    assert session_reply.text == "session-model response"
    assert preview["usageEstimate"]["contextLimit"] == 8_192
    assert session_cleared is not None and session_cleared.effective_source == "story"
    assert fallback_reply.text == "story-model response"

    main_routes = [
        call.provider_key
        for call in scripted_llm_manager.calls
        if call.biz_key == AGENT_MAIN_BIZ_KEY
    ]
    assert main_routes == [
        CONFIG_PROVIDER_KEY,
        STORY_PROVIDER_KEY,
        SESSION_PROVIDER_KEY,
        STORY_PROVIDER_KEY,
    ]
    assert len(scripted_llm_manager.status.calls) == 8
    assert [
        {
            str(schema.get("function", {}).get("name", ""))
            for schema in (call.tools or [])
        }
        for call in scripted_llm_manager.status.calls
    ] == [
        {"rp_story_outcome"},
        {"select_status_targets"},
    ] * 4
    status_system = scripted_llm_manager.status.calls[0].messages[0]["content"]
    assert "当前玩家扮演角色：Integration Tester" in status_system
    assert "Integration Tester [PLAYER_CHARACTER｜玩家当前扮演]" in status_system
    assert scripted_llm_manager.status.get_default_model() == "status-model"
    assert any(
        call.biz_key == AGENT_STATUS_SUB_AGENT_BIZ_KEY and call.provider_key is None
        for call in scripted_llm_manager.calls
    )


@pytest.mark.asyncio
async def test_provider_switch_during_active_stream_only_applies_to_next_turn(
    integration_agent,
    integration_data_gateway,
    scripted_llm_manager,
):
    started = asyncio.Event()
    release = asyncio.Event()

    async def gated_stream(_messages, _tools):
        started.set()
        await release.wait()
        return (
            ProviderChunk(content="old provider reply"),
            ProviderChunk(
                finish_reason="stop",
                model="config-model",
            ),
        )

    scripted_llm_manager.main_provider().queue_stream(gated_stream)
    events = []

    async def consume() -> None:
        async for event in integration_agent.send_stream("first", request_id="req_switch"):
            events.append(event)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=2)
    selection = MainLLMSelectionService(integration_data_gateway)
    updated = await selection.set_session_provider_key("integration_smoke", SESSION_PROVIDER_KEY)
    assert updated is not None
    release.set()
    await asyncio.wait_for(task, timeout=2)

    assert events[-1].kind == StreamEventKind.DONE
    assert events[-1].content == "old provider reply"
    assert events[-1].model == "config-model"

    next_reply = await integration_agent.send("second")

    assert next_reply.text == "session-model response"
    rows = integration_data_gateway.messages.list("integration_smoke")
    assert [(row.turn_id, row.content) for row in rows] == [
        (1, "first"),
        (1, "old provider reply"),
        (2, "second"),
        (2, "session-model response"),
    ]


@pytest.mark.asyncio
async def test_story_memory_extraction_runs_after_commit_and_marks_message_rows(
    integration_agent_factory,
    integration_data_gateway,
    integration_settings,
    scripted_llm_manager,
    monkeypatch,
):
    monkeypatch.setattr(
        type(integration_settings),
        "memory_story_trigger_rounds",
        property(lambda self: 1),
    )
    session_id = "integration_story_memory"
    agent = await integration_agent_factory(session_id)
    def extract_with_prompt_evidence(messages, _tools):  # noqa: ANN001
        source_ids = [
            int(value)
            for value in re.findall(
                r"message_id=(\d+)",
                str(messages[1]["content"]),
            )
        ]
        return response(
            "",
            model="memory-model",
            tool_calls=[
                tool_call(
                    "extract_story_details",
                    json.dumps(
                        {
                            "story_details": [{
                                "text": "测试者在大厅发现了一枚银色钥匙。",
                                "memory_kind": "clue",
                                "epistemic_status": "confirmed",
                                "salience": 0.8,
                                "evidence_message_ids": source_ids,
                            }]
                        },
                        ensure_ascii=False,
                    ),
                )
            ],
        )

    scripted_llm_manager.memory.queue_chat(extract_with_prompt_evidence)

    reply = await agent.send("我捡起银色钥匙")

    assert reply.text == "config-model response"
    memories = _story_memory(integration_data_gateway).list(session_id)
    assert [item.text for item in memories] == ["测试者在大厅发现了一枚银色钥匙。"]
    assert [item.message_id for item in memories[0].evidence] == [
        row.id for row in integration_data_gateway.messages.list(session_id)
    ]
    rows = integration_data_gateway.messages.list(session_id)
    assert rows and all(row.story_memory_processed for row in rows)
    assert any(
        call.biz_key == AGENT_MEMORY_SUB_AGENT_BIZ_KEY and call.provider_key is None
        for call in scripted_llm_manager.calls
    )


@pytest.mark.asyncio
async def test_default_agent_disables_online_rag_but_keeps_story_and_persistent_memory(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    from rpg_data import models

    session_id = "integration_memory_disabled"
    agent = await integration_agent_factory(session_id)

    assert agent._lifecycle.resources.memory_manager is None  # noqa: SLF001

    scripted_llm_manager.main_provider().queue_chat(
        response("测试大厅的北门由银色机关控制。", model="config-model")
    )
    first = await agent.send("记住这条用于长期事实证据的消息。")
    assert first.committed_turn_id == 1
    assert first.text == "测试大厅的北门由银色机关控制。"

    snapshot = _dream(integration_data_gateway).build_source_snapshot(session_id)
    evidence_message = snapshot.messages[-1]
    source_fingerprint = "f" * 64
    proposal = _dream(integration_data_gateway).create_proposal(
        session_id,
        depth=DreamDepth.SHALLOW,
        scope=DreamScope.INCREMENTAL,
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint=source_fingerprint,
    )
    ready = _dream(integration_data_gateway).set_proposal_ready(
        proposal.id,
        (
            DreamProposalItemInput(
                action=DreamProposalAction.ADD,
                dedupe_key="a" * 64,
                text="测试大厅的北门由银色机关控制。",
                memory_kind=MemoryKind.WORLD_FACT,
                epistemic_status=EpistemicStatus.CONFIRMED,
                salience=0.9,
                evidence=(
                    DreamEvidence(
                        message_id=evidence_message.id,
                        turn_id=evidence_message.turn_id,
                        message_version=evidence_message.version,
                        content_hash=hashlib.sha256(
                            evidence_message.content.encode("utf-8")
                        ).hexdigest(),
                    ),
                ),
            ),
        ),
    )
    _dream(integration_data_gateway).apply_proposal(
        ready.id,
        history_fingerprint=snapshot.history_fingerprint,
        source_fingerprint=source_fingerprint,
    )
    _story_memory(integration_data_gateway).add_detail(
        session_id,
        "测试者在大厅拾取了一枚银色钥匙。",
        turn_id=1,
    )

    second = await agent.send("继续探索大厅。")
    provider_context = "\n".join(
        str(message.get("content") or "")
        for message in scripted_llm_manager.main_provider().calls[-1].messages
    )

    assert second.committed_turn_id == 2
    assert "## 剧情记忆" in provider_context
    assert "测试者在大厅拾取了一枚银色钥匙。" in provider_context
    assert "## 常驻记忆" in provider_context
    assert "测试大厅的北门由银色机关控制。" in provider_context
    assert "## 召回记忆" not in provider_context
    assert {
        MEMORY_EMBED_BIZ_KEY,
        MEMORY_QUERY_PLANNER_BIZ_KEY,
        MEMORY_RERANK_BIZ_KEY,
    }.isdisjoint(call.biz_key for call in scripted_llm_manager.calls)


@pytest.mark.asyncio
async def test_memory_recall_falls_back_locally_then_retries_remote_capability(
    integration_agent_factory,
    integration_data_gateway,
    integration_settings,
    scripted_llm_manager,
    monkeypatch,
):
    session_id = "integration_memory_retry"
    remote_memory_settings = replace(
        integration_settings.memory_settings,
        enabled=True,
        query_planner_enabled=True,
        rerank_enabled=True,
    )
    monkeypatch.setattr(
        type(integration_settings),
        "memory_settings",
        property(lambda self: remote_memory_settings),
    )
    agent = await integration_agent_factory(session_id)
    runtime_dir = integration_data_gateway.catalog.get_session_runtime_dir(session_id)
    summary_dir = runtime_dir / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "observatory.md").write_text(
        "银色天文仪被藏在测试大厅北侧的锁柜中。",
        encoding="utf-8",
    )

    original_get_provider = scripted_llm_manager.get_provider
    remote_attempts = {
        MEMORY_EMBED_BIZ_KEY: 0,
        MEMORY_QUERY_PLANNER_BIZ_KEY: 0,
        MEMORY_RERANK_BIZ_KEY: 0,
    }

    async def flaky_get_provider(biz_key: str, *, provider_key: str | None = None):
        if biz_key in remote_attempts:
            remote_attempts[biz_key] += 1
            if remote_attempts[biz_key] == 1:
                raise RuntimeError(f"{biz_key} temporarily unavailable")
        return await original_get_provider(biz_key, provider_key=provider_key)

    scripted_llm_manager.get_provider = flaky_get_provider  # type: ignore[method-assign]

    first = await agent.send("银色天文仪在哪里？")
    first_request = "\n".join(
        str(message.get("content") or "")
        for message in scripted_llm_manager.main_provider().calls[-1].messages
    )

    assert first.committed_turn_id == 1
    assert "银色天文仪" in first_request
    assert set(remote_attempts.values()) == {1}

    second = await agent.send("再确认一次天文仪的位置。")

    assert second.committed_turn_id == 2
    assert set(remote_attempts.values()) == {2}
    assert scripted_llm_manager.embedding.calls
    assert integration_data_gateway.messages.latest_turn_id(session_id) == 2


@pytest.mark.asyncio
async def test_deferred_status_runs_before_next_mailbox_item_and_isolates_batches(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    from rpg_data import models

    session_id = "integration_deferred"
    agent = await integration_agent_factory(session_id, with_status=True)
    failed_document = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow(
            "长期警戒",
            "低",
            update_frequency=models.STATUS_UPDATE_FREQUENCY_DEFERRED,
            deferred_interval_turns=1,
        )
    ])
    successful_document = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow(
            "长期信任",
            "低",
            update_frequency=models.STATUS_UPDATE_FREQUENCY_DEFERRED,
            deferred_interval_turns=1,
        )
    ])
    failed_table = integration_data_gateway.status.create_table(
        session_id,
        "失败批次",
        document=failed_document,
    )
    successful_table = integration_data_gateway.status.create_table(
        session_id,
        "成功批次",
        document=successful_document,
    )
    scripted_llm_manager.status.queue_chat(
        response("", model="status-model"),
        response("", model="status-model"),
        response(
            "",
            model="status-model",
            tool_calls=[tool_call("invalid_deferred_tool", "{}")],
        ),
        response(
            "",
            model="status-model",
            tool_calls=[
                tool_call(
                    "set_deferred_values",
                    '{"updates":[{"key":"长期信任","value":"中"}]}',
                )
            ],
        ),
    )

    reply = await agent.send("我连续守约并帮助了同伴。")
    command = await agent.execute_command("/help")

    assert reply.committed_turn_id == 1
    assert command.handled is True
    failed_after = integration_data_gateway.status.get_table_for_session(
        session_id,
        failed_table.id,
    )
    successful_after = integration_data_gateway.status.get_table_for_session(
        session_id,
        successful_table.id,
    )
    assert failed_after.document.row_for_key("长期警戒").value == "低"
    assert successful_after.document.row_for_key("长期信任").value == "中"
    progress = integration_data_gateway.status.list_deferred_progress(session_id)
    assert [(item.session_status_table_id, item.field_key, item.last_processed_turn_id) for item in progress] == [
        (successful_table.id, "长期信任", 1),
    ]


@pytest.mark.asyncio
async def test_different_sessions_progress_while_one_waits_on_remote_llm(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    first_agent = await integration_agent_factory("integration_concurrent_a")
    second_agent = await integration_agent_factory("integration_concurrent_b")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_reply(_messages, _tools):  # noqa: ANN001, ANN202
        entered.set()
        await release.wait()
        return response("session A completed", model="config-model")

    provider = scripted_llm_manager.main_provider()
    provider.queue_chat(
        blocked_reply,
        response("session B completed", model="config-model"),
    )

    first_task = asyncio.create_task(first_agent.send("block session A"))
    await asyncio.wait_for(entered.wait(), timeout=2)
    second_reply = await asyncio.wait_for(
        second_agent.send("allow session B"),
        timeout=2,
    )

    assert second_reply.text == "session B completed"
    assert not first_task.done()
    assert integration_data_gateway.messages.latest_turn_id(
        "integration_concurrent_b"
    ) == 1

    release.set()
    first_reply = await asyncio.wait_for(first_task, timeout=2)

    assert first_reply.text == "session A completed"
    assert integration_data_gateway.messages.latest_turn_id(
        "integration_concurrent_a"
    ) == 1


@pytest.mark.asyncio
async def test_turn_mode_style_snapshot_and_ooc_policy_are_end_to_end(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_composer"
    agent = await integration_agent_factory(session_id, with_status=True)
    session = integration_data_gateway.catalog.get_session(session_id)
    assert session is not None
    style = integration_data_gateway.session_composer.create_style(
        session.workspace_id,
        name="集成测试风格",
        prompt="COMPOSER_STYLE_PROMPT",
        sort_order=90,
    )
    assert style is not None
    mount = integration_data_gateway.session_composer.mount_story_style(
        session.workspace_id,
        session.story_id,
        style.id,
    )
    assert mount is not None

    preview = await agent.get_context_payload(mode="gm", narrative_style_id=style.id)
    assert any(
        "COMPOSER_STYLE_PROMPT" in str(message.get("content") or "")
        for message in preview["messages"]
    )

    status_calls_before = len(scripted_llm_manager.status.calls)
    ooc_reply = await agent.send(
        "解释当前规则",
        mode="ooc",
        narrative_style_id=style.id,
    )
    ooc_call = scripted_llm_manager.main_provider().calls[-1]
    ooc_content = "\n".join(str(message.get("content") or "") for message in ooc_call.messages)
    ooc_tool_names = {
        str(schema.get("function", {}).get("name", ""))
        for schema in (ooc_call.tools or [])
    }
    assert ooc_reply.committed_turn_id == 1
    assert len(scripted_llm_manager.status.calls) == status_calls_before
    assert "COMPOSER_STYLE_PROMPT" not in ooc_content
    assert "硬性边界：本轮是场外讨论" in ooc_content
    assert not ({"rp_story_outcome", "status_table_set_values", "write_file"} & ooc_tool_names)
    assert not any(name.startswith("scene_") for name in ooc_tool_names)

    gm_reply = await agent.send("推进场景", mode="gm", narrative_style_id=style.id)
    gm_call = scripted_llm_manager.main_provider().calls[-1]
    gm_content = "\n".join(str(message.get("content") or "") for message in gm_call.messages)
    assert gm_reply.committed_turn_id == 2
    assert len(scripted_llm_manager.status.calls) == status_calls_before + 2
    assert [
        {
            str(schema.get("function", {}).get("name", ""))
            for schema in (call.tools or [])
        }
        for call in scripted_llm_manager.status.calls[-2:]
    ] == [
        {"rp_story_outcome"},
        {"select_status_targets"},
    ]
    assert "COMPOSER_STYLE_PROMPT" in gm_content
    rows = integration_data_gateway.messages.list(session_id)
    assert [row.mode for row in rows] == ["ooc", "ooc", "gm", "gm"]
    assert all(row.summary_processed and row.summary_batch_id is None for row in rows[:2])
    assert all(row.story_memory_processed for row in rows[:2])


@pytest.mark.asyncio
async def test_main_context_and_preview_filter_summary_processed_rows_only(
    integration_agent_factory,
    integration_data_gateway,
    scripted_llm_manager,
):
    session_id = "integration_context_projection"
    agent = await integration_agent_factory(session_id)

    await agent.send("第一轮用户输入")
    before = await agent.get_context_payload()
    first_rows = integration_data_gateway.messages.list(session_id)
    first_user = next(row for row in first_rows if row.role == "user")
    integration_data_gateway.messages.mark_summary_processed(
        session_id,
        [first_user.id],
        batch_id=999,
    )

    after = await agent.get_context_payload()
    after_contents = [str(message["content"]) for message in after["messages"]]

    assert [row.content for row in integration_data_gateway.messages.list(session_id)] == [
        "第一轮用户输入",
        "config-model response",
    ]
    assert all("第一轮用户输入" not in content for content in after_contents)
    assert "config-model response" in after_contents
    assert after["usageEstimate"]["usedTokens"] < before["usageEstimate"]["usedTokens"]
    assert after["usageEstimate"]["usedTokens"] == after["totals"]["tokenCount"]

    await agent.send("第二轮用户输入")
    send_call = scripted_llm_manager.main_provider().calls[-1]
    send_contents = [str(message.get("content") or "") for message in send_call.messages]
    assert all("第一轮用户输入" not in content for content in send_contents)
    assert "config-model response" in send_contents
    assert any("第二轮用户输入" in content for content in send_contents)

    second_user = next(
        row
        for row in integration_data_gateway.messages.list(session_id)
        if row.role == "user" and row.content == "第二轮用户输入"
    )
    integration_data_gateway.messages.mark_summary_processed(
        session_id,
        [second_user.id],
        batch_id=1000,
    )

    events = [event async for event in agent.send_stream("第三轮用户输入")]
    stream_call = scripted_llm_manager.main_provider().calls[-1]
    stream_contents = [str(message.get("content") or "") for message in stream_call.messages]
    assert events[-1].kind == StreamEventKind.DONE
    assert stream_call.stream is True
    assert all("第一轮用户输入" not in content for content in stream_contents)
    assert all("第二轮用户输入" not in content for content in stream_contents)
    assert any("第三轮用户输入" in content for content in stream_contents)


@pytest.mark.asyncio
async def test_context_threshold_uses_filtered_current_context_and_excludes_new_input(
    integration_agent_factory,
    integration_data_gateway,
    integration_settings,
    scripted_llm_manager,
    monkeypatch,
):
    session_id = "integration_context_threshold"
    agent = await integration_agent_factory(session_id)
    await agent.send("第一轮用于门禁的用户输入")
    before = await agent.get_context_payload()
    used_tokens = int(before["usageEstimate"]["usedTokens"])
    context_limit = int(before["usageEstimate"]["contextLimit"])
    threshold_ratio = used_tokens / context_limit
    monkeypatch.setattr(
        type(integration_settings),
        "context_window_reject_threshold_ratio",
        property(lambda self: threshold_ratio),
    )
    main_call_count = len(scripted_llm_manager.main_provider().calls)

    with pytest.raises(MainContextWindowThresholdExceededError):
        await agent.send("这条正文不应写入历史")

    assert len(scripted_llm_manager.main_provider().calls) == main_call_count
    assert all(
        row.content != "这条正文不应写入历史"
        for row in integration_data_gateway.messages.list(session_id)
    )

    first_user = next(
        row
        for row in integration_data_gateway.messages.list(session_id)
        if row.role == "user"
    )
    integration_data_gateway.messages.mark_summary_processed(
        session_id,
        [first_user.id],
        batch_id=999,
    )
    after = await agent.get_context_payload()
    assert int(after["usageEstimate"]["usedTokens"]) < used_tokens

    reply = await agent.send("x" * 10_000)

    assert reply.text == "config-model response"


@pytest.mark.asyncio
async def test_summary_compression_writes_batches_and_flags_without_truncating_history(
    integration_agent_factory,
    integration_data_gateway,
    integration_settings,
    scripted_llm_manager,
    monkeypatch,
):
    settings_type = type(integration_settings)
    monkeypatch.setattr(settings_type, "memory_compression_enabled", property(lambda self: True))
    monkeypatch.setattr(settings_type, "memory_keep_rounds", property(lambda self: 1))
    monkeypatch.setattr(settings_type, "memory_compress_batch_size", property(lambda self: 1))
    session_id = "integration_summary"
    agent = await integration_agent_factory(session_id)
    scripted_llm_manager.memory.queue_chat(
        response(
            "",
            model="memory-model",
            tool_calls=[
                tool_call(
                    "generate_batch_summary",
                    '{"title":"第一批","summary_text":"第一轮摘要",'
                    '"time":"第一天","location":"大厅","characters":["测试者"]}',
                )
            ],
        ),
        response(
            "",
            model="memory-model",
            tool_calls=[
                tool_call(
                    "generate_batch_summary",
                    '{"title":"第二批","summary_text":"第二轮摘要",'
                    '"time":"第二天","location":"门厅","characters":["测试者"]}',
                )
            ],
        ),
            response(
                "",
                model="memory-model",
                tool_calls=[
                    tool_call(
                        "generate_overall_summary",
                        '{"title":"阶段总览","summary_text":"第一轮整体摘要",'
                        '"key_events":["发现线索"]}',
                    )
                ],
            ),
            response(
                "",
                model="memory-model",
                tool_calls=[
                    tool_call(
                        "generate_overall_summary",
                        '{"title":"总览","summary_text":"两轮整体摘要","key_events":["发现线索"]}',
                    )
                ],
        ),
    )

    await agent.send("第一轮")
    await agent.send("第二轮")
    await agent.send("第三轮")

    rows = integration_data_gateway.messages.list(session_id)
    assert len(rows) == 6
    assert [row.summary_processed for row in rows] == [True, True, True, True, False, False]
    assert len(agent.history) == 6
    runtime_dir = integration_data_gateway.catalog.get_session_runtime_dir(session_id)
    summary_dir = runtime_dir / "summaries"
    batch_files = sorted(path.name for path in summary_dir.glob("*.md") if path.name != "overall.md")
    assert len(batch_files) == 2
    assert (summary_dir / "overall.md").is_file()
