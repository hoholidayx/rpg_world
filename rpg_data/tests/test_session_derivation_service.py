from __future__ import annotations

from pathlib import Path

import pytest

from rpg_data import models
from rpg_data.repositories.records import (
    SessionBackupMessageRecord,
    SessionMessageRecord,
    SessionNarrativeOutcomeRecord,
    SessionProfileRecord,
    SessionStoryMemoryRecord,
)
from rpg_data.services import (
    SessionDerivationDataError,
    get_data_service_gateway,
    reset_data_service_gateways,
)


@pytest.fixture(autouse=True)
def _isolate_runtime_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def test_derivation_seeds_only_history_and_required_session_configuration(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive.sqlite3")
    source = gateway.catalog.get_session("s_forest001")
    assert source is not None

    (
        SessionProfileRecord.update(description="仅属于源会话的描述")
        .where(SessionProfileRecord.session == source.id)
        .execute()
    )
    (
        SessionMessageRecord.update(
            mode=models.TURN_MODE_GM,
            tool_call_id="call-branch-copy",
            tool_calls_json='[{"id":"call-branch-copy"}]',
            metadata_json='{"kind":"copy-proof"}',
            version=7,
            created_at="2024-01-02 03:04:05",
            updated_at="2024-02-03 04:05:06",
        )
        .where(
            (SessionMessageRecord.session == source.id)
            & (SessionMessageRecord.turn_id == 3)
            & (SessionMessageRecord.seq_in_turn == 2)
        )
        .execute()
    )
    SessionBackupMessageRecord.create(
        session=source.id,
        role=models.MESSAGE_ROLE_ASSISTANT,
        content="只存在于源冷备，不应复制",
        turn_id=99,
        seq_in_turn=1,
    )
    source = gateway.catalog.get_session(source.id)
    assert source is not None
    assert source.description == "仅属于源会话的描述"

    source = gateway.catalog.set_session_main_llm_provider_key(
        source.id,
        "main_provider_test",
    )
    assert source is not None
    override = gateway.rp_modules.set_session_override(
        source.id,
        "dice",
        enabled=False,
        config={"reason": "branch test"},
    )
    assert override is not None
    source_tables = gateway.status.list_tables(source.id)
    source_normal = next(
        table for table in source_tables if table.status_kind == models.STATUS_KIND_NORMAL
    )
    gateway.status.set_key_value(source_normal.id, "已发现线索", "仅存在于源会话")
    (
        SessionMessageRecord.update(
            summary_processed=True,
            summary_batch_id=99,
            story_memory_processed=True,
        )
        .where(
            (SessionMessageRecord.session == source.id)
            & (SessionMessageRecord.turn_id <= 3)
        )
        .execute()
    )

    job = gateway.session_derivations.create_job(
        source.id,
        3,
        requested_title="铜扣之前",
    )
    running = gateway.session_derivations.start_job(job.id)
    assert running.status == models.SESSION_DERIVATION_JOB_STATUS_RUNNING
    seeded = gateway.session_derivations.seed_target_session(job.id)
    target = seeded.session

    assert target.lifecycle == models.SESSION_LIFECYCLE_PROVISIONING
    assert target.title == "铜扣之前"
    assert target.description == ""
    assert target.player_character_id == source.player_character_id
    assert target.player_character_snapshot_json == source.player_character_snapshot_json
    assert target.story_opening_id == source.story_opening_id
    assert target.main_llm_provider_key == "main_provider_test"
    assert target.id not in {
        row.id
        for row in gateway.catalog.list_sessions(source.workspace_id, source.story_id) or []
    }

    messages = gateway.messages.list(target.id)
    backup = gateway.backup.messages.list(target.id)
    source_messages = [
        row for row in gateway.messages.list(source.id) if row.turn_id <= 3
    ]
    assert seeded.copied_message_count == 6
    assert [row.turn_id for row in messages] == [1, 1, 2, 2, 3, 3]
    assert max(row.turn_id for row in gateway.messages.list(source.id)) > 3
    def copied_fields(row):  # noqa: ANN001, ANN202
        return (
            row.role,
            row.content,
            row.mode,
            row.turn_id,
            row.seq_in_turn,
            row.tool_call_id,
            row.tool_calls_json,
            row.metadata_json,
            row.created_at,
            row.updated_at,
        )
    assert [copied_fields(row) for row in messages] == [
        copied_fields(row) for row in source_messages
    ]
    assert [copied_fields(row) for row in backup] == [
        copied_fields(row) for row in source_messages
    ]
    assert all(row.content != "只存在于源冷备，不应复制" for row in backup)
    assert all(row.session_id == target.id and row.version == 1 for row in messages)
    assert all(row.session_id == target.id and row.version == 1 for row in backup)
    assert all(not row.summary_processed for row in messages)
    assert all(row.summary_batch_id is None for row in messages)
    assert all(not row.story_memory_processed for row in messages)

    target_overrides = gateway.rp_modules.list_session_overrides(target.id)
    assert target_overrides is not None
    assert [(item.module_name, item.enabled, item.config) for item in target_overrides] == [
        ("dice", False, {"reason": "branch test"})
    ]
    target_normal = next(
        table
        for table in gateway.status.list_tables(target.id)
        if table.status_kind == models.STATUS_KIND_NORMAL
    )
    assert target_normal.document != gateway.status.get_table_by_id(source_normal.id).document
    assert SessionStoryMemoryRecord.select().where(
        SessionStoryMemoryRecord.session == target.id
    ).count() == 0
    assert SessionNarrativeOutcomeRecord.select().where(
        SessionNarrativeOutcomeRecord.session == target.id
    ).count() == 0

    ready_job = gateway.session_derivations.complete_job(job.id)
    ready_target = gateway.catalog.get_session(target.id)
    assert ready_job.status == models.SESSION_DERIVATION_JOB_STATUS_READY
    assert ready_job.stage == "ready"
    assert ready_target is not None
    assert ready_target.lifecycle == models.SESSION_LIFECYCLE_READY
    assert ready_target.id in {
        row.id
        for row in gateway.catalog.list_sessions(source.workspace_id, source.story_id) or []
    }


def test_derivation_failure_cleans_provisioning_target_and_retains_job(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-failure.sqlite3")
    service = gateway.session_derivations
    job = service.create_job("s_forest001", 2)
    service.start_job(job.id)
    seeded = service.seed_target_session(job.id)
    target_id = seeded.session.id
    runtime_dir = gateway.catalog.get_session_runtime_dir(target_id)
    marker = runtime_dir / "cleanup.marker"
    marker.write_text("target", encoding="utf-8")

    deleted = gateway.session_deletion.delete_provisioning_target(job.id, target_id)

    failed = service.fail_job(
        job.id,
        error_code="STORY_MEMORY_FAILED",
        error_message="mock extraction failure",
    )

    assert gateway.catalog.get_session(target_id) is None
    assert deleted.runtime_cleanup == models.SESSION_RUNTIME_CLEANUP_DELETED
    assert not runtime_dir.exists()
    assert failed.target_session_id == target_id
    assert failed.status == models.SESSION_DERIVATION_JOB_STATUS_FAILED
    assert failed.stage == "failed"
    assert failed.error_code == "STORY_MEMORY_FAILED"
    assert failed.finished_at
    assert service.get_job(job.id) == failed


def test_derivation_rejects_missing_or_incomplete_branch_turn(tmp_path: Path) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-invalid.sqlite3")
    service = gateway.session_derivations

    with pytest.raises(SessionDerivationDataError) as missing:
        service.create_job("s_forest001", 99)
    assert missing.value.code == "DERIVATION_TURN_NOT_FOUND"

    gateway.messages.append(
        "s_forest001",
        models.MESSAGE_ROLE_USER,
        "尚未得到回复",
        turn_id=9,
        seq_in_turn=1,
    )
    with pytest.raises(SessionDerivationDataError) as incomplete:
        service.create_job("s_forest001", 9)
    assert incomplete.value.code == "DERIVATION_TURN_INCOMPLETE"


def test_derivation_accepts_assistant_ended_turn_with_deleted_sequence_gap(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-gap.sqlite3")
    source_user = (
        SessionMessageRecord.select()
        .where(
            (SessionMessageRecord.session == "s_forest001")
            & (SessionMessageRecord.turn_id == 2)
            & (SessionMessageRecord.seq_in_turn == 1)
        )
        .get()
    )
    assert gateway.messages.delete(source_user.id) is True

    service = gateway.session_derivations
    job = service.create_job("s_forest001", 2)
    service.start_job(job.id)
    seeded = service.seed_target_session(job.id)

    boundary_rows = [
        row for row in gateway.messages.list(seeded.session.id) if row.turn_id == 2
    ]
    assert [(row.role, row.seq_in_turn) for row in boundary_rows] == [
        (models.MESSAGE_ROLE_ASSISTANT, 2)
    ]


def test_derivation_seed_rolls_back_target_and_copied_rows_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-rollback.sqlite3")
    service = gateway.session_derivations
    job = service.create_job("s_forest001", 2)
    service.start_job(job.id)
    original_session_ids = {row.id for row in service._sessions.list()}
    original_copy = service._copy_messages

    def fail_after_partial_copy(messages, target_session_id):  # noqa: ANN001
        original_copy(messages[:1], target_session_id)
        raise RuntimeError("copy interrupted")

    monkeypatch.setattr(service, "_copy_messages", fail_after_partial_copy)

    with pytest.raises(RuntimeError, match="copy interrupted"):
        service.seed_target_session(job.id)

    persisted_job = service.get_job(job.id)
    assert persisted_job is not None
    assert persisted_job.target_session_id is None
    assert {row.id for row in service._sessions.list()} == original_session_ids
    assert SessionMessageRecord.select().where(
        ~SessionMessageRecord.session.in_(original_session_ids)
    ).count() == 0


def test_derivation_interrupts_running_jobs_and_cleans_targets(tmp_path: Path) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-interrupt.sqlite3")
    service = gateway.session_derivations
    job = service.create_job("s_forest001", 1)
    service.start_job(job.id)
    target_id = service.seed_target_session(job.id).session.id

    gateway.session_deletion.delete_provisioning_target(job.id, target_id)
    interrupted = service.interrupt_job(job.id)

    assert interrupted.id == job.id
    assert interrupted.status == models.SESSION_DERIVATION_JOB_STATUS_INTERRUPTED
    assert gateway.catalog.get_session(target_id) is None


def test_source_deletion_is_rejected_while_derivation_is_active(tmp_path: Path) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-delete-conflict.sqlite3")
    job = gateway.session_derivations.create_job("s_forest001", 1)

    with pytest.raises(SessionDerivationDataError) as busy:
        gateway.session_deletion.delete("s_forest001")
    assert busy.value.code == "DERIVATION_SOURCE_BUSY"

    gateway.session_derivations.fail_job(
        job.id,
        error_code="TEST_CANCELLED",
        error_message="test cleanup",
    )
    assert gateway.session_deletion.delete("s_forest001") is not None


def test_regular_deletion_rejects_active_target_and_orphan_provisioning(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-target-delete.sqlite3")
    job = gateway.session_derivations.create_job("s_forest001", 1)
    gateway.session_derivations.start_job(job.id)
    target_id = gateway.session_derivations.seed_target_session(job.id).session.id

    with pytest.raises(SessionDerivationDataError) as active_target:
        gateway.session_deletion.delete(target_id)
    assert active_target.value.code == "DERIVATION_TARGET_BUSY"

    gateway.session_deletion.delete_provisioning_target(job.id, target_id)
    gateway.session_derivations.interrupt_job(job.id)

    orphan = gateway.session_derivations._sessions.create(
        "demo_workspace",
        1,
        lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
    )
    with pytest.raises(SessionDerivationDataError) as provisioning:
        gateway.session_deletion.delete(orphan.id)
    assert provisioning.value.code == "DERIVATION_TARGET_PROVISIONING"


def test_privileged_target_deletion_validates_job_ownership(tmp_path: Path) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-target-owner.sqlite3")
    job = gateway.session_derivations.create_job("s_forest001", 1)
    gateway.session_derivations.start_job(job.id)
    target_id = gateway.session_derivations.seed_target_session(job.id).session.id

    with pytest.raises(SessionDerivationDataError) as mismatch:
        gateway.session_deletion.delete_provisioning_target(job.id, "wrong_target")
    assert mismatch.value.code == "DERIVATION_TARGET_OWNERSHIP_MISMATCH"
    assert gateway.catalog.get_session(target_id) is not None


def test_job_claim_is_a_single_conditional_transition(tmp_path: Path) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-claim.sqlite3")
    service = gateway.session_derivations
    job = service.create_job("s_forest001", 1)

    running = service.start_job(job.id)
    assert running.status == models.SESSION_DERIVATION_JOB_STATUS_RUNNING
    with pytest.raises(SessionDerivationDataError) as second_claim:
        service.start_job(job.id)
    assert second_claim.value.code == "DERIVATION_INVALID_STATE"


def test_conditional_deletes_cannot_remove_published_or_actively_owned_sessions(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "derive-delete-condition.sqlite3")
    service = gateway.session_derivations
    job = service.create_job("s_forest001", 1)

    assert gateway.session_deletion._sessions.delete_ready_without_active_derivation(
        "s_forest001"
    ) is False
    assert gateway.catalog.get_session("s_forest001") is not None

    service.start_job(job.id)
    target_id = service.seed_target_session(job.id).session.id
    service.complete_job(job.id)

    assert gateway.session_deletion._sessions.delete_provisioning_for_derivation(
        target_id,
        job.id,
    ) is False
    target = gateway.catalog.get_session(target_id)
    assert target is not None
    assert target.lifecycle == models.SESSION_LIFECYCLE_READY
