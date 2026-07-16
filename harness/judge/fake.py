# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic fake judge.

Like the fake model, this exists so the pipeline runs and is testable offline,
and so determinism can be asserted. It is a pure function of its inputs: it
scores a rubric item by checking whether the item's adjudicated evidence (from
the case's ground truth) appears in the SUT output. It contains no use-case
knowledge — the evidence comes entirely from pack content.
"""

from __future__ import annotations

from typing import Any

from harness.judge.base import Judge
from harness.models.pack import RubricItem


class FakeJudge(Judge):
    def grade_item(
        self,
        item: RubricItem,
        document: str,
        output: str,
        ground_truth: dict[str, Any],
        seed: int,
    ) -> tuple[float, str]:
        spec = ground_truth.get(item.id) or {}
        evidence = [str(e) for e in spec.get("evidence", [])]
        haystack = output.lower()
        found = [e for e in evidence if e.lower() in haystack]

        if not evidence:
            return 0.0, f"no adjudicated evidence for {item.id}; scored 0"
        if found:
            return item.max_score, f"found evidence: {', '.join(found)}"
        return 0.0, f"missing evidence: {', '.join(evidence)}"
