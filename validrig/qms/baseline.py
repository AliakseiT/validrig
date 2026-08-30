# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reference to the QMS baseline revision these mappers target.

Recording the exact upstream baseline tag and per-template ``version:`` in every
emitted record makes each artifact self-identify which controlled-document
revision it was generated against — a prerequisite for change control when the
baseline itself is revised.
"""

from __future__ import annotations

# DearAuditor Open QMS Baseline formal release these mappers were built against.
QMS_BASELINE_TAG = "QMS-2026-07-09-R005"
QMS_BASELINE_REPO = "AliakseiT/dearauditor-qms-baseline"

# Template ``version:`` fields as declared in the r05 templates.
TEMPLATE_VERSIONS = {
    "verification_validation_plan": 1,  # records/verification_validation/vv_plan_template.yml
    "verification_validation_report": 1,  # records/verification_validation/vv_report_template.md
    "change_request": 1,  # records/change/change_request_template.md (unversioned md)
}

# Source template paths in the baseline repo, for traceability.
TEMPLATE_SOURCES = {
    "verification_validation_plan": "records/verification_validation/vv_plan_template.yml",
    "verification_validation_report": "records/verification_validation/vv_report_template.md",
    "change_request": "records/change/change_request_template.md",
}
