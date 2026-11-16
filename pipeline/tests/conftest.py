"""Hypothesis profiles (testing.md): `fast` (default, whole suite under 60 s) and `deep` (nightly, 10x examples)."""

import os

from hypothesis import HealthCheck, settings
from hypothesis.database import DirectoryBasedExampleDatabase

_common = {"deadline": None, "suppress_health_check": [HealthCheck.too_slow, HealthCheck.data_too_large]}
settings.register_profile("fast", max_examples=100, derandomize=False, **_common)
settings.register_profile(
    "deep", max_examples=1000, database=DirectoryBasedExampleDatabase(".hypothesis/deep"), **_common
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "fast"))
