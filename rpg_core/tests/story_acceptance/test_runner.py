from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from llm_client.client import LLMServiceTimeout
from llm_client.keys import (
    AGENT_MAIN_BIZ_KEY,
    AGENT_STATUS_SUB_AGENT_BIZ_KEY,
)
from rpg_data.services.gateway import DataServiceGateway
from tests.story_acceptance.errors import is_infrastructure_error
from tests.story_acceptance.integrity import (
    changed_fingerprints,
    fingerprint_files,
    protected_paths,
)
from tests.story_acceptance.loader import load_acceptance_profile, load_story_pack
from tests.story_acceptance.models import (
    AcceptanceStatus,
    StoryAcceptanceFlow,
    StoryAcceptanceStep,
)
from tests.story_acceptance.reporting import AcceptanceReport
from tests.story_acceptance.runner import (
    ImportedStory,
    StepResult,
    StoryAcceptanceRunner,
)
from tests.support.live_agent import RecordedLiveCall


class _Writer:
    def __init__(self) -> None:
        self.flushed = 0

    def flush_calls(self, calls) -> None:  # noqa: ANN001
        self.flushed += 1

    def append_step(self, value) -> None:  # noqa: ANN001
        pass


def test_llm_client_failures_are_infrastructure_errors() -> None:
    assert is_infrastructure_error(LLMServiceTimeout("timed out"))
    assert not is_infrastructure_error(AssertionError("protocol mismatch"))


def test_project_integrity_scope_detects_new_protected_artifacts(
    story_pack_value: dict,
    tmp_path: Path,
) -> None:
    loaded, _profile = _loaded_profile(tmp_path, story_pack_value)
    project = tmp_path / "project"
    existing = [
        project / "design-project.json",
        project / "design/current.json",
        project / "design/revisions/r000002.json",
        project / "design/checkpoints/baseline.json",
        project / "artifacts/story-packs/current.json",
        project / "artifacts/snapshots/current.json",
        project / "integrations/rpg-world.json",
    ]
    for path in existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    project_loaded = replace(loaded, project_root=project.resolve())
    before = fingerprint_files(
        protected_paths(project_loaded, repository_root=tmp_path)
    )

    added = project / "design/checkpoints/new-checkpoint.json"
    added.write_text("{}\n", encoding="utf-8")
    after = fingerprint_files(
        protected_paths(project_loaded, repository_root=tmp_path)
    )

    assert {str(path.resolve()) for path in existing}.issubset(before)
    assert changed_fingerprints(before, after) == [str(added.resolve())]


def _tool_schema(name: str) -> dict[str, object]:
    return {"type": "function", "function": {"name": name}}


def _tool_response(name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "toolCalls": [{
            "function": {
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            }
        }]
    }


def test_status_route_allowlist_ignores_main_agent_fallback() -> None:
    runner = object.__new__(StoryAcceptanceRunner)
    runner.report = AcceptanceReport(
        pack_id="pack",
        source_revision="r1",
        source_digest="0" * 64,
        suite="smoke",
    )
    flow = StoryAcceptanceFlow(
        id="status_flow",
        title="状态回退",
        steps=[{"id": "update", "input": "我确认两项事实已经发生变化。"}],
    )
    step = StoryAcceptanceStep(
        id="update",
        input="我确认两项事实已经发生变化。",
    )
    calls = (
        RecordedLiveCall(
            biz_key=AGENT_STATUS_SUB_AGENT_BIZ_KEY,
            messages=[],
            tools=[_tool_schema("select_status_targets")],
            response=_tool_response(
                "select_status_targets",
                {"tables": [{"table_id": 1, "keys": ["状态"]}]},
            ),
        ),
        RecordedLiveCall(
            biz_key=AGENT_STATUS_SUB_AGENT_BIZ_KEY,
            messages=[],
            tools=[_tool_schema("status_table_set_values")],
            response=_tool_response(
                "status_table_set_values",
                {"table_id": 1, "updates": [{"key": "状态", "value": "已更新"}]},
            ),
        ),
        RecordedLiveCall(
            biz_key=AGENT_MAIN_BIZ_KEY,
            messages=[],
            tools=[_tool_schema("status_table_set_values")],
            response=_tool_response(
                "status_table_set_values",
                {"table_id": 2, "updates": [{"key": "备注", "value": "已补偿"}]},
            ),
        ),
    )
    result = StepResult(
        flow_id=flow.id,
        step_id=step.id,
        session_id="session",
        user_input=step.input,
        mode=step.mode,
        reply_text="完成。",
        committed_turn_id=1,
        calls=calls,
        actual_tools=(),
        status_before={
            "表一": {"id": 1, "rows": {}},
            "表二": {"id": 2, "rows": {}},
        },
        status_after={},
        plot_before={},
        plot_after={},
        persisted_messages=(),
        backup_messages=(),
        outcome=None,
        runtime_plot_directives=(),
    )

    runner._check_status_route_allowlist(flow, step, result)

    assert len(runner.report.checks) == 1
    assert runner.report.checks[0].status is AcceptanceStatus.PASS


