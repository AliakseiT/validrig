# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lint a loaded pack for authoring gaps.

Errors are things that make the pack unable to grade properly (a rubric item with
no grading instructions). Warnings are coverage gaps — a case or critical item
with no physician adjudication. A gap is reported as a gap, never silently
treated as an adjudicated zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from validrig.models.pack import Pack

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class LintFinding:
    severity: str
    code: str
    message: str


def lint_pack(pack: Pack) -> list[LintFinding]:
    findings: list[LintFinding] = []

    for item in pack.rubric.items:
        if not item.statement.strip():
            findings.append(
                LintFinding(ERROR, "rubric-item-no-statement",
                            f"rubric item '{item.id}' has no statement")
            )
        if not item.grading_instructions.strip():
            findings.append(
                LintFinding(ERROR, "rubric-item-no-grading-instructions",
                            f"rubric item '{item.id}' has no grading instructions")
            )

    if not pack.cases:
        findings.append(LintFinding(WARNING, "no-cases", "pack has no cases"))

    adjudicated = {a.case_id: a for a in pack.adjudications}
    critical_ids = [i.id for i in pack.rubric.items if i.critical]

    for case in pack.cases:
        adj = adjudicated.get(case.case_id)
        if adj is None:
            findings.append(
                LintFinding(WARNING, "case-no-adjudication",
                            f"case '{case.case_id}' has no physician adjudication")
            )
            continue
        for cid in critical_ids:
            if cid not in adj.values:
                findings.append(
                    LintFinding(WARNING, "critical-not-adjudicated",
                                f"critical item '{cid}' not adjudicated for case '{case.case_id}'")
                )

    return findings


def has_errors(findings: list[LintFinding]) -> bool:
    return any(f.severity == ERROR for f in findings)
