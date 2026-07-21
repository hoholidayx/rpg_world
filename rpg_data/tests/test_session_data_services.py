from __future__ import annotations

import json

import pytest

from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway


@pytest.fixture
def gateway() -> DataServiceGateway:
    service_gateway = DataServiceGateway(":memory:")
    service_gateway.initialize()
    try:
        yield service_gateway
    finally:
        service_gateway.close()


def test_session_role_data_service_reads_mounts_and_persists_explicit_profile(
    gateway: DataServiceGateway,
) -> None:
    session = gateway.catalog.create_session("demo_workspace", 1, title="role data")
    assert session is not None
    mounts = gateway.sessions.list_character_mounts(session.id)
    openings = gateway.sessions.list_story_openings(session.id)
    assert mounts and openings
    mount = mounts[0]
    snapshot_json = json.dumps(
        {
            "characterId": mount.character_id,
            "mountId": mount.mount_id,
            "storyId": mount.story_id,
            "name": mount.name,
        }
    )

    updated = gateway.sessions.update_player_character_and_opening(
        session.id,
        player_character_id=mount.character_id,
        player_character_snapshot_json=snapshot_json,
        story_opening_id=openings[0].id,
    )

    assert updated is not None
    assert updated.player_character_id == mount.character_id
    assert updated.player_character_snapshot_json == snapshot_json
    assert updated.story_opening_id == openings[0].id


def test_session_data_service_lists_only_ready_sessions_for_story(
    gateway: DataServiceGateway,
) -> None:
    ready = gateway.sessions.create_session(
        "demo_workspace",
        1,
        title="ready through session data",
    )
    provisioning = gateway.sessions.create_session(
        "demo_workspace",
        1,
        title="hidden provisioning",
        lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
    )
    assert ready is not None and provisioning is not None

    sessions = gateway.sessions.list_sessions("demo_workspace", 1)

    assert sessions is not None
    assert ready.id in {session.id for session in sessions}
    assert provisioning.id not in {session.id for session in sessions}
    assert gateway.sessions.list_sessions("missing", 1) is None


def test_session_role_data_transaction_rolls_back_explicit_update(
    gateway: DataServiceGateway,
) -> None:
    session = gateway.catalog.create_session("demo_workspace", 1, title="rollback")
    assert session is not None
    mount = gateway.sessions.list_character_mounts(session.id)[0]

    with pytest.raises(RuntimeError, match="rollback"):
        with gateway.sessions.transaction():
            gateway.sessions.update_player_character(
                session.id,
                player_character_id=mount.character_id,
                player_character_snapshot_json='{"prepared":true}',
            )
            raise RuntimeError("rollback")

    stored = gateway.catalog.get_session(session.id)
    assert stored is not None
    assert stored.player_character_id is None
    assert stored.player_character_snapshot_json == "{}"


def test_derivation_data_service_crud_and_explicit_message_copy(
    gateway: DataServiceGateway,
) -> None:
    target = gateway.catalog.create_session("demo_workspace", 1, title="target")
    assert target is not None
    data = gateway.sessions
    source_messages = data.list_messages_through_turn("s_forest001", 1)
    assert source_messages
    job = data.create_derivation_job("s_forest001", 1, requested_title="branch")

    running = data.update_derivation_job_if_status(
        job.id,
        models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
        models.SessionDerivationJobUpdate(
            status=models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
            stage="snapshotting",
            mark_started=True,
        ),
    )
    copied = data.copy_messages(target.id, source_messages)

    assert running is not None
    assert copied == len(source_messages)
    assert data.get_derivation_job(job.id) == running
    assert data.list_derivation_jobs(models.SESSION_DERIVATION_JOB_STATUS_RUNNING) == [running]
    with pytest.raises(ValueError, match="Unsupported derivation status"):
        data.list_derivation_jobs("unknown")
    assert data.update_derivation_job_if_status(
        job.id,
        models.SESSION_DERIVATION_JOB_STATUS_QUEUED,
        models.SessionDerivationJobUpdate(stage="copying"),
    ) is None
    assert len(gateway.messages.list(target.id)) == copied
    assert len(gateway.backup.messages.list(target.id)) == copied
    assert all(not row.summary_processed for row in gateway.messages.list(target.id))


def test_session_deletion_data_service_honors_caller_selected_predicates(
    gateway: DataServiceGateway,
) -> None:
    ready = gateway.catalog.create_session("demo_workspace", 1, title="ready")
    source = gateway.catalog.create_session("demo_workspace", 1, title="source")
    target = gateway.catalog.create_session(
        "demo_workspace",
        1,
        title="provisioning",
        lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
    )
    assert ready is not None and source is not None and target is not None
    job = gateway.sessions.create_derivation_job(source.id, 1)
    gateway.sessions.update_derivation_job(
        job.id,
        models.SessionDerivationJobUpdate(
            target_session_id=target.id,
            status=models.SESSION_DERIVATION_JOB_STATUS_RUNNING,
            stage="copying",
        ),
    )

    assert gateway.sessions.delete_ready_without_active_derivation(
        source.id
    ) is False
    assert gateway.sessions.delete_ready_without_active_derivation(
        ready.id
    ) is True
    assert gateway.sessions.delete_provisioning_for_derivation(
        target.id,
        job.id,
    ) is True
    assert gateway.catalog.get_session(ready.id) is None
    assert gateway.catalog.get_session(target.id) is None
    assert gateway.catalog.get_session(source.id) is not None


def test_status_data_service_applies_exact_reset_plan(
    gateway: DataServiceGateway,
) -> None:
    session = gateway.catalog.create_session("demo_workspace", 1, title="status data")
    assert session is not None
    mounts = gateway.status.list_story_mounts(session.workspace_id, session.story_id)
    copied = gateway.status.copy_story_mounts_to_session(
        session.id,
        (mount.id for mount in mounts),
    )
    native = gateway.status.create_table(
        session.id,
        "native",
        document=models.StatusTableDocument.from_rows(
            rows=[models.StatusTableRow("key", "value")]
        ),
    )
    template_ids = tuple(
        table.id
        for table in copied
        if table.origin == models.STATUS_ORIGIN_TEMPLATE_COPY
    )

    result = gateway.status.apply_session_reset_plan(
        session.id,
        models.SessionStatusResetPlan(
            delete_table_ids=template_ids,
            document_writes=(
                models.SessionStatusDocumentWrite(
                    table_id=native.id,
                    document=native.document.with_cleared_values(),
                ),
            ),
            story_mount_ids=tuple(mount.id for mount in mounts),
        ),
    )

    assert result.template_tables_cleared == len(template_ids)
    assert result.template_tables_initialized == len(mounts)
    assert result.native_tables_reset == 1
    assert gateway.status.get_table_by_id(native.id).document.rows[0].value == ""
