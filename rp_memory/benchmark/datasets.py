"""Dataset selection shared by the benchmark CLI and suite."""

from __future__ import annotations


LOCOMO = "locomo"
RP_GOLD = "rp-gold"
LONGMEMEVAL_S = "longmemeval-s"

SUPPORTED_DATASETS = (LOCOMO, RP_GOLD, LONGMEMEVAL_S)
DEFAULT_DATASETS = (LOCOMO, RP_GOLD)


def parse_datasets(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Normalize repeated and comma-separated CLI values without reordering."""
    if not values:
        return DEFAULT_DATASETS
    selected: list[str] = []
    for value in values:
        for item in str(value).split(","):
            dataset = item.strip().lower()
            if not dataset:
                continue
            if dataset not in SUPPORTED_DATASETS:
                supported = ", ".join(SUPPORTED_DATASETS)
                raise ValueError(f"unsupported benchmark dataset {dataset!r}; choose from {supported}")
            if dataset not in selected:
                selected.append(dataset)
    if not selected:
        raise ValueError("at least one benchmark dataset must be selected")
    return tuple(selected)
