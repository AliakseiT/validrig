# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate production events into a MonitoringSnapshot.

Reports the override rate (with a bootstrap CI) and, per contract element, the
input completeness observed in production — three-state: a not-logged element
has ``present_rate: null`` and is excluded from completeness, never counted as
absent.

The override rate is a *signal*, not a measure of error: a clinician may override
a correct output. Drift detection treats changes in the signal, not its absolute
level, as the primary concern.
"""

from __future__ import annotations

from typing import Any

from validrig.monitoring.models import ProductionEvent
from validrig.stats.bootstrap import bootstrap_ci

_PHI_ASSERTION = (
    "Aggregate signals only: element-presence booleans and an override flag. "
    "No case content is present in this snapshot."
)


def build_snapshot(
    events: list[ProductionEvent],
    contract: dict[str, Any],
    period: str,
    seed: int = 0,
) -> dict[str, Any]:
    n = len(events)
    override_flags = [1.0 if e.overridden else 0.0 for e in events]
    orr_mean, orr_lo, orr_hi = bootstrap_ci(override_flags, seed=seed)

    necessary = set(contract.get("minimal_sufficient_set_candidate", []))
    elements = contract.get("elements", [])

    completeness = []
    for elem in elements:
        name = elem["name"]
        logged = [e for e in events if e.is_logged(name)]
        present = [e for e in logged if e.elements_present[name]]
        present_rate = (len(present) / len(logged)) if logged else None  # not-logged -> unknown
        completeness.append({
            "element": name,
            "necessary": name in necessary,
            "logged_n": len(logged),
            "present_rate": present_rate,
        })

    return {
        "artifact_type": "monitoring_snapshot",
        "schema_version": 1,
        "period": period,
        "n_events": n,
        "override_rate": {"mean": orr_mean, "lo": orr_lo, "hi": orr_hi},
        "completeness": completeness,
        "pins": contract.get("pins"),
        "phi_boundary": _PHI_ASSERTION,
    }
