# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ablation axis: drop one or more case elements.

Ablation is how information value is measured — remove an element and observe
what the score does. Two level styles are supported:

* explicit ``drop``: a fixed list of element names to remove.
* ``powerset``: deterministically sampled subsets of a candidate element set,
  capped by ``budget`` (no RNG, so replay is exact).
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from harness.models.pack import Case, CaseSchema
from harness.perturb.base import PerturbedCase, Transformer


def _drop_id(dropped: list[str]) -> str:
    return "ablation:none" if not dropped else "ablation:" + "-".join(sorted(dropped))


def _apply(case: Case, dropped: list[str]) -> PerturbedCase:
    dropped_sorted = sorted(dropped)
    remaining = {k: v for k, v in case.elements.items() if k not in dropped_sorted}
    new_case = case.model_copy(update={"elements": remaining})
    return PerturbedCase(
        perturbation_id=_drop_id(dropped_sorted),
        case=new_case,
        provenance={"axis": "ablation", "dropped": dropped_sorted},
    )


def _powerset_subsets(elements: list[str], budget: int) -> list[list[str]]:
    """Deterministic subsets: all non-empty combinations by ascending size then
    lexical order, truncated to ``budget``."""
    ordered = sorted(elements)
    out: list[list[str]] = []
    for size in range(1, len(ordered) + 1):
        for combo in combinations(ordered, size):
            out.append(list(combo))
            if len(out) >= budget:
                return out
    return out


class AblationTransformer(Transformer):
    axis_name = "ablation"

    def expand(
        self, case: Case, schema: CaseSchema, level_cfg: dict[str, Any]
    ) -> list[PerturbedCase]:
        if level_cfg.get("powerset"):
            budget = int(level_cfg.get("budget", 1))
            candidates = level_cfg.get("elements") or schema.element_names()
            subsets = _powerset_subsets(list(candidates), budget)
            return [_apply(case, subset) for subset in subsets]

        dropped = list(level_cfg.get("drop", []))
        return [_apply(case, dropped)]
