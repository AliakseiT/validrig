# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production event model — deliberately aggregate-safe (no PHI).

A production event records only which contract elements were *present* in a
production input and whether the clinician *overrode* the output. There is no
case content, so the monitoring log is safe to aggregate and export.

``elements_present`` is three-state by construction: a key set ``true``/``false``
means the element was logged present/absent; a key that is *absent from the dict*
means presence was not logged (unknown) and is excluded from completeness — never
counted as absent.

``extra="forbid"`` rejects any unexpected field, so an event that tried to carry
free-text (potential PHI) fails validation rather than being silently stored.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProductionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str
    elements_present: dict[str, bool] = Field(default_factory=dict)
    overridden: bool = False

    def is_logged(self, element: str) -> bool:
        return element in self.elements_present
