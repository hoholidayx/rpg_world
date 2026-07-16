from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from play_api import tts_client
from play_api.main import app
from rpg_data.services import reset_data_service_gateways
from tts_service.schemas import TTSAudioPartResponse, TTSJobResponse


def _job() -> TTSJobResponse:
    return TTSJobResponse(
        jobId="job1",
        sessionId="s_forest001",
        messageId=2,
        status="succeeded",
        partCount=1,
        parts=[TTSAudioPartResponse(partIndex=0, audioUrl="/internal")],
        errorCode="",
        errorMessage="",
        createdAt="now",
        updatedAt="now",
    )


class _FakeTTSClient:
    async def create_job(self, session_id: str, message_id: int) -> TTSJobResponse:
        assert (session_id, message_id) == ("s_forest001", 2)
        return _job()

    async def get_job(self, session_id: str, job_id: str) -> TTSJobResponse:
        assert (session_id, job_id) == ("s_forest001", "job1")
        return _job()

    async def retry_job(self, session_id: str, job_id: str) -> TTSJobResponse:
        return await self.get_job(session_id, job_id)

    async def get_audio(self, session_id: str, job_id: str, part_index: int, *, range_header=None):  # noqa: ANN001, ANN201
        assert (session_id, job_id, part_index, range_header) == (
            "s_forest001",
            "job1",
            0,
            "bytes=0-2",
        )
        return httpx.Response(
            206,
            content=b"ID3",
            headers={"content-type": "audio/mpeg", "content-range": "bytes 0-2/8"},
        )

    async def aclose(self) -> None:
        return None


def test_play_api_tts_proxy_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    tts_client._client = _FakeTTSClient()  # type: ignore[assignment]
    try:
        with TestClient(app) as client:
            created = client.post("/play-api/v1/sessions/s_forest001/tts/messages/2/jobs")
            assert created.status_code == 200
            assert created.json()["parts"] == [
                {
                    "partIndex": 0,
                    "audioUrl": "/sessions/s_forest001/tts/jobs/job1/parts/0/audio",
                }
            ]

            audio = client.get(
                "/play-api/v1/sessions/s_forest001/tts/jobs/job1/parts/0/audio",
                headers={"Range": "bytes=0-2"},
            )
            assert audio.status_code == 206
            assert audio.content == b"ID3"
            assert audio.headers["content-range"] == "bytes 0-2/8"
    finally:
        tts_client._client = None
        reset_data_service_gateways()
