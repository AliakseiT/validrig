# SPDX-License-Identifier: AGPL-3.0-or-later
"""Grade a generation against a rubric, and build a judge from a spec."""

from __future__ import annotations

from validrig.judge.base import Judge
from validrig.models.pack import Case, JudgeSpec, Rubric
from validrig.models.results import Generation, Grade


def build_judge(judge_spec: JudgeSpec) -> Judge:
    if judge_spec.kind == "fake":
        from validrig.judge.fake import FakeJudge

        return FakeJudge()
    if judge_spec.kind == "openai_compat":
        from validrig.judge.llm import GradingConfig, LLMJudge
        from validrig.models.sut import SUTBinding

        binding = SUTBinding(**judge_spec.binding)
        grading_cfg = judge_spec.grading
        grading = GradingConfig(
            include_document=grading_cfg.get("include_document", True),
            include_reference=grading_cfg.get("include_reference", False),
            evaluation_steps=grading_cfg.get("evaluation_steps", {}),
        )
        return LLMJudge(binding, grading)
    raise NotImplementedError(f"judge kind '{judge_spec.kind}' not supported")


def grade_generation(
    rubric: Rubric,
    generation: Generation,
    case: Case,
    judge: Judge,
    seed: int,
    sut_kind: str = "llm_call",
) -> Grade:
    item_scores: dict[str, float] = {}
    judge_notes: dict[str, str] = {}
    item_status: dict[str, str] = {}
    document = str(case.elements.get("__document__", ""))
    for item in rubric.items:
        # A process (trace-target) rubric is only applicable to systems with an
        # observable process. For a non-agent SUT it is N/A, not a failure.
        if item.target == "trace" and sut_kind != "agent":
            item_status[item.id] = "not_applicable"
            judge_notes[item.id] = "process rubric not applicable: SUT is not an agent"
            continue
        result = judge.grade_item(
            item, document, generation.raw_output, case.ground_truth, seed,
            trace=generation.trace,
        )
        judge_notes[item.id] = result.note
        if result.is_error or result.score is None:
            # Record the error state; do NOT score it 0 (that would conflate
            # "couldn't grade" with "graded zero").
            item_status[item.id] = result.status
        else:
            item_scores[item.id] = result.score
    return Grade(
        case_id=generation.case_id,
        perturbation_id=generation.perturbation_id,
        sample_idx=generation.sample_idx,
        item_scores=item_scores,
        judge_notes=judge_notes,
        item_status=item_status,
    )
