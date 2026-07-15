"""Main-Agent LLM selection endpoints for the Play client."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Literal, TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agent_service.client import AgentClientError, AgentServiceUnavailable
from play_api.backends import get_agent_backend
from play_api.routers._locator import resolve_session_or_404

router = APIRouter(tags=["play-main-llm"])
T = TypeVar("T")


class PlayMainLLMProviderOption(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider_key: str = Field(alias="providerKey")
    backend: str
    model: str
    context_window: int | None = Field(default=None, alias="contextWindow")


class PlayMainLLMInvalidOverride(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: Literal["story", "session"]
    provider_key: str = Field(alias="providerKey")


class PlayMainLLMProviderCatalog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config_default_provider_key: str = Field(alias="configDefaultProviderKey")
    options: list[PlayMainLLMProviderOption] = Field(default_factory=list)


class PlayMainLLMSelection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config_default_provider_key: str = Field(alias="configDefaultProviderKey")
    story_provider_key: str | None = Field(default=None, alias="storyProviderKey")
    session_provider_key: str | None = Field(default=None, alias="sessionProviderKey")
    effective_provider_key: str = Field(alias="effectiveProviderKey")
    effective_source: Literal["config", "story", "session"] = Field(alias="effectiveSource")
    effective: PlayMainLLMProviderOption
    invalid_overrides: list[PlayMainLLMInvalidOverride] = Field(
        default_factory=list,
        alias="invalidOverrides",
    )


class PlayMainLLMUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    provider_key: str | None = Field(alias="providerKey")


async def _agent_call(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except AgentServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentClientError as exc:
        detail: str | dict[str, str] = str(exc)
        if exc.error_code:
            detail = {"errorCode": exc.error_code, "message": str(exc)}
        raise HTTPException(
            status_code=exc.status_code or 502,
            detail=detail,
        ) from exc


@router.get("/llm/main-agent/options", response_model=PlayMainLLMProviderCatalog)
async def get_main_llm_options() -> PlayMainLLMProviderCatalog:
    payload = await _agent_call(get_agent_backend().get_main_llm_options())
    return PlayMainLLMProviderCatalog.model_validate(payload)


@router.get(
    "/workspaces/{workspace_id}/stories/{story_id}/main-llm",
    response_model=PlayMainLLMSelection,
)
async def get_story_main_llm(
    workspace_id: str,
    story_id: int,
) -> PlayMainLLMSelection:
    payload = await _agent_call(
        get_agent_backend().get_story_main_llm(workspace_id, story_id)
    )
    return PlayMainLLMSelection.model_validate(payload)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/main-llm",
    response_model=PlayMainLLMSelection,
)
async def set_story_main_llm(
    workspace_id: str,
    story_id: int,
    body: PlayMainLLMUpdateRequest,
) -> PlayMainLLMSelection:
    payload = await _agent_call(
        get_agent_backend().set_story_main_llm(
            workspace_id,
            story_id,
            body.provider_key,
        )
    )
    return PlayMainLLMSelection.model_validate(payload)


@router.get(
    "/sessions/{session_id}/main-llm",
    response_model=PlayMainLLMSelection,
)
async def get_session_main_llm(session_id: str) -> PlayMainLLMSelection:
    session = await resolve_session_or_404(session_id)
    payload = await _agent_call(
        get_agent_backend().get_session_main_llm(str(session["id"]))
    )
    return PlayMainLLMSelection.model_validate(payload)


@router.patch(
    "/sessions/{session_id}/main-llm",
    response_model=PlayMainLLMSelection,
)
async def set_session_main_llm(
    session_id: str,
    body: PlayMainLLMUpdateRequest,
) -> PlayMainLLMSelection:
    session = await resolve_session_or_404(session_id)
    payload = await _agent_call(
        get_agent_backend().set_session_main_llm(
            str(session["id"]),
            body.provider_key,
        )
    )
    return PlayMainLLMSelection.model_validate(payload)
