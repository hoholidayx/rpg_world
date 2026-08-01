"""Opt-in real-Provider acceptance for an arbitrary current Story Pack."""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from llm_client.auth import resolve_llm_service_token
from llm_client.keys import AGENT_PLOT_SCHEDULER_BIZ_KEY
from llm_client.manager import LLMClientManager
from tests.story_acceptance.generator import generate_natural_acceptance_flow
from tests.story_acceptance.errors import is_infrastructure_error
from tests.story_acceptance.integrity import (
    changed_fingerprints,
    fingerprint_files,
    protected_paths,
)
from tests.story_acceptance.loader import (
    StoryAcceptanceInputError,
    load_acceptance_profile,
    load_story_pack,
)
from tests.story_acceptance.models import AcceptanceStatus
from tests.story_acceptance.reporting import (
    AcceptanceRunWriter,
    summarize_live_calls,
)
from tests.story_acceptance.runner import StoryAcceptanceRunner


pytestmark = [pytest.mark.integration, pytest.mark.live_llm]

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
async def test_live_story_pack_acceptance(
    request: pytest.FixtureRequest,
    integration_settings,  # noqa: ARG001
    integration_workspace: Path,
    integration_data_gateway,
    live_call_recorder,
) -> None:
    """Import into temporary runtime state and aggregate all flow outcomes."""

    project_arg = request.config.getoption("--story-project")
    pack_arg = request.config.getoption("--story-pack")
    if project_arg is None and pack_arg is None:
        pytest.skip("provide --story-project or --story-pack")
    try:
        loaded = load_story_pack(
            project_root=project_arg,
            pack_path=pack_arg,
        )
        profile = load_acceptance_profile(
            loaded,
            profile_path=request.config.getoption("--story-profile"),
            player_character_ref=request.config.getoption("--story-player-ref"),
        )
    except StoryAcceptanceInputError as exc:
        raise pytest.UsageError(str(exc)) from exc

    suite = str(request.config.getoption("--story-suite"))
    report_root = request.config.getoption("--story-report-dir")
    llm_timeout_seconds = int(
        request.config.getoption("--story-llm-timeout-seconds")
    )
    if llm_timeout_seconds < 1:
        raise pytest.UsageError(
            "--story-llm-timeout-seconds must be a positive integer"
        )
    guarded_paths = protected_paths(
        loaded,
        repository_root=_REPOSITORY_ROOT,
    )
    protected_before = fingerprint_files(guarded_paths)
    database_path = Path(os.environ["RPG_WORLD_DB_PATH"]).resolve()
    workspace_base = Path(os.environ["RPG_WORLD_WORKSPACE_ROOT_BASE"]).resolve()
    writer = AcceptanceRunWriter(
        report_root=report_root,
        pack_id=loaded.pack.pack_id,
        run_metadata={
            "gitCommit": _git_commit(),
            "packPath": str(loaded.path),
            "packId": loaded.pack.pack_id,
            "projectId": loaded.pack.project_id,
            "sourceRevision": loaded.pack.source_revision,
            "sourceDigest": loaded.pack.source_digest,
            "canonicalPackDigest": loaded.canonical_digest,
            "packFileSha256": loaded.file_sha256,
            "suite": suite,
            "stableSeed": "production scheduler: session_id + story_id + turn_id",
            "environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "liveLlmTest": os.environ.get("LIVE_LLM_TEST") == "1",
                "llmRequestTimeoutSeconds": llm_timeout_seconds,
                "temporaryDatabase": str(database_path),
                "temporaryWorkspaceBase": str(workspace_base),
            },
            "protectedBefore": protected_before,
        },
    )
    writer.write_json_artifact(
        "effective-profile.json",
        profile.model_dump(by_alias=True, exclude_none=True),
    )

    runner: StoryAcceptanceRunner | None = None
    report = None
    generation_result: tuple[AcceptanceStatus, str, tuple[str, ...]] | None = None
    try:
        await LLMClientManager.aconfigure(
            base_url=os.environ.get(
                "RPG_WORLD_LLM_SERVICE_URL",
                "http://127.0.0.1:8012/llm/v1",
            ),
            token=resolve_llm_service_token(),
            request_timeout_ms=llm_timeout_seconds * 1000,
            stream_timeout_ms=max(300, llm_timeout_seconds) * 1000,
        )
        try:
            await asyncio.wait_for(
                LLMClientManager.get().client.health(),
                timeout=30,
            )
        except Exception as exc:
            runner = StoryAcceptanceRunner(
                gateway=integration_data_gateway,
                loaded=loaded,
                profile=profile,
                suite=suite,
                calls=live_call_recorder,
                writer=writer,
            )
            report = runner.report
            report.add(
                check_id="infrastructure.llm_service_health",
                category="infrastructure",
                status=AcceptanceStatus.INFRASTRUCTURE_ERROR,
                summary="独立 LLM Service health 检查失败",
                evidence=(f"{type(exc).__name__}: {exc}",),
            )
        else:
            if (
                request.config.getoption("--story-profile") is None
                and suite == "full"
            ):
                try:
                    provider = await LLMClientManager.get().get_provider(
                        AGENT_PLOT_SCHEDULER_BIZ_KEY
                    )
                    generated = await asyncio.wait_for(
                        generate_natural_acceptance_flow(
                            provider,
                            loaded=loaded,
                        ),
                        timeout=180,
                    )
                    profile = profile.model_copy(
                        update={"flows": [*profile.flows, generated]}
                    )
                    generation_result = (
                        AcceptanceStatus.PASS,
                        "独立 LLM 已从 Story 定义生成自然剧情验收流程",
                        (f"flowId={generated.id}", f"steps={len(generated.steps)}"),
                    )
                except Exception as exc:
                    generation_result = (
                        (
                            AcceptanceStatus.INFRASTRUCTURE_ERROR
                            if is_infrastructure_error(exc)
                            else AcceptanceStatus.NEEDS_REVIEW
                        ),
                        "无 sidecar 的自然剧情流程生成未得到可靠结果",
                        (f"{type(exc).__name__}: {exc}",),
                    )
            writer.write_json_artifact(
                "effective-profile.json",
                profile.model_dump(by_alias=True, exclude_none=True),
            )
            runner = StoryAcceptanceRunner(
                gateway=integration_data_gateway,
                loaded=loaded,
                profile=profile,
                suite=suite,
                calls=live_call_recorder,
                writer=writer,
            )
            if generation_result is not None:
                runner.report.add(
                    check_id="profile.generated_flow",
                    category="profile",
                    status=generation_result[0],
                    summary=generation_result[1],
                    evidence=generation_result[2],
                )
            report = await runner.run()
    except Exception as exc:
        if report is None:
            if runner is None:
                runner = StoryAcceptanceRunner(
                    gateway=integration_data_gateway,
                    loaded=loaded,
                    profile=profile,
                    suite=suite,
                    calls=live_call_recorder,
                    writer=writer,
                )
            report = runner.report
        report.add(
            check_id="framework.unhandled",
            category="framework",
            status=(
                AcceptanceStatus.INFRASTRUCTURE_ERROR
                if is_infrastructure_error(exc)
                else AcceptanceStatus.FAIL
            ),
            summary="Story acceptance 顶层执行发生未处理异常",
            evidence=(f"{type(exc).__name__}: {exc}",),
        )
    finally:
        await LLMClientManager.areset()

    assert report is not None
    temp_root = integration_workspace.resolve()
    target_workspace = (workspace_base / loaded.pack.target.workspace_root).resolve()
    isolated = (
        database_path.is_relative_to(temp_root)
        and workspace_base.is_relative_to(temp_root)
        and target_workspace.is_relative_to(temp_root)
        and Path(integration_data_gateway.database.database).resolve()
        == database_path
    )
    report.add(
        check_id="isolation.temporary_runtime",
        category="isolation",
        status=AcceptanceStatus.PASS if isolated else AcceptanceStatus.FAIL,
        summary=(
            "数据库与 Story Workspace 均位于 pytest 临时目录"
            if isolated
            else "验收运行态逃离 pytest 临时目录"
        ),
        evidence=(
            f"tmpRoot={temp_root}",
            f"database={database_path}",
            f"workspaceBase={workspace_base}",
            f"targetWorkspace={target_workspace}",
        ),
    )
    protected_after = fingerprint_files(
        protected_paths(
            loaded,
            repository_root=_REPOSITORY_ROOT,
        )
    )
    changed = changed_fingerprints(protected_before, protected_after)
    report.add(
        check_id="isolation.protected_files_unchanged",
        category="isolation",
        status=AcceptanceStatus.PASS if not changed else AcceptanceStatus.FAIL,
        summary=(
            "DesignProject、Story Pack、integration marker 与正式数据库字节未变"
            if not changed
            else "验收期间有受保护文件发生字节变化"
        ),
        evidence=(f"changed={changed}",),
    )
    writer.finalize(
        report,
        calls=live_call_recorder,
        semantic_review_items=(
            runner.semantic_review_items if runner is not None else ()
        ),
        final_metadata={
            "usage": summarize_live_calls(live_call_recorder),
            "protectedAfter": protected_after,
            "protectedChanged": changed,
            "effectiveProfile": "effective-profile.json",
        },
    )
    print(f"Story acceptance report: {writer.run_dir / 'report.md'}")
    failure_reasons: list[str] = []
    if report.hard_failures:
        failures = "; ".join(
            f"{item.id}: {item.summary}" for item in report.hard_failures
        )
        failure_reasons.append(f"hard failures: {failures}")
    if runner is not None and runner.semantic_review_items:
        failure_reasons.append(
            "Codex review required: copy codex-review-template.json to "
            "codex-review.json, complete the evidence-bound review, then run "
            "python -m tests.story_acceptance.codex_review finalize"
        )
    if failure_reasons:
        pytest.fail(
            f"Story acceptance is not final; report={writer.run_dir}: "
            + "; ".join(failure_reasons)
        )


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"
