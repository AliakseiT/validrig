# SPDX-License-Identifier: AGPL-3.0-or-later
"""Immutable, version-pinned result records — the versioning spine.

Every result carries the full set of pins (pack, battery, SUT, judge, seed,
engine) so any number in a report is traceable back to the exact inputs that
produced it. Content records (``Generation``, ``Grade``) hold no wall-clock
time or environment data; those live only in ``RunMeta``. This separation is
what lets determinism checks and regression diffs compare *content* without a
timestamp making every comparison fail.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from harness.hashing import content_hash


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class TokenUsage(_Frozen):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_chf: float = 0.0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_chf=self.cost_chf + other.cost_chf,
        )

    @staticmethod
    def zero() -> "TokenUsage":
        return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_chf=0.0)


class Pins(_Frozen):
    """The complete provenance of a run. Its content hash *is* the run id."""

    pack_id: str
    pack_version: str
    pack_hash: str
    battery_id: str
    battery_version: str
    sut_id: str
    sut_hash: str
    judge_id: str | None
    judge_version: str | None
    seed: int
    engine_version: str


class RunMeta(_Frozen):
    """Run metadata that is deliberately excluded from content comparisons."""

    run_id: str
    timestamp: str
    env_hash: str


class Generation(_Frozen):
    """A single SUT generation. Content only — no timestamp, no environment."""

    case_id: str
    perturbation_id: str
    sample_idx: int
    raw_output: str
    trace: dict[str, Any]
    usage: TokenUsage


class Grade(_Frozen):
    """Judge scores for one generation against the rubric. Content only."""

    case_id: str
    perturbation_id: str
    sample_idx: int
    item_scores: dict[str, float]
    judge_notes: dict[str, str]
    human_agreement: dict[str, bool] | None = None


class Run(_Frozen):
    pins: Pins
    meta: RunMeta


def run_id_for(pins: Pins) -> str:
    """Deterministic run id: first 16 hex chars of the pins content hash."""
    return content_hash(pins.model_dump(mode="json"))[:16]


def content_key(record: Generation | Grade) -> tuple[str, str, int]:
    """Stable identity of a content record within a run."""
    return (record.case_id, record.perturbation_id, record.sample_idx)
