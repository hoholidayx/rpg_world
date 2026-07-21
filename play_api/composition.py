"""Play API composition helpers for local application services."""

from __future__ import annotations

from rpg_core.session.composer import SessionComposerApplicationService
from rpg_data.services import get_data_service_gateway


def session_composer_service() -> SessionComposerApplicationService:
    gateway = get_data_service_gateway()
    return SessionComposerApplicationService(gateway.session_composer)


__all__ = ["session_composer_service"]
