# SPDX-License-Identifier: AGPL-3.0-or-later
"""Post-market monitoring: snapshot, three-state completeness, drift direction."""

import pytest
from pydantic import ValidationError

from validrig.monitoring.drift import evaluate_drift
from validrig.monitoring.models import ProductionEvent
from validrig.monitoring.snapshot import build_snapshot

_CONTRACT = {
    "pins": {"pack_id": "p", "seed": 1},
    "minimal_sufficient_set_candidate": ["pathology_report", "molecular_report"],
    "elements": [
        {"name": "pathology_report"},
        {"name": "molecular_report"},
        {"name": "prior_notes"},
    ],
}
_THRESH = {"override_rate_max": 0.30, "input_completeness_min": 0.80,
           "override_trend_delta_max": 0.05}


def _events(n, n_overridden, present=None, period="2026-Q3"):
    present = present or {"pathology_report": True, "molecular_report": True, "prior_notes": True}
    return [ProductionEvent(period=period, elements_present=dict(present), overridden=(i < n_overridden))
            for i in range(n)]


def test_event_rejects_unexpected_field():
    with pytest.raises(ValidationError):
        ProductionEvent(period="p", overridden=False, note="patient John Doe")  # PHI-ish free text


def test_snapshot_override_rate_and_completeness():
    snap = build_snapshot(_events(20, 4), _CONTRACT, "2026-Q3")
    assert snap["n_events"] == 20
    assert snap["override_rate"]["mean"] == pytest.approx(0.2)
    comp = {c["element"]: c for c in snap["completeness"]}
    assert comp["pathology_report"]["present_rate"] == 1.0
    assert comp["pathology_report"]["necessary"] is True
    assert comp["prior_notes"]["necessary"] is False


def test_not_logged_element_is_unknown_not_absent():
    # molecular_report presence is never logged -> present_rate None, excluded
    present = {"pathology_report": True}  # molecular_report key absent = not-logged
    snap = build_snapshot(_events(20, 2, present=present), _CONTRACT, "2026-Q3")
    comp = {c["element"]: c for c in snap["completeness"]}
    assert comp["molecular_report"]["present_rate"] is None
    assert comp["molecular_report"]["logged_n"] == 0
    # and drift does NOT fire on a not-logged necessary element
    drift = evaluate_drift(snap, _THRESH)
    assert not any(f["kind"] == "necessary_element_incomplete" for f in drift["absolute"]["findings"])


def test_absolute_override_above_threshold_fires():
    snap = build_snapshot(_events(20, 8), _CONTRACT, "2026-Q3")  # 0.4 > 0.30
    drift = evaluate_drift(snap, _THRESH)
    assert drift["status"] == "drift"
    assert any(f["kind"] == "override_rate_above_threshold" for f in drift["absolute"]["findings"])


def test_absolute_necessary_element_incomplete_fires():
    # molecular_report present in only half of events -> 0.5 < 0.80
    events = (_events(10, 1, present={"pathology_report": True, "molecular_report": True})
              + _events(10, 1, present={"pathology_report": True, "molecular_report": False}))
    snap = build_snapshot(events, _CONTRACT, "2026-Q3")
    drift = evaluate_drift(snap, _THRESH)
    kinds = [f for f in drift["absolute"]["findings"] if f["kind"] == "necessary_element_incomplete"]
    assert any(f["element"] == "molecular_report" for f in kinds)


def test_trend_fires_only_on_degradation_same_absolute_level():
    # all three CURRENT snapshots sit at override 0.2 (below the 0.30 absolute max)
    current = build_snapshot(_events(20, 4), _CONTRACT, "2026-Q4")  # 0.2
    degrading_prior = build_snapshot(_events(20, 2), _CONTRACT, "2026-Q3")  # 0.1 -> +0.1 rising
    stable_prior = build_snapshot(_events(20, 4), _CONTRACT, "2026-Q3")     # 0.2 -> 0 change
    improving_prior = build_snapshot(_events(20, 6), _CONTRACT, "2026-Q3")  # 0.3 -> -0.1 falling

    degrading = evaluate_drift(current, _THRESH, prior_snapshot=degrading_prior)
    stable = evaluate_drift(current, _THRESH, prior_snapshot=stable_prior)
    improving = evaluate_drift(current, _THRESH, prior_snapshot=improving_prior)

    assert degrading["status"] == "drift"
    assert any(f["kind"] == "override_rate_rising" for f in degrading["trend"]["findings"])
    # stable and improving do NOT fire (and no absolute finding at 0.2)
    assert stable["status"] == "ok"
    assert improving["status"] == "ok"
    assert improving["trend"]["findings"] == []


def test_underpowered_snapshot_is_advisory():
    snap = build_snapshot(_events(5, 4), _CONTRACT, "2026-Q3")  # 0.8 override but n=5
    drift = evaluate_drift(snap, _THRESH)
    assert drift["status"] == "advisory_low_n"
    assert drift["underpowered"] is True
