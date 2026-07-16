# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic calibration sampling.

Selects a reproducible subset of a run's generations for human double-grading.
Because the judge grades every rubric item on every generation, sampling
generations already covers all items — so a seeded uniform sample is sufficient
for v1. The selection is a pure function of ``(sorted content keys, fraction,
seed)``, so an auditor can reproduce exactly which generations were reviewed.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

ContentKey = tuple[str, str, int]


def select_calibration_sample(
    content_keys: Sequence[ContentKey],
    fraction: float,
    seed: int = 0,
) -> list[ContentKey]:
    """Return a deterministic sample of ``ceil(fraction * n)`` content keys."""
    keys = sorted(set(content_keys))
    n = len(keys)
    if n == 0 or fraction <= 0:
        return []
    k = min(n, max(1, math.ceil(fraction * n)))
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, size=k, replace=False)
    return sorted(keys[i] for i in idx)
