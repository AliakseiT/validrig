# SPDX-License-Identifier: AGPL-3.0-or-later
"""Grading: an LLM-judge (or a deterministic fake) scores generations."""

from validrig.judge.base import ItemGrade, Judge
from validrig.judge.fake import FakeJudge
from validrig.judge.grading import build_judge, grade_generation
from validrig.judge.llm import GradingConfig, LLMJudge

__all__ = [
    "Judge",
    "ItemGrade",
    "FakeJudge",
    "LLMJudge",
    "GradingConfig",
    "build_judge",
    "grade_generation",
]
