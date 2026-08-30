# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calibration status as a QMS artifact.

Judge-human agreement (kappa) and the gate verdict, rendered as a signable,
attested record. This is *project data* — it is written to the run store (the
project repo), never into the engine repo. It is produced asynchronously (a human
grades over time), so it is evaluated as-of-now from the calibration store, not
at run time.
"""

from __future__ import annotations

from typing import Any

from validrig.models.results import Pins, RunMeta
from validrig.qms.attestation import build_attestation
from validrig.qms.baseline import QMS_BASELINE_TAG


def build_calibration_status(
    pins: Pins,
    run_meta: RunMeta,
    agreement: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_type": "calibration_status",
        "schema_version": 1,
        "qms_baseline_tag": QMS_BASELINE_TAG,
        "agreement": agreement,
        "gate": gate,
        "attestation": build_attestation(pins, run_meta),
    }
