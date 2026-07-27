"""Lifespan-owned Play data composition root."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rpg_core.rp_modules.application import RPModuleApplicationService
from rpg_core.rp_modules.plot_scheduler.management import (
    PlotScheduleManagementService,
)
from rpg_core.rp_modules.plot_scheduler.story_projection import (
    PlotStoryProjectionService,
)
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.scene.status import SceneStatusService
from rpg_core.session.composer import SessionComposerApplicationService
from rpg_core.settings import settings
from rpg_core.status.administration import StatusTableAdministrationService
from rpg_data.services import DataServiceGateway, get_data_service_gateway
from rpg_data.settings import get_database_path

from play_api.backends.data_backends import (
    PlayCatalogBackend,
    PlayRuntimeMaintenanceBackend,
    PlaySessionReadBackend,
    PlayStoryAssetBackend,
)


@dataclass(slots=True)
class PlayDataRuntime:
    """Own one data Gateway and expose only preassembled narrow backends."""

    catalog: PlayCatalogBackend
    story_assets: PlayStoryAssetBackend
    session_read: PlaySessionReadBackend
    runtime_maintenance: PlayRuntimeMaintenanceBackend
    _gateway: DataServiceGateway = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def create(
        cls,
        database_path: str | Path | None = None,
    ) -> "PlayDataRuntime":
        gateway = get_data_service_gateway(
            database_path if database_path is not None else get_database_path()
        )
        try:
            gateway.initialize()
            rp_modules = RPModuleApplicationService(
                RPModuleRegistry(settings=settings.rp_module_settings),
                gateway.rp_modules,
            )
            session_composer = SessionComposerApplicationService(
                gateway.session_composer,
                rp_modules,
            )
            status_administration = StatusTableAdministrationService(
                gateway.status
            )
            scene = SceneStatusService(gateway.status)
            plot_management = PlotScheduleManagementService(
                gateway.plot_scheduling
            )
            plot_story_projection = PlotStoryProjectionService(
                gateway.plot_scheduling
            )
            return cls(
                catalog=PlayCatalogBackend(
                    catalog=gateway.catalog,
                    sessions=gateway.sessions,
                    session_composer=session_composer,
                    rp_modules=rp_modules,
                ),
                story_assets=PlayStoryAssetBackend(
                    catalog=gateway.catalog,
                    character_management=gateway.character_management,
                    lorebook_management=gateway.lorebook_management,
                    status_administration=status_administration,
                    plot_management=plot_management,
                    plot_story_projection=plot_story_projection,
                    scene=scene,
                ),
                session_read=PlaySessionReadBackend(
                    catalog=gateway.catalog,
                    messages=gateway.messages,
                    story_memory=gateway.story_memory,
                    narrative_outcomes=gateway.narrative_outcomes,
                    plot_scheduling=gateway.plot_scheduling,
                    scene=scene,
                ),
                runtime_maintenance=PlayRuntimeMaintenanceBackend(
                    gateway.runtime_maintenance
                ),
                _gateway=gateway,
            )
        except Exception:
            gateway.close()
            raise

    @property
    def database_path(self) -> Path:
        return self._gateway.database_path

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._gateway.close()


__all__ = ["PlayDataRuntime"]
