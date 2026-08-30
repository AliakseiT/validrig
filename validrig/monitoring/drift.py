# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift detection against two distinct baselines.

* **absolute** — is production within the envelope validation established?
  (override rate above its threshold; a necessary element's completeness below
  its threshold)
* **trend** — is it moving? (override rate rising beyond a delta versus a prior
  snapshot)

These are reported separately and never collapsed: a snapshot can be
within-threshold but trending badly, or out-of-threshold but stable — different
post-market signals with different actions. Only *degradation* raises a finding;
an improving override rate (falling) is never an alert. An underpowered snapshot
is advisory, not actionable.
"""

from __future__ import annotations

from typing import Any

from validrig.power import DEFAULT_MIN_N, is_underpowered


def evaluate_drift(
    snapshot: dict[str, Any],
    thresholds: dict[str, float],
    prior_snapshot: dict[str, Any] | None = None,
    min_n: int = DEFAULT_MIN_N,
) -> dict[str, Any]:
    n = snapshot.get("n_events", 0)
    orr = snapshot["override_rate"]["mean"]

    absolute: list[dict[str, Any]] = []
    if "override_rate_max" in thresholds and orr > thresholds["override_rate_max"]:
        absolute.append({
            "kind": "override_rate_above_threshold",
            "value": orr, "limit": thresholds["override_rate_max"],
        })
    completeness_min = thresholds.get("input_completeness_min")
    if completeness_min is not None:
        for elem in snapshot.get("completeness", []):
            rate = elem["present_rate"]
            if elem["necessary"] and rate is not None and rate < completeness_min:
                absolute.append({
                    "kind": "necessary_element_incomplete",
                    "element": elem["element"], "value": rate, "limit": completeness_min,
                })

    trend: list[dict[str, Any]] = []
    has_prior = prior_snapshot is not None
    if has_prior:
        prior_orr = prior_snapshot["override_rate"]["mean"]
        delta = orr - prior_orr
        limit = thresholds.get("override_trend_delta_max", float("inf"))
        # Only a rising override rate (degradation) is a finding; falling is fine.
        if delta > limit:
            trend.append({
                "kind": "override_rate_rising",
                "delta": delta, "limit": limit, "from": prior_orr, "to": orr,
            })

    underpowered = is_underpowered(n, min_n)
    has_findings = bool(absolute or trend)
    if underpowered:
        status = "advisory_low_n"
    elif has_findings:
        status = "drift"
    else:
        status = "ok"

    return {
        "status": status,
        "underpowered": underpowered,
        "n_events": n,
        "absolute": {"findings": absolute},
        "trend": {"has_prior": has_prior, "findings": trend},
    }
