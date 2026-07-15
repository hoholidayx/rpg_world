"""Main model selection and provider cache for ``RPGGameAgent``."""

from __future__ import annotations

from loguru import logger

from llm_client.keys import AGENT_MAIN_BIZ_KEY
from llm_client.manager import LLMClientManager
from llm_client.types import LLMProvider
from rpg_core.main_llm import MainLLMSelection, MainLLMSelectionService

_TAG = "[MainModelRuntime]"


class MainModelRuntime:
    """Resolve the per-turn model snapshot and reuse compatible providers."""

    def __init__(
        self,
        *,
        selection_service: MainLLMSelectionService,
        initial_model: str | None = None,
    ) -> None:
        self._selection_service = selection_service
        self._provider: LLMProvider | None = None
        self._selection: MainLLMSelection | None = None
        self._model = initial_model

    @property
    def model(self) -> str | None:
        return self._model

    @property
    def selection(self) -> MainLLMSelection | None:
        return self._selection

    def resolve(self, session_id: str) -> MainLLMSelection:
        selection = self._selection_service.resolve_session(session_id)
        if selection is None:
            raise FileNotFoundError(
                f"Main LLM selection context not found for session: {session_id}"
            )
        return selection

    def provider_for(
        self,
        session_id: str,
        *,
        selection: MainLLMSelection | None = None,
    ) -> LLMProvider:
        resolved = selection or self.resolve(session_id)
        if (
            self._provider is not None
            and self._selection is not None
            and self._selection.effective_provider_key
            == resolved.effective_provider_key
        ):
            self._selection = resolved
            return self._provider

        previous_key = (
            self._selection.effective_provider_key
            if self._selection is not None
            else None
        )
        self._provider = LLMClientManager.get().get_provider(
            AGENT_MAIN_BIZ_KEY,
            provider_key=resolved.effective_provider_key,
        )
        self._model = self._provider.get_default_model()
        self._selection = resolved
        logger.info(
            _TAG + " provider selected: session_id={}, previous={}, current={}, source={}",
            session_id,
            previous_key,
            resolved.effective_provider_key,
            resolved.effective_source,
        )
        return self._provider
