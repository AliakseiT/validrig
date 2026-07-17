# SPDX-License-Identifier: AGPL-3.0-or-later
"""Enforced ingestion pipeline: raw case -> pseudonymized, store-safe case (B1).

This is the *only* sanctioned path from raw source text into the casebank. It
enforces exactly one provable guarantee and states it in those terms — it does
**not** claim the free text is PHI-free (that is an upper bound; see the de-id
recall measurement).

Ordering is correctness-critical:

1. Capture the plaintext values of every element the pack schema marks
   ``pii="identifier"`` — BEFORE any redaction. These are the *known* identifier
   values the residual gate needs; encrypt/redact them first and the value is
   lost.
2. Hard-scrub those known values from EVERY element (exact + a punctuation-
   tolerant variant). For a known value this is direct string matching, so recall
   is ~100% — a categorically stronger claim than NER's upper bound. The only
   residual risk is formatting the tolerant pass does not model.
3. NER-pseudonymize each ``pii="free_text"`` element. ``pii="non_phi"`` elements
   pass through untouched.
4. Post-condition assertion: no known identifier survives in any element. After
   steps 2-3 this holds by construction, so a failure is a *bug* -> hard-fail the
   ingest, never write the case.

Re-identification material (the plaintext identifiers + NER re-id items) is
returned separately and must be kept hospital-side; it is never part of the
store-safe case. Durable key management / encryption-at-rest of that bundle is
tracked as a separate issue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from harness.ingest.pseudonymize import Pseudonymizer, residual_identifiers
from harness.models.pack import CaseSchema

#: The exact guarantee `harness ingest` makes. Stated everywhere the pipeline
#: reports, so the claim can never quietly widen to "no PHI".
INGEST_GUARANTEE = (
    "declared identifier fields removed; known identifiers absent from the entire "
    "persisted case (elements and ground_truth); de-identification executed on "
    "free text. NOT a claim that the free text is PHI-free (that is an upper "
    "bound — see the de-id recall record)."
)


class IngestError(RuntimeError):
    """Raised when the ingest post-condition fails — a bug, never a silent skip."""


@dataclass(frozen=True)
class IngestReport:
    case_id: str
    identifier_fields: list[str] = field(default_factory=list)
    free_text_fields: list[str] = field(default_factory=list)
    non_phi_fields: list[str] = field(default_factory=list)
    #: Distinct known identifier values captured and scrubbed.
    known_identifiers: int = 0
    #: NER entity types found across the free-text elements.
    entity_types: list[str] = field(default_factory=list)
    #: Post-condition: every known identifier is absent from every element.
    residual_clean: bool = True


def _tolerant_pattern(value: str) -> re.Pattern[str]:
    """Match ``value`` allowing punctuation/whitespace between its characters.

    So a captured ``7654321`` also catches ``765-4321`` / ``765 4321``. Errs
    toward redaction; only applied to known identifier values, never free text.
    """
    chars = [re.escape(c) for c in value if not c.isspace()]
    return re.compile(r"[\s.\-/]*".join(chars), re.IGNORECASE)


def scrub_known(text: str, values: list[str], placeholder: str = "<IDENTIFIER>") -> str:
    """Remove known identifier ``values`` from ``text`` (exact + tolerant)."""
    for v in values:
        if not v:
            continue
        text = text.replace(v, placeholder)
        text = _tolerant_pattern(v).sub(placeholder, text)
    return text


def ingest_case(
    raw_elements: dict[str, Any],
    schema: CaseSchema,
    pseudonymizer: Pseudonymizer,
    *,
    case_id: str = "",
    also_gate: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, Any], IngestReport]:
    """Pseudonymize one raw case's elements per its schema's ``pii`` classes.

    Returns ``(store_elements, reid_material, report)``. ``store_elements`` is
    safe to persist; ``reid_material`` is hospital-side only and must never be
    written to the store.

    ``also_gate`` is other content persisted alongside the elements (e.g. a
    case's ``ground_truth``): its values are covered by the residual gate but not
    transformed. A known identifier appearing there is a producer error, so it
    fails closed rather than being silently scrubbed — the gate must cover the
    whole persisted artifact, not just the elements.
    """
    id_fields, free_fields, nonphi_fields = [], [], []
    for name in raw_elements:
        spec = schema.by_name(name)
        cls = spec.pii if spec is not None else "free_text"  # unclassified -> safe default
        (id_fields if cls == "identifier" else
         nonphi_fields if cls == "non_phi" else free_fields).append(name)

    # 1. Capture plaintext identifier values BEFORE any redaction.
    known: list[str] = []
    for name in id_fields:
        val = raw_elements[name]
        if val is not None and str(val).strip():
            known.append(str(val))
    # Longest-first so a value that contains another scrubs cleanly.
    known.sort(key=len, reverse=True)

    store: dict[str, str] = {}
    reid: dict[str, Any] = {"case_id": case_id, "identifiers": {}, "ner_items": {}}
    entity_types: set[str] = set()

    for name, val in raw_elements.items():
        text = "" if val is None else str(val)
        if name in id_fields:
            # 2a. The whole value is an identifier: it becomes a placeholder; the
            #     plaintext goes hospital-side for re-identification.
            reid["identifiers"][name] = text
            store[name] = f"<IDENTIFIER:{name}>"
        elif name in nonphi_fields:
            store[name] = text  # declared non-identifying -> passthrough
        else:
            # 2b + 3. Scrub known identifiers, then NER-pseudonymize.
            scrubbed = scrub_known(text, known)
            result = pseudonymizer.pseudonymize(scrubbed)
            store[name] = result.text
            entity_types.update(result.entity_types)
            if result.reid_material is not None:
                reid["ner_items"][name] = result.reid_material

    # 4. Post-condition: no known identifier survives anywhere in the persisted
    #    artifact — the elements AND anything gated alongside them (ground_truth).
    #    By construction after step 2 for elements; for also_gate a hit means the
    #    producer put an identifier in a non-transformed field. Either way it is a
    #    bug, so refuse to emit the case.
    gate_targets = dict(store)
    for k, v in (also_gate or {}).items():
        gate_targets[f"ground_truth.{k}"] = "" if v is None else str(v)
    leaks = {n: residual_identifiers(t, known) for n, t in gate_targets.items()}
    residual_clean = not any(leaks.values())
    if not residual_clean:
        offending = {n: v for n, v in leaks.items() if v}
        raise IngestError(
            f"known identifier(s) survived pseudonymization in case '{case_id}': "
            f"{offending} — refusing to write the case (this is a bug)"
        )

    report = IngestReport(
        case_id=case_id,
        identifier_fields=sorted(id_fields),
        free_text_fields=sorted(free_fields),
        non_phi_fields=sorted(nonphi_fields),
        known_identifiers=len(known),
        entity_types=sorted(entity_types),
        residual_clean=residual_clean,
    )
    return store, reid, report
