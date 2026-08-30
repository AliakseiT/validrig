# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ingestion boundary: pseudonymize source text before it reaches the engine.

This is the ONLY place that ever sees raw identifiers. Downstream (casebank, run
store) sees only pseudonymized text; the re-identification material stays
hospital-side and is never persisted by the engine.

Lightweight-first: the default backend uses Microsoft Presidio in a lightweight
configuration (a small spaCy model + regex pattern recognizers, no heavy
HF/transformer models), which reliably catches *structured* PII (emails, phones,
IDs, dates) and basic free-text names/locations. It **establishes the boundary
and the reversible-pseudonymization contract**; it is NOT a validated de-identifier
for clinical free text — higher recall (a domain NER model such as OpenMed) is a
deliberate, measured next step, taken only if the recall gap justifies it.
"""

from validrig.ingest.pseudonymize import (
    Pseudonymizer,
    PseudonymizationResult,
    residual_identifiers,
)

__all__ = ["Pseudonymizer", "PseudonymizationResult", "residual_identifiers"]
