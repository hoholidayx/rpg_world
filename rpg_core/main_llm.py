"""Main-agent LLM selection across config, story, and session scopes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loguru import logger

from llm_client.keys import AGENT_MAIN_BIZ_KEY
from llm_client.manager import LLMClientManager
from llm_client.types import LLMProviderOption
from rpg_data import models
from rpg_data.services import DataServiceGateway, get_data_service_gateway

MainLLMSelectionSource = Literal["config", "story", "session"]
MainLLMOverrideSource = Literal["story", "session"]


class InvalidMainLLMProviderKey(ValueError):
    """Raised when a requested provider is outside the main-agent option pool."""


@dataclass(frozen=True)
class InvalidMainLLMOverride:
    source: MainLLMOverrideSource
    provider_key: str


@dataclass(frozen=True)
class MainLLMProviderCatalog:
    config_default_provider_key: str
    options: tuple[LLMProviderOption, ...]


@dataclass(frozen=True)
class MainLLMSelection:
    config_default_provider_key: str
    story_provider_key: str | None
    session_provider_key: str | None
    effective_provider_key: str
    effective_source: MainLLMSelectionSource
    effective: LLMProviderOption
    invalid_overrides: tuple[InvalidMainLLMOverride, ...] = ()


class MainLLMSelectionService:
    """Resolve and persist the main Agent's provider selection."""

    def __init__(self, gateway: DataServiceGateway | None = None) -> None:
        self._gateway = gateway or get_data_service_gateway()

    async def get_provider_catalog(self) -> MainLLMProviderCatalog:
        remote = await LLMClientManager.get().get_catalog(AGENT_MAIN_BIZ_KEY)
        return MainLLMProviderCatalog(
            config_default_provider_key=remote.default_provider_key,
            options=remote.options,
        )

    async def resolve_story(
        self,
        workspace_id: str,
        story_id: int,
    ) -> MainLLMSelection | None:
        story = self._gateway.catalog.get_story(workspace_id, story_id)
        if story is None:
            return None
        return await self._resolve(story=story, session=None)

    async def resolve_session(self, session_id: str) -> MainLLMSelection | None:
        session = self._gateway.catalog.get_session(session_id)
        if session is None:
            return None
        story = self._gateway.catalog.get_session_story(session_id)
        if story is None:
            return None
        return await self._resolve(story=story, session=session)

    async def set_story_provider_key(
        self,
        workspace_id: str,
        story_id: int,
        provider_key: str | None,
    ) -> MainLLMSelection | None:
        story = self._gateway.catalog.get_story(workspace_id, story_id)
        if story is None:
            return None
        normalized = await self._validate_provider_key(provider_key)
        updated = self._gateway.catalog.set_story_main_llm_provider_key(
            workspace_id,
            story_id,
            normalized,
        )
        if updated is None:
            return None
        return await self._resolve(story=updated, session=None)

    async def set_session_provider_key(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> MainLLMSelection | None:
        session = self._gateway.catalog.get_session(session_id)
        if session is None:
            return None
        normalized = await self._validate_provider_key(provider_key)
        updated = self._gateway.catalog.set_session_main_llm_provider_key(
            session_id,
            normalized,
        )
        if updated is None:
            return None
        story = self._gateway.catalog.get_session_story(session_id)
        if story is None:
            return None
        return await self._resolve(story=story, session=updated)

    async def _validate_provider_key(self, provider_key: str | None) -> str | None:
        if provider_key is None:
            return None
        normalized = str(provider_key).strip()
        if not normalized:
            raise InvalidMainLLMProviderKey("provider_key must be null or a non-empty string")
        allowed = {
            option.provider_key
            for option in (await self.get_provider_catalog()).options
        }
        if normalized not in allowed:
            raise InvalidMainLLMProviderKey(
                f"main Agent provider_key {normalized!r} is not selectable; "
                f"allowed={sorted(allowed)}"
            )
        return normalized

    async def _resolve(
        self,
        *,
        story: models.Story,
        session: models.Session | None,
    ) -> MainLLMSelection:
        catalog = await self.get_provider_catalog()
        options = {option.provider_key: option for option in catalog.options}
        invalid: list[InvalidMainLLMOverride] = []

        story_key = _optional_key(story.main_llm_provider_key)
        session_key = _optional_key(session.main_llm_provider_key) if session is not None else None

        effective_key = catalog.config_default_provider_key
        effective_source: MainLLMSelectionSource = "config"
        if story_key:
            if story_key in options:
                effective_key = story_key
                effective_source = "story"
            else:
                invalid.append(InvalidMainLLMOverride("story", story_key))
        if session_key:
            if session_key in options:
                effective_key = session_key
                effective_source = "session"
            else:
                invalid.append(InvalidMainLLMOverride("session", session_key))

        if invalid:
            logger.warning(
                "[MainLLMSelection] ignored invalid overrides: story_id={}, session_id={}, overrides={}",
                story.id,
                session.id if session is not None else None,
                [(item.source, item.provider_key) for item in invalid],
            )

        return MainLLMSelection(
            config_default_provider_key=catalog.config_default_provider_key,
            story_provider_key=story_key,
            session_provider_key=session_key,
            effective_provider_key=effective_key,
            effective_source=effective_source,
            effective=options[effective_key],
            invalid_overrides=tuple(invalid),
        )


def _optional_key(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
