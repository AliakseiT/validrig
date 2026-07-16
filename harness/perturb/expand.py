# SPDX-License-Identifier: AGPL-3.0-or-later
"""Battery expansion: turn a declarative battery into concrete work units.

The engine composes the declared perturbation axes in declaration order and
takes their cartesian product, so each unit carries a fully-perturbed, rendered
document plus the provenance of every axis that shaped it. Axis order matters:
mutation axes (e.g. ablation) are declared before the rendering axis (format), so
that rendering sees the already-reduced element set.

Expansion is deterministic — cases, axis levels, SUTs, and samples are all
iterated in a fixed, sorted order — which is what lets a battery serve as a
stable regression baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.models.pack import BatterySpec, Case, Pack
from harness.perturb.base import PerturbedCase, get_transformer
from harness.perturb.format import DOCUMENT_KEY, FormatTransformer


@dataclass(frozen=True)
class ExpansionUnit:
    case_id: str
    perturbation_id: str
    sample_idx: int
    sut_id: str
    document: str
    provenance: dict[str, Any] = field(default_factory=dict)


def _join_ids(existing: str, new: str) -> str:
    return new if not existing else f"{existing}|{new}"


def _selected_cases(pack: Pack, battery: BatterySpec) -> list[Case]:
    if battery.cases == "all":
        return sorted(pack.cases, key=lambda c: c.case_id)
    wanted = set(battery.cases)
    return [c for c in sorted(pack.cases, key=lambda c: c.case_id) if c.case_id in wanted]


def _perturbed_states(pack: Pack, case: Case) -> list[PerturbedCase]:
    """Cartesian product of all declared axis levels for one case."""
    schema = pack.case_schema
    states = [PerturbedCase(perturbation_id="", case=case, provenance={})]
    for axis_name, levels in pack.perturbations.axes.items():
        transformer = get_transformer(axis_name)
        next_states: list[PerturbedCase] = []
        for state in states:
            for level in levels:
                for pc in transformer.expand(state.case, schema, level):
                    merged_prov = dict(state.provenance)
                    merged_prov[axis_name] = pc.provenance
                    next_states.append(
                        PerturbedCase(
                            perturbation_id=_join_ids(state.perturbation_id, pc.perturbation_id),
                            case=pc.case,
                            provenance=merged_prov,
                        )
                    )
        states = next_states
    return states


def _ensure_document(pack: Pack, state: PerturbedCase) -> str:
    """Return the rendered document, falling back to a structured render if no
    axis produced one (e.g. a pack with no format axis declared)."""
    doc = state.case.elements.get(DOCUMENT_KEY)
    if doc is not None:
        return str(doc)
    rendered = FormatTransformer().expand(state.case, pack.case_schema, {"style": "structured"})
    return str(rendered[0].case.elements[DOCUMENT_KEY])


def _perturbation_selected(perturbation_id: str, battery: BatterySpec) -> bool:
    if battery.perturbations == "all":
        return True
    return perturbation_id in set(battery.perturbations)


def expand_battery(pack: Pack, battery: BatterySpec) -> list[ExpansionUnit]:
    if battery is None:
        raise ValueError("battery is None")

    units: list[ExpansionUnit] = []
    seen: set[tuple[str, str, int, str]] = set()

    for case in _selected_cases(pack, battery):
        for state in _perturbed_states(pack, case):
            if not _perturbation_selected(state.perturbation_id, battery):
                continue
            document = _ensure_document(pack, state)
            for sut_id in sorted(battery.suts):
                for sample_idx in range(battery.n_samples):
                    key = (case.case_id, state.perturbation_id, sample_idx, sut_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    units.append(
                        ExpansionUnit(
                            case_id=case.case_id,
                            perturbation_id=state.perturbation_id,
                            sample_idx=sample_idx,
                            sut_id=sut_id,
                            document=document,
                            provenance=state.provenance,
                        )
                    )

    units.sort(key=lambda u: (u.case_id, u.perturbation_id, u.sut_id, u.sample_idx))
    return units
