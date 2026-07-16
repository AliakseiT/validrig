# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared statistical-power guard.

A rate computed over a handful of observations is noise, not signal. Both the
judge-calibration gate and the monitoring drift detector treat an underpowered
sample as *advisory*, not actionable — using this one definition so the two
cannot drift apart.
"""

from __future__ import annotations

DEFAULT_MIN_N = 10


def is_underpowered(n: int, min_n: int = DEFAULT_MIN_N) -> bool:
    return n < min_n
