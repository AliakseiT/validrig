# SPDX-License-Identifier: AGPL-3.0-or-later
"""InputContract extraction.

The input contract is the product's core derived artifact: for a given system
under test, which input elements it actually relies on, how much each one
contributes, and where its failures are dangerous. It contains only element
*names* and aggregate statistics — never case content — so it is safe to export
and, later, to aggregate across sites.
"""

from __future__ import annotations

from typing import Any

from harness.models.pack import CaseSchema
from harness.models.results import Pins

#: An element is treated as part of the minimal sufficient set if ablating it
#: drops the mean score by at least this much.
DEFAULT_NECESSITY_DELTA = 0.05


def extract_contract(
    pins: Pins,
    information_value: dict[str, float],
    critical: dict[str, Any],
    schema: CaseSchema,
    necessity_delta: float = DEFAULT_NECESSITY_DELTA,
) -> dict[str, Any]:
    elements = []
    for spec in schema.elements:
        measured = spec.name in information_value
        elements.append(
            {
                "name": spec.name,
                "modality": spec.modality,
                "language": spec.language,
                "required": spec.required,
                # An element is "measured" only if it was ablated in isolation.
                # A bundled-only or never-dropped element is unknown, not zero —
                # this distinction is load-bearing for regression diffs, which
                # must tell "newly stopped using" apart from "never measured".
                "measured": measured,
                "information_value": round(information_value[spec.name], 6) if measured else None,
            }
        )

    minimal_sufficient_set = sorted(
        name
        for name, iv in information_value.items()
        if iv >= necessity_delta
    )

    return {
        "artifact_type": "input_contract",
        "schema_version": 1,
        "pins": pins.model_dump(mode="json"),
        "elements": elements,
        "minimal_sufficient_set_candidate": minimal_sufficient_set,
        "necessity_delta": necessity_delta,
        "critical_omission_rate": critical.get("critical_omission_rate"),
    }
