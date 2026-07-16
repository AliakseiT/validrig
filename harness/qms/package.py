# SPDX-License-Identifier: AGPL-3.0-or-later
"""QMS package manifest — the index that makes the package a package.

Ties the documents produced for one validation campaign to their shared pinned
inputs, the pack version, the overall verdict, and the calibration gate. Written
to the run store (project repo). A reviewer opens one file to see what the
package contains and that every part shares the same provenance.
"""

from __future__ import annotations

from typing import Any

from harness.models.results import Pins, RunMeta
from harness.qms.attestation import build_attestation


def build_package_manifest(
    pins: Pins,
    run_meta: RunMeta,
    documents: list[dict[str, str]],
    release_recommendation: str,
    calibration_gate_status: str,
) -> dict[str, Any]:
    return {
        "record_type": "qms_package_manifest",
        "schema_version": 1,
        "product_id": pins.pack_id,
        "pack_version": pins.pack_version,
        "run_id": run_meta.run_id,
        "documents": documents,
        "release_recommendation": release_recommendation,
        "calibration_gate_status": calibration_gate_status,
        "attestation": build_attestation(pins, run_meta),
    }
