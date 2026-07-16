# SPDX-License-Identifier: AGPL-3.0-or-later
"""QMS integration: map immutable harness results into audit-ready records.

The engine emits structured records that mirror the DearAuditor Open QMS Baseline
templates (release ``QMS-2026-07-09-R005``); rendering turns them into
QMS-ready documents. Every record carries an attestation block — the content
hash of the pinned inputs — so the artifact is self-verifying. Records are
emitted as *draft evidence for a human to review and sign*; signature blocks are
never pre-filled.
"""

from harness.qms.attestation import build_attestation
from harness.qms.mappers import (
    build_change_request,
    build_vv_plan,
    build_vv_report,
)

__all__ = [
    "build_attestation",
    "build_vv_plan",
    "build_vv_report",
    "build_change_request",
]
