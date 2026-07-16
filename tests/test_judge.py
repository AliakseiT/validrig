# SPDX-License-Identifier: AGPL-3.0-or-later
from harness.models.pack import Case, RubricItem, Rubric
from harness.models.results import Generation, TokenUsage
from harness.judge.fake import FakeJudge
from harness.judge.grading import build_judge, grade_generation
from harness.models.pack import JudgeSpec


def _item():
    return RubricItem(
        id="item_molecular",
        statement="reports molecular alteration",
        type="binary",
        grading_instructions="score 1 if present",
        max_score=1.0,
    )


def _gt():
    return {"item_molecular": {"evidence": ["EGFR"], "expected": True}}


def test_fake_judge_deterministic():
    j = FakeJudge()
    a = j.grade_item(_item(), "doc", "output mentions EGFR", _gt(), seed=0)
    b = j.grade_item(_item(), "doc", "output mentions EGFR", _gt(), seed=0)
    assert a == b


def test_present_evidence_scores_higher_than_absent():
    j = FakeJudge()
    present = j.grade_item(_item(), "doc", "the EGFR deletion", _gt(), seed=0)
    absent = j.grade_item(_item(), "doc", "nothing relevant here", _gt(), seed=0)
    assert present.score > absent.score
    assert present.score == 1.0
    assert absent.score == 0.0
    assert present.status == "graded"


def test_case_insensitive_match():
    j = FakeJudge()
    result = j.grade_item(_item(), "doc", "found egfr lowercase", _gt(), seed=0)
    assert result.score == 1.0


def test_grade_generation_scores_every_item():
    rubric = Rubric(items=[_item(), RubricItem(
        id="item_staging", statement="s", type="binary",
        grading_instructions="g", max_score=1.0)])
    case = Case(case_id="C", elements={}, ground_truth={
        "item_molecular": {"evidence": ["EGFR"], "expected": True},
        "item_staging": {"evidence": ["cT2N1M0"], "expected": True},
    })
    gen = Generation(
        case_id="C", perturbation_id="p", sample_idx=0,
        raw_output="EGFR present but stage missing", trace={},
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    grade = grade_generation(rubric, gen, case, FakeJudge(), seed=0)
    assert set(grade.item_scores.keys()) == {"item_molecular", "item_staging"}
    assert grade.item_scores["item_molecular"] == 1.0
    assert grade.item_scores["item_staging"] == 0.0


def test_build_judge_from_spec():
    j = build_judge(JudgeSpec(id="x", version="1", kind="fake"))
    assert isinstance(j, FakeJudge)
