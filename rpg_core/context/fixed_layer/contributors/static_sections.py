"""Static fixed-layer section contributor."""

from __future__ import annotations

from rpg_core.context.fixed_layer.models import (
    FIXED_LAYER_SOURCE_RP_MODULE,
    FixedLayerContribution,
    FixedLayerContributor,
    FixedLayerSection,
)


class StaticFixedLayerContributor(FixedLayerContributor):
    """Wrap already-built sections as one fixed-layer contributor."""

    name = FIXED_LAYER_SOURCE_RP_MODULE

    def __init__(self, sections: list[FixedLayerSection] | None = None) -> None:
        self._sections = list(sections or [])

    def get_fixed_contribution(self) -> FixedLayerContribution:
        return FixedLayerContribution(sections=list(self._sections))
