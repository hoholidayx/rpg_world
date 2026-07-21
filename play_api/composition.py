"""Play API composition helpers for local application services."""

from __future__ import annotations

from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.session.composer import SessionComposerApplicationService
from rpg_core.settings import settings
from rpg_data.services import get_data_service_gateway


def session_composer_service() -> SessionComposerApplicationService:
    gateway = get_data_service_gateway()
    return SessionComposerApplicationService(gateway.session_composer)


def rp_module_service() -> RPModuleApplicationService:
    gateway = get_data_service_gateway()
    registry = RPModuleRegistry(settings=settings.rp_module_settings)
    return RPModuleApplicationService(registry, gateway.rp_modules)


__all__ = ["rp_module_service", "session_composer_service"]
