# SPDX-License-Identifier: AGPL-3.0-or-later
"""Grade a generation against a rubric, and build a judge from a spec."""

from __future__ import annotations

from harness.judge.base import Judge
from harness.judge.fake import FakeJudge
from harness.models.pack import Case, JudgeSpec, Rubric
from harness.models.results import Generation, Grade


def build_judge(judge_spec: JudgeSpec) -> Judge:
    if judge_spec.kind == "fake":
        return FakeJudge()
    if judge_spec.kind == "openai_compat":
        from harness.judge.llm import LLMJudge  # pragma: no cover - M2+

        return LLMJudge(judge_spec)
    raise NotImplementedError(f"judge kind '{judge_spec.kind}' not supported in M1")


def grade_generation(
    rubric: Rubric,
    generation: Generation,
    case: Case,
    judge: Judge,
    seed: int,
) -> Grade:
    item_scores: dict[str, float] = {}
    judge_notes: dict[str, str] = {}
    document = str(case.elements.get("__document__", ""))
    for item in rubric.items:
        score, note = judge.grade_item(
            item, document, generation.raw_output, case.ground_truth, seed
        )
        item_scores[item.id] = score
        judge_notes[item.id] = note
    return Grade(
        case_id=generation.case_id,
        perturbation_id=generation.perturbation_id,
        sample_idx=generation.sample_idx,
        item_scores=item_scores,
        judge_notes=judge_notes,
    )
