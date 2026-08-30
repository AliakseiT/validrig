# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent-specific perturbation axes: the tool environment, not the document.

Unlike ablation/format/language (which rewrite the case), these axes perturb the
*tool environment* an agent runs against, to measure whether it compensates or
hallucinates when a tool is removed or degraded (design doc §3):

* ``tool_availability`` — make one or more tools unavailable.
* ``tool_response`` — inject a degraded response (error / empty) for one tool.

They are transformers so they compose in the existing battery expansion and are
selectable via a battery's axis allowlist. They leave the case unchanged and
record the perturbation in provenance; the executor threads it to the agent
adapter via ``SUTContext.tool_perturbation``.
"""

from __future__ import annotations

from typing import Any

from validrig.models.pack import Case, CaseSchema
from validrig.perturb.base import PerturbedCase, Transformer


class ToolAvailabilityTransformer(Transformer):
    axis_name = "tool_availability"

    def expand(
        self, case: Case, schema: CaseSchema, level_cfg: dict[str, Any]
    ) -> list[PerturbedCase]:
        removed = sorted(str(t) for t in level_cfg.get("remove", []))
        label = "-".join(removed) if removed else "all"
        return [
            PerturbedCase(
                perturbation_id=f"tool_availability:{label}",
                case=case,  # document unchanged; this axis perturbs the environment
                provenance={"axis": "tool_availability", "removed": removed},
            )
        ]


class ToolResponseTransformer(Transformer):
    axis_name = "tool_response"

    def expand(
        self, case: Case, schema: CaseSchema, level_cfg: dict[str, Any]
    ) -> list[PerturbedCase]:
        mode = str(level_cfg.get("mode", "normal"))
        tool = level_cfg.get("tool")
        if mode == "normal" or tool is None:
            perturbation_id = "tool_response:normal"
            provenance = {"axis": "tool_response", "tool": None, "mode": "normal"}
        else:
            perturbation_id = f"tool_response:{mode}:{tool}"
            provenance = {"axis": "tool_response", "tool": str(tool), "mode": mode}
        return [
            PerturbedCase(perturbation_id=perturbation_id, case=case, provenance=provenance)
        ]
