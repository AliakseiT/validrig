# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calibration record model.

A ``HumanGrade`` is one clinician's grade of one generation against the rubric,
stored append-only and attributed to a grader — the QMS-grade evidence of a
double-grading. It mirrors the shape of a judge ``Grade`` but is kept separate so
the immutable judge grades are never touched.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HumanGrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    case_id: str
    perturbation_id: str
    sample_idx: int
    grader_id: str
    item_scores: dict[str, float]
    note: str = ""
    created_at: str = ""  # injected timestamp; run metadata, not content

    def content_key(self) -> tuple[str, str, int]:
        return (self.case_id, self.perturbation_id, self.sample_idx)
