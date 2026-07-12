"""Resolve per-turn mode and narrative-style configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import (
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnPlayerCharacterSnapshot,
    TurnRequest,
)
from rpg_data import models as data_models
from rpg_data.story_template import (
    UNBOUND_PLAYER_ROLE_NAME,
    render_story_text_template,
)

if TYPE_CHECKING:
    from rpg_data.services import DataServiceGateway


class TurnSnapshotResolver:
    """Build immutable execution snapshots from catalog-backed configuration."""

    def __init__(
        self,
        session_id: str,
        *,
        gateway: "DataServiceGateway | None" = None,
    ) -> None:
        self._session_id = str(session_id)
        self._gateway = gateway

    def resolve(
        self,
        request: TurnRequest,
        *,
        require_player_character: bool = False,
    ) -> TurnExecutionSnapshot:
        gateway = self._get_gateway()
        policy = TurnExecutionPolicy.for_mode(request.mode)
        session = gateway.catalog.get_session(self._session_id)
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

        player_character = self._resolve_player_character(gateway)
        if require_player_character and player_character is None:
            raise PlayerCharacterRequiredError(
                self._role_bind_prompt(gateway)
            )
        rendered_story_prompt = self._render_story_prompt(
            gateway,
            player_character,
        )

        mode_config = gateway.session_composer.get_mode(
            session.workspace_id,
            request.mode.value,
        )
        mode_prompt = mode_config.prompt if mode_config is not None else ""

        style = None
        if policy.apply_narrative_style or request.narrative_style_id is not None:
            # Explicit overrides remain validated in OOC mode even though the
            # OOC execution policy suppresses their prompt.
            style = gateway.session_composer.resolve_session_style(
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
        gateway: "DataServiceGateway",
    ) -> TurnPlayerCharacterSnapshot | None:
        state = gateway.session_roles.get_state(self._session_id)
        if (
            state.status != data_models.PLAYER_CHARACTER_STATUS_BOUND
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
        gateway: "DataServiceGateway",
        player_character: TurnPlayerCharacterSnapshot | None,
    ) -> str:
        story = gateway.catalog.get_session_story(self._session_id)
        raw_prompt = str(story.story_prompt or "") if story is not None else ""
        return render_story_text_template(
            raw_prompt,
            user_play_role_name=(
                player_character.name
                if player_character is not None
                else UNBOUND_PLAYER_ROLE_NAME
            ),
        )

    def _role_bind_prompt(self, gateway: "DataServiceGateway") -> str:
        return gateway.session_roles.render_role_bind_prompt(self._session_id)

    def _get_gateway(self) -> "DataServiceGateway":
        if self._gateway is None:
            from rpg_data.services import get_data_service_gateway

            self._gateway = get_data_service_gateway()
        return self._gateway


class PlayerCharacterRequiredError(RuntimeError):
    """Internal bypass signal when a normal turn loses its role binding."""

    def __init__(self, reply: str) -> None:
        self.reply = str(reply)
        super().__init__(self.reply)