def _loaded_profile(tmp_path: Path, pack: dict):
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    loaded = load_story_pack(pack_path=pack_path)
    profile = load_acceptance_profile(
        loaded,
        profile_path=None,
        player_character_ref="character-player",
    )
    return loaded, profile


def test_formal_runtime_import_uses_only_temporary_database(
    story_pack_value: dict,
    tmp_path: Path,
) -> None:
    loaded, profile = _loaded_profile(tmp_path, story_pack_value)
    pack_before = fingerprint_files([loaded.path])
    gateway = DataServiceGateway(tmp_path / "runtime.sqlite3")
    gateway.initialize()
    try:
        runner = StoryAcceptanceRunner(
            gateway=gateway,
            loaded=loaded,
            profile=profile,
            suite="smoke",
            calls=[],
            writer=_Writer(),
        )

        imported = runner._import_pack()

        assert imported.story_id > 0
        assert imported.preview_result["plan"]["conflicts"] == []
        assert imported.repeated_preview_result["alreadyApplied"] is True
        assert Path(gateway.database.database).resolve().is_relative_to(tmp_path)
        assert changed_fingerprints(
            pack_before,
            fingerprint_files([loaded.path]),
        ) == []
    finally:
        gateway.close()


def test_semantic_rubric_is_queued_for_codex_without_verifier_llm(
    story_pack_value: dict,
    tmp_path: Path,
) -> None:
    loaded, profile = _loaded_profile(tmp_path, story_pack_value)
    gateway = DataServiceGateway(tmp_path / "runtime.sqlite3")
    gateway.initialize()
    try:
        runner = StoryAcceptanceRunner(
            gateway=gateway,
            loaded=loaded,
            profile=profile,
            suite="full",
            calls=[],
            writer=_Writer(),
        )
        flow = StoryAcceptanceFlow(
            id="semantic_flow",
            title="语义证据",
            steps=[{
                "id": "observe",
                "input": "我只观察眼前已经发生的情况。",
                "semanticRubric": ["不得替玩家角色新增决定。"],
            }],
        )
        step = flow.steps[0]
        result = StepResult(
            flow_id=flow.id,
            step_id=step.id,
            session_id="session",
            user_input=step.input,
            mode=step.mode,
            reply_text="门厅里只有雨声。",
            committed_turn_id=1,
            calls=(),
            actual_tools=(),
            status_before={},
            status_after={},
            plot_before={},
            plot_after={},
            persisted_messages=(),
            backup_messages=(),
            outcome=None,
            runtime_plot_directives=(),
            call_start=4,
            call_end_exclusive=7,
        )

        runner._queue_semantic_review(flow, step, result)

        assert len(runner.semantic_review_items) == 1
        queued = runner.semantic_review_items[0]
        assert queued["rubric"] == ["不得替玩家角色新增决定。"]
        assert queued["providerCallRange"] == {
            "start": 4,
            "endExclusive": 7,
        }
        check = runner.report.checks[-1]
        assert check.status is AcceptanceStatus.NEEDS_REVIEW
        assert "等待当前 Codex" in check.summary
    finally:
        gateway.close()


@pytest.mark.asyncio
async def test_flow_failure_does_not_stop_later_flows(
    story_pack_value: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded, profile = _loaded_profile(tmp_path, story_pack_value)
    second = StoryAcceptanceFlow(
        id="second_flow",
        title="第二流程",
        suites=["smoke", "full"],
        steps=[{"id": "observe", "input": "我观察已经发生的情况。"}],
    )
    profile = profile.model_copy(update={"flows": [profile.flows[0], second]})
    gateway = DataServiceGateway(tmp_path / "runtime.sqlite3")
    gateway.initialize()
    writer = _Writer()
    runner = StoryAcceptanceRunner(
        gateway=gateway,
        loaded=loaded,
        profile=profile,
        suite="smoke",
        calls=[],
        writer=writer,
    )
    imported = ImportedStory(
        workspace_id="test_world",
        story_id=1,
        id_mapping={},
        validate_result={},
        preview_result={},
        apply_result={},
        repeated_preview_result={},
    )
    attempted: list[str] = []

    monkeypatch.setattr(runner, "_import_pack", lambda: imported)
    monkeypatch.setattr(runner, "_check_imported_resources", lambda value: None)
    monkeypatch.setattr(
        runner,
        "_check_plot_definition_and_distribution",
        lambda value: None,
    )
    monkeypatch.setattr(runner, "_check_no_derivation_jobs", lambda: None)

    async def run_flow(flow, *, ordinal):  # noqa: ANN001, ARG001
        attempted.append(flow.id)
        if flow.id == profile.flows[0].id:
            raise AssertionError("first flow failed")

    monkeypatch.setattr(runner, "_run_flow", run_flow)
    try:
        report = await runner.run()
    finally:
        gateway.close()

    assert attempted == [profile.flows[0].id, "second_flow"]
    failure = next(
        item for item in report.checks if item.id.endswith(".unhandled")
    )
    assert failure.status is AcceptanceStatus.FAIL
    assert writer.flushed == 2
