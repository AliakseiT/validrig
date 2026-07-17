# SPDX-License-Identifier: AGPL-3.0-or-later
"""Consolidated validation dossier — one assembled, attested record per run.

Pulls the per-run QMS records (V&V plan, V&V report, input contract, and — when
present — the calibration status) into a single structured document that
``dossier_html`` renders as a printable page. This is the reviewer-ready
deliverable: everything an auditor needs, with the pinned-inputs attestation
printed once.

Signing seam (not yet implemented): ``signing.release_anchor`` is a placeholder
for the DearAuditor mechanism of anchoring a record to an immutable GitHub
release — publish the dossier under a ``QMS-*``-style release tag, and the tag +
the release's content hash become the tamper-evident anchor for the
``pinned_inputs_hash`` already computed here. Prepared for, not rushed in.
"""

from __future__ import annotations

from typing import Any

from harness.models.pack import BatterySpec, Pack
from harness.models.results import Grade, Run
from harness.qms.attestation import build_attestation
from harness.qms.baseline import QMS_BASELINE_TAG
from harness.qms.mappers import build_vv_plan, build_vv_report


def build_dossier(
    pack: Pack,
    battery: BatterySpec,
    run: Run,
    grades: list[Grade],
    validation_report: dict[str, Any],
    contract: dict[str, Any],
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    vv_report = build_vv_report(
        pack, battery, run.pins, run.meta, grades, validation_report, contract,
        calibration=calibration,
    )
    vv_plan = build_vv_plan(pack, battery)
    return {
        "record_type": "validation_dossier",
        "schema_version": 1,
        "product_id": pack.manifest.id,
        "product_version": pack.manifest.version,
        "intended_use": pack.manifest.intended_use.strip(),
        "run_id": run.meta.run_id,
        "generated_at": run.meta.timestamp,
        "qms_baseline_tag": QMS_BASELINE_TAG,
        "attestation": build_attestation(run.pins, run.meta),
        "signing": {
            "status": "unsigned",
            "mechanism": "github_immutable_release (planned)",
            "release_anchor": None,  # filled when anchored to a QMS-* release
            "note": "Draft evidence; sign by anchoring to an immutable GitHub release.",
        },
        "vv_plan": vv_plan,
        "vv_report": vv_report,
        "acceptance": validation_report.get("acceptance", {}),
        "contract": contract,
    }
