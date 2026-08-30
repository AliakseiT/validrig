# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bootstrap confidence intervals.

A simple, citable percentile bootstrap over the mean, with a seeded RNG so
results are reproducible and can serve as a regression baseline. No bespoke
statistics — resample with replacement, take percentiles.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def bootstrap_ci(
    values: Sequence[float],
    n_boot: int = 1000,
    seed: int = 0,
    ci: float = 0.95,
) -> tuple[float, float, float]:
    """Return ``(mean, lo, hi)`` where lo/hi bound a ``ci`` percentile interval.

    Deterministic for a given ``seed``. Empty input returns ``(0.0, 0.0, 0.0)``.
    """
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return (0.0, 0.0, 0.0)

    rng = np.random.default_rng(seed)
    n = arr.size
    idx = rng.integers(0, n, size=(n_boot, n))
    boot_means = arr[idx].mean(axis=1)

    lo_pct = (1.0 - ci) / 2.0 * 100.0
    hi_pct = (1.0 + ci) / 2.0 * 100.0
    lo = float(np.percentile(boot_means, lo_pct))
    hi = float(np.percentile(boot_means, hi_pct))
    return (float(arr.mean()), lo, hi)
