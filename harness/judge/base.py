# SPDX-License-Identifier: AGPL-3.0-or-later
"""Judge interface.

A judge grades one generation against one rubric item and returns an
``ItemGrade``: a numeric score with a note, or an explicit ``judge_error`` state
when it could not grade at all. The error state is deliberately distinct from a
score of 0 — "couldn't grade" and "graded zero" mean different things, and
folding them together would corrupt metrics and could falsely fail acceptance.

The judge model is pinned and versioned like any SUT: a judge upgrade is a
revalidation event. Because the loader hashes the full pack (including
``judge.yaml``) into ``pack_hash``, and ``pack_hash`` is part of ``Pins``, any
change to the judge model or grading prompt already flows through to a new
``run_id`` — no extra versioning machinery is needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from harness.models.pack import RubricItem

STATUS_GRADED = "graded"
STATUS_JUDGE_ERROR = "judge_error"
STATUS_NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ItemGrade:
    """Result of grading one rubric item.

    ``score`` is ``None`` iff ``status == judge_error``.
    """

    score: float | None
    note: str
    status: str = STATUS_GRADED

    @property
    def is_error(self) -> bool:
        return self.status == STATUS_JUDGE_ERROR

    @classmethod
    def graded(cls, score: float, note: str) -> "ItemGrade":
        return cls(score=score, note=note, status=STATUS_GRADED)

    @classmethod
    def error(cls, note: str) -> "ItemGrade":
        return cls(score=None, note=note, status=STATUS_JUDGE_ERROR)

    @classmethod
    def not_applicable(cls, note: str) -> "ItemGrade":
        return cls(score=None, note=note, status=STATUS_NOT_APPLICABLE)


class Judge(ABC):
    #: Whether grades from this judge are safe to use as a regression baseline.
    #: Live LLM judges are non-reproducible; their grades must be recorded once
    #: and replayed, never re-invoked.
    reproducible: bool = True

    @abstractmethod
    def grade_item(
        self,
        item: RubricItem,
        document: str,
        output: str,
        ground_truth: dict[str, Any],
        seed: int,
        trace: dict[str, Any] | None = None,
    ) -> ItemGrade:
        """Return an ``ItemGrade`` for ``item``.

        For an output-target item this grades ``output``; for a trace-target
        (process) item it grades ``trace`` (the agent's observable steps).
        """
        raise NotImplementedError
