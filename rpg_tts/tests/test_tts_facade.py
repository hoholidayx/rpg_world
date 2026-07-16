from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm_client.types import LLMSpeechAudio, LLMSpeechProfile
from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway
from rpg_tts.facade import TTSFacade
from rpg_tts.text import normalize_spoken_text, split_spoken_text


class _FakeSpeechClient:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def get_speech_profile(self, biz_key: str) -> LLMSpeechProfile:
        return LLMSpeechProfile(
            biz_key=biz_key,
            provider_key="openai-tts",
            model="tts-model",
            voice="alloy",
            response_format="mp3",
            speed=1.0,
            cache_revision="v1",
            config_fingerprint="c" * 64,
        )

    async def speech(self, *, biz_key: str, provider_key: str | None, text: str) -> LLMSpeechAudio:
        del biz_key, provider_key
        self.texts.append(text)
        return LLMSpeechAudio(
            content=b"ID3" + text.encode("utf-8"),
            media_type="audio/mpeg",
            config_fingerprint="c" * 64,
        )


def test_normalize_and_split_spoken_text() -> None:
    content = (
        '<rp-narration>风穿过树林。</rp-narration>'
        '<rp-character name="Alice">我们走吧！</rp-character>'
    )
    spoken = normalize_spoken_text(content)

    assert spoken == "风穿过树林。\n我们走吧！"
    assert split_spoken_text(spoken, 100) == (spoken,)
    assert all(len(part) <= 100 for part in split_spoken_text("很长。" * 80, 100))


@pytest.mark.asyncio
async def test_facade_generates_persistent_parts_and_reuses_cache(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "tts.sqlite3")
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(tmp_path / "workspace"),),
    )
    session = gateway.catalog.create_session("demo_workspace", 1, title="TTS")
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "<rp-narration>风起。</rp-narration>",
        turn_id=1,
        seq_in_turn=1,
    )
    client = _FakeSpeechClient()
    facade = TTSFacade(
        data=gateway.tts,
        llm_manager=SimpleNamespace(client=client),  # type: ignore[arg-type]
    )

    queued = await facade.create_job(session.id, message.id)
    assert queued.status == models.TTS_JOB_STATUS_QUEUED
    claimed = gateway.tts.claim_next_job()
    assert claimed is not None
    completed = await facade.execute_job(claimed.id)

    assert completed is not None
    assert completed.status == models.TTS_JOB_STATUS_SUCCEEDED
    parts = gateway.tts.list_parts(session.id, completed.id)
    assert len(parts) == 1
    assert facade.resolve_audio_part(session.id, completed.id, 0).read_bytes().startswith(b"ID3")

    orphan = tmp_path / "workspace" / "assets" / "audio" / f"{'f' * 64}.mp3"
    orphan.write_bytes(b"ID3orphan")
    reconciled = await facade.reconcile_workspace("demo_workspace")
    assert reconciled.removed_files == 1
    assert not orphan.exists()

    second_session = gateway.catalog.create_session("demo_workspace", 1, title="TTS cache")
    second_message = gateway.messages.append(
        second_session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        message.content,
        turn_id=1,
        seq_in_turn=1,
    )
    cached = await facade.create_job(second_session.id, second_message.id)
    assert cached.status == models.TTS_JOB_STATUS_SUCCEEDED
    assert len(client.texts) == 1
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
    )

    assert gateway.messages.delete_for_session(session.id, message.id)
    assert gateway.tts.get_job(session.id, job.id) is None
    gateway.close()
