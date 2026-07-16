# SPDX-License-Identifier: AGPL-3.0-or-later
"""Grading: an LLM-judge (or a deterministic fake) scores generations."""

from harness.judge.base import Judge
from harness.judge.fake import FakeJudge
from harness.judge.grading import build_judge, grade_generation

__all__ = ["Judge", "FakeJudge", "build_judge", "grade_generation"]
