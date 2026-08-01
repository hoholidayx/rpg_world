"""RPG runtime composition root for the MCP process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.rp_modules.plot_scheduler.management import (
    PlotScheduleManagementService,
)
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.composer import SessionComposerApplicationService
from rpg_data.services.gateway import DataServiceGateway
from rpg_mcp.runtime import RuntimeApplication
from rpg_mcp.runtime_ports import RuntimeServices


@dataclass
class RuntimeComposition:
    application: RuntimeApplication
    gateway: DataServiceGateway

    def close(self) -> None:
        self.gateway.close()


def build_runtime_composition(
    db_path: str | Path | None = None,
) -> RuntimeComposition:
    gateway = DataServiceGateway(db_path)
    gateway.initialize()
    return RuntimeComposition(
        application=build_runtime_application(gateway),
        gateway=gateway,
    )


def build_runtime_application(
    gateway: DataServiceGateway,
) -> RuntimeApplication:
    """Compose the runtime adapter over an already-owned data gateway.

    The MCP process normally owns its gateway through
    :func:`build_runtime_composition`.  Tests and other composition roots that
    already own the database lifecycle can use this narrower helper without
    opening a second connection or duplicating the production service wiring.
    """

    services = RuntimeServices(
        transaction=gateway.transaction,
        catalog=gateway.catalog,
        stories=SessionCatalogService(gateway.sessions),
        characters=gateway.character_management,
        lorebook=gateway.lorebook_management,
        status=gateway.status,
        composer=SessionComposerApplicationService(gateway.session_composer),
        rp_modules=RPModuleApplicationService(
            RPModuleRegistry(),
            gateway.rp_modules,
        ),
        rp_module_data=gateway.rp_modules,
        plot=PlotScheduleManagementService(gateway.plot_scheduling),
        story_packs=gateway.story_packs,
    )
    return RuntimeApplication(services)


__all__ = [
    "RuntimeComposition",
    "build_runtime_application",
    "build_runtime_composition",
]
