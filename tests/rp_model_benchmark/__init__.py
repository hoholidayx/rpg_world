"""Provider-direct, story-neutral RP model benchmark."""

from tests.rp_model_benchmark.loader import load_dataset
from tests.rp_model_benchmark.models import RPBenchmarkDataset

__all__ = ["RPBenchmarkDataset", "load_dataset"]
