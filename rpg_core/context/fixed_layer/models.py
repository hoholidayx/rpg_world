"""Fixed-layer data models and shared constants."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from commons.types import JsonObject

FIXED_LAYER_CORE_SECTION_ID = "core_rp_contract"
FIXED_LAYER_LOREBOOK_SECTION_ID = "lorebook"
FIXED_LAYER_CHARACTER_SECTION_ID = "character_card"

FIXED_LAYER_SOURCE_CORE = "core"
FIXED_LAYER_SOURCE_LOREBOOK = "lorebook"
FIXED_LAYER_SOURCE_CHARACTER = "character"
FIXED_LAYER_SOURCE_RP_MODULE = "rp_module"


@dataclass(frozen=True)
class FixedLayerSection:
    """渲染到固定层的一段稳定内容。"""

    id: str
    title: str
    content: str
    priority: int = 100
    source: str = FIXED_LAYER_SOURCE_CORE
    source_kind: str = FIXED_LAYER_SOURCE_CORE
    item_count: int = 0


@dataclass(frozen=True)
class FixedLayerContribution:
    """一类固定层来源贡献的结构化快照。"""

    sections: list[FixedLayerSection] = field(default_factory=list)
    lorebook_entries: list[JsonObject] = field(default_factory=list)
    characters: list[JsonObject] = field(default_factory=list)


class FixedLayerContributor(ABC):
    """固定层贡献者，只负责产出稳定 section 和结构化领域数据。"""

    name = "fixed_layer"

    @abstractmethod
    def get_fixed_contribution(self) -> FixedLayerContribution:
        raise NotImplementedError
