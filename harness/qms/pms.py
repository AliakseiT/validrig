# SPDX-License-Identifier: AGPL-3.0-or-later
"""Post-market surveillance records from monitoring outputs.

Two mappers, both fed by *real* snapshot/drift outputs (never fabricated):

* ``build_pms_report`` — a PMS periodic report from a snapshot + drift. Always
  produced; a clean snapshot yields a report with "no signals".
* ``build_aims_event`` — an AIMS event, produced **only** when drift is actually
  detected. A clean or advisory snapshot produces no event.

Both mirror the r05 templates, attest over the snapshot's pinned inputs, and
leave signatures unsigned.
"""

from __future__ import annotations

from typing import Any

from harness.qms.attestation import build_attestation_from_dict, unsigned_signoff
from harness.qms.baseline import QMS_BASELINE_TAG


def _signals(drift: dict[str, Any]) -> list[str]:
    out = []
    for f in drift.get("absolute", {}).get("findings", []):
        out.append(f"absolute: {f['kind']} ({f})")
    for f in drift.get("trend", {}).get("findings", []):
        out.append(f"trend: {f['kind']} ({f})")
    return out


def build_pms_report(snapshot: dict[str, Any], drift: dict[str, Any]) -> dict[str, Any]:
    signals = _signals(drift)
    return {
        "record_type": "pms_periodic_report",
        "schema_version": 1,
        "qms_baseline_tag": QMS_BASELINE_TAG,
        "metadata": {
            "report_id": f"PMS-{(snapshot.get('pins') or {}).get('pack_id', 'unknown')}-{snapshot['period']}",
            "product_id": (snapshot.get("pins") or {}).get("pack_id", "unknown"),
            "review_period": snapshot["period"],
            "reviewers": [],
        },
        "inputs_reviewed": {
            "reliability_metrics": {
                "override_rate": snapshot["override_rate"],
                "n_events": snapshot["n_events"],
                "input_completeness": snapshot["completeness"],
            },
        },
        "signal_assessment": {
            "drift_status": drift["status"],
            "signals_identified": signals or ["none"],
        },
        "decisions_and_actions": {
            "capa_required": "",
            "change_required": "",
            "follow_up_owner_and_due_date": "",
        },
        "attestation": build_attestation_from_dict(snapshot.get("pins")),
        "signatures": unsigned_signoff("Approved PMS Periodic Report",
                                       ),
    }


def build_aims_event(snapshot: dict[str, Any], drift: dict[str, Any]) -> dict[str, Any] | None:
    """Return an AIMS event ONLY if drift was actually detected; else None."""
    if drift.get("status") != "drift":
        return None
    return {
        "record_type": "aims_event",
        "schema_version": 1,
        "qms_baseline_tag": QMS_BASELINE_TAG,
        "event_type": "drift",
        "detected_on": snapshot["period"],
        "summary": "; ".join(_signals(drift)),
        "triage_decision": "confirmed_event",
        "impact_assessment": {"intended_use": "potential"},
        "linked_records": {"pms": f"PMS-*-{snapshot['period']}"},
        "status": "open",
        "attestation": build_attestation_from_dict(snapshot.get("pins")),
        "signatures": unsigned_signoff("Approved AIMS Event Triage",
                                       ),
    }
