from __future__ import annotations

import httpx
import pytest

from agent_service.main import app as agent_app
from dream_service.main import app as dream_app
from llm_service.main import app as llm_app
from media_service.main import app as media_app
from play_api.main import app as play_app
from tts_service.main import app as tts_app


@pytest.mark.asyncio
async def test_play_api_allows_lan_origin_without_credentials() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=play_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/play-api/v1/not-found",
            headers={"Origin": "http://192.168.1.25:3000"},
        )

    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "service_app",
    [
        agent_app,
        media_app,
        tts_app,
        dream_app,
        llm_app,
    ],
)
async def test_internal_services_do_not_emit_browser_cors_headers(
    service_app,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=service_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/__cors_probe__",
            headers={"Origin": "http://192.168.1.25:3000"},
        )

    assert response.status_code == 404
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers
