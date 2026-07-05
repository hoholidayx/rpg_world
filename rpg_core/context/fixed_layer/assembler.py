"""Fixed-layer contributor assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from commons.types import JsonObject
from rpg_core.context.fixed_layer.models import FixedLayerContributor, FixedLayerSection

if TYPE_CHECKING:
    from rpg_core.context.rpg_context import FixedLayerData


class FixedLayerAssembler:
    """Assemble all fixed-layer contributors into one structured snapshot."""

    def __init__(
        self,
        world_name: str = "Nanobot Realm",
        contributors: list[FixedLayerContributor] | None = None,
    ) -> None:
        self._world_name = world_name
        self._contributors = list(contributors or [])

    def with_contributor(self, contributor: FixedLayerContributor) -> "FixedLayerAssembler":
        return FixedLayerAssembler(
            world_name=self._world_name,
            contributors=[*self._contributors, contributor],
        )

    def assemble(self) -> "FixedLayerData":
        from rpg_core.context.rpg_context import FixedLayerData

        sections: list[FixedLayerSection] = []
        lorebook_entries: list[JsonObject] = []
        characters: list[JsonObject] = []

        for contributor in self._contributors:
            try:
                contribution = contributor.get_fixed_contribution()
            except Exception as exc:
                contributor_name = getattr(contributor, "name", contributor.__class__.__name__)
                logger.debug(
                    "[FixedLayerAssembler] contributor skipped: name={}, error={}",
                    contributor_name,
                    exc,
                )
                continue
            sections.extend(contribution.sections)
            lorebook_entries.extend(contribution.lorebook_entries)
            characters.extend(contribution.characters)

        sorted_sections = sorted(sections, key=lambda section: (section.priority, section.id))
        active_sections = [section for section in sorted_sections if section.content.strip()]
        return FixedLayerData(
            world_name=self._world_name,
            sections=active_sections,
            lorebook_entries=lorebook_entries,
            characters=characters,
        )
