"""Resolve per-turn mode and narrative-style configuration."""

from __future__ import annotations

from typing import Protocol

from rpg_core.agent.turn.models import (
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnPlayerCharacterSnapshot,
    TurnRequest,
)
from rpg_core.agent.command.role import render_role_bind_prompt
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    PlayerCharacterOption,
    SessionPlayerCharacterState,
)
from rpg_core.story.template import (
    UNBOUND_PLAYER_ROLE_NAME,
    render_story_text_template,
)

from rpg_data import models as data_models
from rpg_data.model.session import Session


class TurnSnapshotDataPort(Protocol):
    def get_session(self, session_id: str) -> Session | None: ...

    def get_session_story(self, session_id: str) -> data_models.Story | None: ...

    def get_turn_mode(
        self,
        workspace_id: str,
        mode: str,
    ) -> data_models.WorkspaceTurnMode | None: ...

    def resolve_session_style(
        self,
        session_id: str,
        override_style_id: int | None,
    ) -> data_models.StoryNarrativeStyle | None: ...


class SessionRoleSnapshotReader(Protocol):
    def get_state(self, session_id: str) -> SessionPlayerCharacterState: ...

    def list_options(self, session_id: str) -> list[PlayerCharacterOption]: ...


class TurnSnapshotResolver:
    """Build immutable execution snapshots from catalog-backed configuration."""

    def __init__(
        self,
        session_id: str,
        *,
        data: TurnSnapshotDataPort,
        role_service: SessionRoleSnapshotReader,
    ) -> None:
        self._session_id = str(session_id)
        self._data = data
        self._role_service = role_service

    def resolve(
        self,
        request: TurnRequest,
        *,
        require_player_character: bool = False,
    ) -> TurnExecutionSnapshot:
        policy = TurnExecutionPolicy.for_mode(request.mode)
        session = self._data.get_session(self._session_id)
        if session is None:
            if request.narrative_style_id is not None:
                raise FileNotFoundError(
                    "Session not found while resolving narrative style: "
                    f"{self._session_id}"
                )
            # In-memory unit-test agents may intentionally have no catalog row.
            # Production Agent service resolves a catalog session first.
            return TurnExecutionSnapshot(
                request=request,
                mode_prompt="",
                narrative_style_id=None,
                narrative_style_name="",
                narrative_style_prompt="",
                policy=policy,
            )

        player_character = self._resolve_player_character()
        if require_player_character and player_character is None:
            raise PlayerCharacterRequiredError(self._role_bind_prompt())
        rendered_story_prompt = self._render_story_prompt(
            player_character,
        )

        mode_config = self._data.get_turn_mode(
            session.workspace_id,
            request.mode.value,
        )
        mode_prompt = mode_config.prompt if mode_config is not None else ""

        style = None
        if policy.apply_narrative_style or request.narrative_style_id is not None:
            # Explicit overrides remain validated in OOC mode even though the
            # OOC execution policy suppresses their prompt.
            style = self._data.resolve_session_style(
                self._session_id,
                request.narrative_style_id,
            )

        return TurnExecutionSnapshot(
            request=request,
            mode_prompt=mode_prompt,
            narrative_style_id=(style.narrative_style_id if style is not None else None),
            narrative_style_name=(style.name if style is not None else ""),
            narrative_style_prompt=(
                style.prompt if style is not None and policy.apply_narrative_style else ""
            ),
            policy=policy,
            player_character=player_character,
            rendered_story_prompt=rendered_story_prompt,
        )

    def _resolve_player_character(
        self,
    ) -> TurnPlayerCharacterSnapshot | None:
        state = self._role_service.get_state(self._session_id)
        if (
            state.status is not PlayerCharacterBindingStatus.BOUND
            or state.player is None
        ):
            return None
        player = state.player
        return TurnPlayerCharacterSnapshot(
            character_id=int(player.character_id),
            mount_id=int(player.mount_id),
            story_id=int(player.story_id),
            name=str(player.name),
        )

    def _render_story_prompt(
        self,
        player_character: TurnPlayerCharacterSnapshot | None,
    ) -> str:
        story = self._data.get_session_story(self._session_id)
        raw_prompt = str(story.story_prompt or "") if story is not None else ""
        return render_story_text_template(
            raw_prompt,
            user_play_role_name=(
                player_character.name
                if player_character is not None
                else UNBOUND_PLAYER_ROLE_NAME
            ),
        )

    def _role_bind_prompt(self) -> str:
        return render_role_bind_prompt(
            self._role_service.list_options(self._session_id),
            self._role_service.get_state(self._session_id),
        )


class PlayerCharacterRequiredError(RuntimeError):
    """Internal bypass signal when a normal turn loses its role binding."""

    def __init__(self, reply: str) -> None:
        self.reply = str(reply)
        super().__init__(self.reply)
