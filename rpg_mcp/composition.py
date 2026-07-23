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
    return RuntimeComposition(
        application=RuntimeApplication(services),
        gateway=gateway,
    )


__all__ = ["RuntimeComposition", "build_runtime_composition"]
