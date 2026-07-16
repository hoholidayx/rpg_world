from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from llm_client.types import LLMSpeechAudio, LLMSpeechProfile
from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway
from rpg_tts.facade import TTSFacade
from tts_service.main import TTSRuntime, app, set_runtime_for_tests
from tts_service.worker import TTSJobWorker


class _SpeechClient:
    async def get_speech_profile(self, biz_key: str) -> LLMSpeechProfile:
        return LLMSpeechProfile(
            biz_key=biz_key,
            provider_key="tts",
            model="model",
            voice="alloy",
            response_format="mp3",
            speed=1.0,
            cache_revision="v1",
            config_fingerprint="d" * 64,
        )

    async def speech(self, *, biz_key: str, provider_key: str | None, text: str) -> LLMSpeechAudio:
        del biz_key, provider_key
        return LLMSpeechAudio(b"ID3" + text.encode(), "audio/mpeg", "d" * 64)


def test_tts_service_job_and_audio_contract(tmp_path) -> None:
    gateway = DataServiceGateway(tmp_path / "service.sqlite3")
    gateway.database.execute_sql(
        "UPDATE rpg_workspaces SET root_path = ? WHERE id = 'demo_workspace'",
        (str(tmp_path / "workspace"),),
    )
    session = gateway.catalog.create_session("demo_workspace", 1, title="speech")
    message = gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_ASSISTANT,
        "<rp-narration>hello</rp-narration>",
        turn_id=1,
        seq_in_turn=1,
    )
    facade = TTSFacade(
        data=gateway.tts,
        llm_manager=SimpleNamespace(client=_SpeechClient()),  # type: ignore[arg-type]
    )
    runtime = TTSRuntime(
        gateway=gateway,
        facade=facade,
        worker=TTSJobWorker(data=gateway.tts, facade=facade),
    )
    set_runtime_for_tests(runtime)
    try:
        with TestClient(app) as client:
            created = client.post(
                f"/tts/v1/sessions/{session.id}/messages/{message.id}/jobs"
            )
            assert created.status_code == 200
            job_id = created.json()["jobId"]
            deadline = time.monotonic() + 2
            payload = created.json()
            while payload["status"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(0.02)
                payload = client.get(
                    f"/tts/v1/sessions/{session.id}/jobs/{job_id}"
                ).json()
            assert payload["status"] == "succeeded"
            assert payload["partCount"] == 1

            audio = client.get(
                f"/tts/v1/sessions/{session.id}/jobs/{job_id}/parts/0/audio",
                headers={"Range": "bytes=0-2"},
            )
            assert audio.status_code == 206
            assert audio.content == b"ID3"
            assert audio.headers["content-type"].startswith("audio/mpeg")
    finally:
        set_runtime_for_tests(None)
        gateway.close()
