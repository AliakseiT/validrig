# SPDX-License-Identifier: AGPL-3.0-or-later
"""Judge calibration: sample generations, capture human double-grades, and
measure judge-human agreement to gate report issuance.

Human grades are kept in a *separate* append-only store and joined with the
judge's grades at read time. The immutable, content-hashed ``Grade`` records are
never mutated — that would corrupt the determinism and regression guarantees.
"""

from harness.calibration.agreement import compute_agreement, cohen_kappa
from harness.calibration.gate import evaluate_gate
from harness.calibration.models import HumanGrade
from harness.calibration.sample import select_calibration_sample
from harness.calibration.store import CalibrationStore

__all__ = [
    "HumanGrade",
    "select_calibration_sample",
    "CalibrationStore",
    "compute_agreement",
    "cohen_kappa",
    "evaluate_gate",
]
