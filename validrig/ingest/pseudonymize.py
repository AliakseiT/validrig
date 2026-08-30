# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pseudonymization contract.

A ``Pseudonymizer`` turns raw text into store-safe pseudonymized text plus
*re-identification material* that is returned separately and must be kept
hospital-side — the engine store only ever receives ``result.text``, never
``result.reid_material``. That separation is the boundary invariant.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PseudonymizationResult:
    #: Pseudonymized text — safe to persist in the casebank / run store.
    text: str
    #: Entity types detected and replaced (e.g. PERSON, EMAIL_ADDRESS).
    entity_types: list[str] = field(default_factory=list)
    #: Whether re-identification is possible (with the hospital-side secret).
    reversible: bool = False
    #: Material needed to re-identify (keys/spans/mapping). HOSPITAL-SIDE ONLY —
    #: the engine must never persist this. ``None`` for one-way pseudonymization.
    reid_material: Any = None


class Pseudonymizer(ABC):
    @abstractmethod
    def pseudonymize(self, text: str) -> PseudonymizationResult:
        """Return store-safe pseudonymized text + separate re-id material."""
        raise NotImplementedError

    def reidentify(self, result: PseudonymizationResult) -> str:
        """Recover the original text (hospital-side, with the secret)."""
        raise NotImplementedError("this pseudonymizer is not reversible")


def residual_identifiers(text: str, identifiers: list[str]) -> list[str]:
    """Return any known identifier still present in ``text`` (case-insensitive).

    The boundary check: after pseudonymization, this must be empty for the
    identifiers you know about. It does not prove completeness — that is what the
    recall measurement (and, if needed, a stronger NER model) is for.
    """
    low = text.lower()
    return [i for i in identifiers if i and i.lower() in low]
