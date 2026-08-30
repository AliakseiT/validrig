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

from validrig.judge.base import ItemGrade, Judge
from validrig.models.pack import RubricItem


class FakeJudge(Judge):
    reproducible = True

    def grade_item(
        self,
        item: RubricItem,
        document: str,
        output: str,
        ground_truth: dict[str, Any],
        seed: int,
        trace: dict[str, Any] | None = None,
    ) -> ItemGrade:
        spec = ground_truth.get(item.id) or {}
        if item.target == "trace":
            return self._grade_trace(item, spec, trace or {})

        evidence = [str(e) for e in spec.get("evidence", [])]
        haystack = output.lower()
        found = [e for e in evidence if e.lower() in haystack]

        if not evidence:
            return ItemGrade.graded(0.0, f"no adjudicated evidence for {item.id}; scored 0")
        if found:
            return ItemGrade.graded(item.max_score, f"found evidence: {', '.join(found)}")
        return ItemGrade.graded(0.0, f"missing evidence: {', '.join(evidence)}")

    def _grade_trace(self, item, spec, trace) -> ItemGrade:
        """Process rubric: were the required tools actually called (successfully)?"""
        required = [str(t) for t in spec.get("required_tools", [])]
        steps = trace.get("steps", [])
        # An agent that called no tools has an empty trace here — that is a
        # process FAILURE (it should have called the tool), not "not applicable".
        # Applicability (agent vs non-agent SUT) is decided in grade_generation.
        called_ok = {
            s.get("name")
            for s in steps
            if not (s.get("data") or {}).get("error")
        }
        missing = [t for t in required if t not in called_ok]
        if not required:
            return ItemGrade.graded(0.0, f"no required_tools declared for {item.id}; scored 0")
        if not missing:
            return ItemGrade.graded(item.max_score, f"required tools called: {', '.join(required)}")
        return ItemGrade.graded(0.0, f"required tool(s) not called: {', '.join(missing)}")
