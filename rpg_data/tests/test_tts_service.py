from __future__ import annotations

from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway


def test_tts_source_read_model_is_policy_neutral(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "tts-source.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="TTS source")
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "player text",
        turn_id=1,
        seq_in_turn=1,
    )

    source = gateway.tts.get_message_source(session.id, message.id)

    assert source.role == models.MESSAGE_ROLE_USER
    assert source.turn_id == 1
    assert source.seq_in_turn == 1
    gateway.close()


def test_tts_job_cascades_when_source_message_is_deleted(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "tts-cascade.sqlite3")
    session = gateway.catalog.create_session("demo_workspace", 1, title="TTS cascade")
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "reply",
        turn_id=1,
        seq_in_turn=1,
    )
    job = gateway.tts.create_or_get_job(
        session_id=session.id,
        message_id=message.id,
        source_fingerprint="a" * 64,
        config_fingerprint="b" * 64,
        normalization_revision="v1",
        status=models.TTS_JOB_STATUS_QUEUED,
        cache_entry_id=None,
    )

    assert gateway.messages.delete_for_session(session.id, message.id)
    assert gateway.tts.get_job(session.id, job.id) is None
    gateway.close()
