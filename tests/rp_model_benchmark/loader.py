"""Strict loading and canonical-dataset validation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from tests.rp_model_benchmark.models import (
    BenchmarkCategory,
    RPBenchmarkDataset,
)


DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parent / "datasets" / "neutral-rp-v1.json"
)
CANONICAL_FULL_CASES = 48
CANONICAL_SMOKE_CASES = 12
CASES_PER_CATEGORY = 6


class RPBenchmarkInputError(ValueError):
    """The benchmark dataset cannot be used safely."""


def load_dataset(
    path: str | Path | None = None,
    *,
    require_canonical_shape: bool = True,
) -> RPBenchmarkDataset:
    source = Path(path or DEFAULT_DATASET_PATH).expanduser().resolve()
    if not source.is_file():
        raise RPBenchmarkInputError(f"benchmark dataset not found: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
        dataset = RPBenchmarkDataset.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise RPBenchmarkInputError(f"invalid benchmark dataset: {source}: {exc}") from exc
    if require_canonical_shape:
        validate_canonical_dataset(dataset)
    return dataset


def validate_canonical_dataset(dataset: RPBenchmarkDataset) -> None:
    if len(dataset.cases) != CANONICAL_FULL_CASES:
        raise RPBenchmarkInputError(
            f"canonical dataset requires {CANONICAL_FULL_CASES} cases"
        )
    counts = Counter(item.category for item in dataset.cases)
    expected = {category: CASES_PER_CATEGORY for category in BenchmarkCategory}
    if counts != expected:
        raise RPBenchmarkInputError(
            f"canonical category distribution mismatch: {dict(counts)!r}"
        )
    smoke_count = sum(item.smoke for item in dataset.cases)
    if smoke_count != CANONICAL_SMOKE_CASES:
        raise RPBenchmarkInputError(
            f"canonical dataset requires {CANONICAL_SMOKE_CASES} smoke cases"
        )
    if any(
        not any(item.smoke for item in dataset.cases if item.category is category)
        for category in BenchmarkCategory
    ):
        raise RPBenchmarkInputError("smoke suite must cover every category")


def select_cases(dataset: RPBenchmarkDataset, suite: str) -> tuple:
    if suite == "smoke":
        return tuple(item for item in dataset.cases if item.smoke)
    if suite == "full":
        return tuple(dataset.cases)
    raise RPBenchmarkInputError(f"unsupported benchmark suite: {suite!r}")


__all__ = [
    "CANONICAL_FULL_CASES",
    "CANONICAL_SMOKE_CASES",
    "CASES_PER_CATEGORY",
    "DEFAULT_DATASET_PATH",
    "RPBenchmarkInputError",
    "load_dataset",
    "select_cases",
    "validate_canonical_dataset",
]
