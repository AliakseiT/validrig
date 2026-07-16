# SPDX-License-Identifier: AGPL-3.0-or-later
"""The calibration gate.

A pure function over an agreement summary: does judge-human agreement clear the
pre-registered kappa threshold? It is deliberately standalone and **not** wired
into the synchronous run/report path — calibration is asynchronous (a human
grades over hours or days), so at run time there is no calibration data yet.
A separate step reads the calibration store and evaluates this gate as-of-now.

Underpowered samples are advisory, not blocking: kappa on a handful of paired
grades is a measurement artifact, not a real disagreement — the same
"don't conflate a measurement gap with a signal" discipline used elsewhere.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MIN_N = 10


def evaluate_gate(
    agreement: dict[str, Any],
    kappa_min: float,
    min_n: int = DEFAULT_MIN_N,
) -> dict[str, Any]:
    item_results: dict[str, dict[str, Any]] = {}
    for item_id, stats in agreement.get("items", {}).items():
        item_results[item_id] = _status_for(stats, kappa_min, min_n)

    statuses = {r["status"] for r in item_results.values()}
    if "block" in statuses:
        overall = "block"
    elif statuses and statuses <= {"advisory_low_n"}:
        overall = "advisory_low_n"
    elif statuses:
        overall = "pass"
    else:
        overall = "no_data"

    return {
        "kappa_min": kappa_min,
        "min_n": min_n,
        "items": item_results,
        "status": overall,
        "blocks_report_issuance": overall == "block",
    }


def _status_for(stats: dict[str, Any], kappa_min: float, min_n: int) -> dict[str, Any]:
    n = stats.get("n", 0)
    kappa = stats.get("kappa")
    if n < min_n or kappa is None:
        status = "advisory_low_n"
    elif kappa >= kappa_min:
        status = "pass"
    else:
        status = "block"
    return {"n": n, "kappa": kappa, "status": status}
