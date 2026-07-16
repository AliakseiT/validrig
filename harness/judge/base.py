# SPDX-License-Identifier: AGPL-3.0-or-later
"""Judge interface.

A judge grades one generation against one rubric item and returns a numeric
score plus a short note. The judge model is pinned and versioned like any SUT: a
judge upgrade is a revalidation event.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from harness.models.pack import RubricItem


class Judge(ABC):
    @abstractmethod
    def grade_item(
        self,
        item: RubricItem,
        document: str,
        output: str,
        ground_truth: dict[str, Any],
        seed: int,
    ) -> tuple[float, str]:
        """Return ``(score, note)`` for ``item`` given the SUT ``output``."""
        raise NotImplementedError
