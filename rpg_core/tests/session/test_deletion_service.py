from __future__ import annotations

import pytest

from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.deletion import (
    SessionDeleteResult,
    SessionDeletionService,
    SessionRuntimeCleanupStatus,
)
from rpg_core.status.manager import StatusManager
from rpg_data import models
from rpg_data.repositories.records import (
    SessionBackupMessageRecord,
    SessionMessageRecord,
    SessionNarrativeOutcomeRecord,
    SessionProfileRecord,
    SessionRPModuleOverrideRecord,
    SessionStatusDeferredProgressRecord,
    SessionStatusTableRecord,
    SessionStoryMemoryRecord,
)
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways
from rp_memory.story_memory_service import StoryMemoryApplicationService


@pytest.fixture(autouse=True)
def _reset_gateways(tmp_path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path / "workspaces"))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _prepared_session(tmp_path):  # noqa: ANN001, ANN202
    gateway = get_data_service_gateway(tmp_path / "session-delete.sqlite3")
    catalog = SessionCatalogService(gateway.sessions)
    session = catalog.create_session("demo_workspace", 1, title="Delete me")
    survivor = catalog.create_session("demo_workspace", 1, title="Keep me")
    assert session is not None
    assert survivor is not None

    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "main",
        turn_id=1,
        seq_in_turn=1,
    )
    gateway.backup.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "cold",
        turn_id=1,
        seq_in_turn=1,
    )
    StoryMemoryApplicationService(gateway.story_memory).add_detail(
        session.id,
        "memory",
        turn_id=1,
    )
    gateway.narrative_outcomes.append(models.NarrativeOutcomeCreate(
        session_id=session.id,
        turn_id=1,
        outcome_code="success",
        reason="delete coverage",
        actor="",
        sample_value=20,
        effective_weights=models.NarrativeOutcomeWeights(),
        effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
    ))
    gateway.rp_modules.upsert_session_override(
        session.id,
        "narrative_outcome",
        enabled=False,
        config={},
    )
    document = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow(
            "长期进度",
            "旧值",
            update_frequency=models.STATUS_UPDATE_FREQUENCY_DEFERRED,
            deferred_interval_turns=2,
        )
    ])
    native = gateway.status.create_table(session.id, "Delete native", document=document)
    StatusManager(session.id, gateway.status).commit_deferred_update(
        native.id,
        document,
        processed_keys=["长期进度"],
        last_processed_turn_id=1,
        base_document=document,
    )
    runtime_dir = gateway.catalog.get_session_runtime_dir(session.id)
    marker = runtime_dir / "nested" / "marker.bin"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"delete")
    return gateway, session, survivor, runtime_dir


def test_delete_removes_catalog_children_and_runtime_directory(tmp_path) -> None:
    gateway, session, survivor, runtime_dir = _prepared_session(tmp_path)

    result = SessionDeletionService(gateway.sessions).delete(session.id)

    assert result == SessionDeleteResult(
        session_id=session.id,
        runtime_cleanup=SessionRuntimeCleanupStatus.DELETED,
    )
    assert gateway.catalog.get_session(session.id) is None
    assert gateway.catalog.get_session(survivor.id) is not None
    assert not runtime_dir.exists()
    assert SessionProfileRecord.select().where(SessionProfileRecord.session == session.id).count() == 0
    assert SessionMessageRecord.select().where(SessionMessageRecord.session == session.id).count() == 0
    assert SessionBackupMessageRecord.select().where(SessionBackupMessageRecord.session == session.id).count() == 0
    assert SessionStoryMemoryRecord.select().where(SessionStoryMemoryRecord.session == session.id).count() == 0
    assert SessionNarrativeOutcomeRecord.select().where(SessionNarrativeOutcomeRecord.session == session.id).count() == 0
    assert SessionStatusTableRecord.select().where(SessionStatusTableRecord.session == session.id).count() == 0
    assert SessionStatusDeferredProgressRecord.select().count() == 0
    assert SessionRPModuleOverrideRecord.select().where(SessionRPModuleOverrideRecord.session == session.id).count() == 0


def test_delete_succeeds_when_runtime_directory_is_absent(tmp_path) -> None:
    gateway, session, _survivor, runtime_dir = _prepared_session(tmp_path)
    import shutil

    shutil.rmtree(runtime_dir)

    result = SessionDeletionService(gateway.sessions).delete(session.id)

    assert result is not None
    assert result.runtime_cleanup == SessionRuntimeCleanupStatus.ABSENT
    assert gateway.catalog.get_session(session.id) is None


def test_delete_restores_runtime_when_database_delete_fails(tmp_path, monkeypatch) -> None:
    gateway, session, _survivor, runtime_dir = _prepared_session(tmp_path)
    marker = runtime_dir / "nested" / "marker.bin"

    def fail_delete(_session_id: str) -> bool:
        raise RuntimeError("database delete failed")

    monkeypatch.setattr(
        gateway.sessions._sessions,
        "delete_ready_without_active_derivation",
        fail_delete,
    )

    with pytest.raises(RuntimeError, match="database delete failed"):
        SessionDeletionService(gateway.sessions).delete(session.id)

    assert gateway.catalog.get_session(session.id) is not None
    assert marker.read_bytes() == b"delete"
    assert list(runtime_dir.parent.glob(f".{runtime_dir.name}.delete-*")) == []


def test_delete_reports_pending_when_quarantine_cleanup_fails(
    tmp_path,
    monkeypatch,
) -> None:
    gateway, session, _survivor, runtime_dir = _prepared_session(tmp_path)

    def fail_cleanup(_path) -> None:  # noqa: ANN001
        raise OSError("busy runtime")

    monkeypatch.setattr("rpg_core.session.deletion.shutil.rmtree", fail_cleanup)

    result = SessionDeletionService(gateway.sessions).delete(session.id)

    assert result is not None
    assert result.runtime_cleanup == SessionRuntimeCleanupStatus.PENDING
    assert gateway.catalog.get_session(session.id) is None
    assert not runtime_dir.exists()
    assert len(list(runtime_dir.parent.glob(f".{runtime_dir.name}.delete-*"))) == 1


def test_delete_missing_session_returns_none(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "session-delete-missing.sqlite3")

    assert SessionDeletionService(gateway.sessions).delete("missing_session") is None
