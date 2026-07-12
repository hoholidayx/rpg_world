"""Resolve per-turn mode and narrative-style configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rpg_core.agent.turn.models import (
    TurnExecutionPolicy,
    TurnExecutionSnapshot,
    TurnRequest,
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

    def resolve(self, request: TurnRequest) -> TurnExecutionSnapshot:
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
        )

    def _get_gateway(self) -> "DataServiceGateway":
        if self._gateway is None:
            from rpg_data.services import get_data_service_gateway

            self._gateway = get_data_service_gateway()
        return self._gateway
