# SPDX-License-Identifier: AGPL-3.0-or-later
"""Format axis: render a case's elements into a single prompt-ready document.

The same information can be presented as a raw text dump, as labeled structured
sections, or as a key/value table. The format axis lets a harness measure how
sensitive a system is to presentation. Rendering is deterministic and follows
the schema's element declaration order. The rendered text is stored under the
reserved ``__document__`` key so downstream execution has a single string to send.
"""

from __future__ import annotations

from typing import Any

from harness.models.pack import Case, CaseSchema
from harness.perturb.base import PerturbedCase, Transformer

DOCUMENT_KEY = "__document__"


def _ordered_items(case: Case, schema: CaseSchema) -> list[tuple[str, str]]:
    """Element (name, value) pairs in schema declaration order, present only."""
    items: list[tuple[str, str]] = []
    for spec in schema.elements:
        if spec.name in case.elements:
            items.append((spec.name, str(case.elements[spec.name])))
    return items


def _render_raw_dump(items: list[tuple[str, str]]) -> str:
    return "\n\n".join(value for _, value in items)


def _render_structured(items: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"## {name}\n{value}" for name, value in items)


def _render_tabular(items: list[tuple[str, str]]) -> str:
    lines = ["| element | content |", "| --- | --- |"]
    for name, value in items:
        cell = value.replace("\n", " ")
        lines.append(f"| {name} | {cell} |")
    return "\n".join(lines)


_RENDERERS = {
    "raw_dump": _render_raw_dump,
    "structured": _render_structured,
    "tabular": _render_tabular,
}


class FormatTransformer(Transformer):
    axis_name = "format"

    def expand(
        self, case: Case, schema: CaseSchema, level_cfg: dict[str, Any]
    ) -> list[PerturbedCase]:
        style = level_cfg.get("style", "structured")
        if style not in _RENDERERS:
            raise ValueError(f"unknown format style '{style}'")
        items = _ordered_items(case, schema)
        document = _RENDERERS[style](items)
        new_elements = dict(case.elements)
        new_elements[DOCUMENT_KEY] = document
        new_case = case.model_copy(update={"elements": new_elements})
        return [
            PerturbedCase(
                perturbation_id=f"format:{style}",
                case=new_case,
                provenance={"axis": "format", "style": style},
            )
        ]
