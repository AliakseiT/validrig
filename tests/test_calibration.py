# SPDX-License-Identifier: AGPL-3.0-or-later
from validrig.calibration.agreement import cohen_kappa, compute_agreement
from validrig.calibration.gate import evaluate_gate
from validrig.calibration.models import HumanGrade
from validrig.calibration.sample import select_calibration_sample
from validrig.calibration.store import CalibrationStore
from validrig.models.results import Grade


def _keys(n):
    return [("C%d" % i, "ablation:none|format:structured", 0) for i in range(n)]


def test_sample_is_deterministic_and_sized():
    keys = _keys(20)
    a = select_calibration_sample(keys, 0.1, seed=1)
    b = select_calibration_sample(keys, 0.1, seed=1)
    assert a == b
    assert len(a) == 2  # ceil(0.1 * 20)
    assert set(a) <= set(keys)


def test_sample_seed_changes_selection():
    keys = _keys(50)
    assert select_calibration_sample(keys, 0.1, seed=1) != select_calibration_sample(keys, 0.1, seed=2)


def test_sample_at_least_one_and_empty():
    assert len(select_calibration_sample(_keys(3), 0.01, seed=0)) == 1
    assert select_calibration_sample([], 0.5, seed=0) == []


def test_cohen_kappa_perfect_and_none():
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert cohen_kappa([], []) is None


def test_cohen_kappa_partial():
    # 3/4 agree, some disagreement -> kappa between 0 and 1
    k = cohen_kappa([1, 1, 0, 0], [1, 1, 1, 0])
    assert -1.0 <= k < 1.0


def test_store_round_trip_append_only(tmp_path):
    store = CalibrationStore(tmp_path)
    hg = HumanGrade(
        run_id="R", case_id="C1", perturbation_id="p", sample_idx=0,
        grader_id="dr_x", item_scores={"item_diagnosis": 1.0}, created_at="2026-07-16",
    )
    store.append_human_grade(hg)
    got = store.read_human_grades("R")
    assert got == [hg]
    assert store.graded_keys("R") == {("C1", "p", 0)}


def _judge_grade(key, scores):
    return Grade(case_id=key[0], perturbation_id=key[1], sample_idx=key[2],
                 item_scores=scores, judge_notes={})


def test_agreement_and_gate_pass(tmp_path):
    # judge and human agree on 12 observations -> kappa 1.0 -> pass
    judge, human = [], []
    for i in range(12):
        key = ("C%d" % i, "p", 0)
        judge.append(_judge_grade(key, {"item_diagnosis": 1.0}))
        human.append(HumanGrade(run_id="R", case_id=key[0], perturbation_id="p",
                                sample_idx=0, grader_id="dr_x", item_scores={"item_diagnosis": 1.0}))
    agreement = compute_agreement(judge, human)
    assert agreement["items"]["item_diagnosis"]["n"] == 12
    assert agreement["items"]["item_diagnosis"]["kappa"] == 1.0
    gate = evaluate_gate(agreement, kappa_min=0.6, min_n=10)
    assert gate["status"] == "pass"
    assert gate["blocks_report_issuance"] is False


def test_gate_blocks_on_disagreement(tmp_path):
    # judge says pass on all; human disagrees on ~half -> low kappa -> block
    judge, human = [], []
    for i in range(12):
        key = ("C%d" % i, "p", 0)
        judge.append(_judge_grade(key, {"item_diagnosis": 1.0}))
        hscore = 1.0 if i % 2 == 0 else 0.0
        human.append(HumanGrade(run_id="R", case_id=key[0], perturbation_id="p",
                                sample_idx=0, grader_id="dr_x", item_scores={"item_diagnosis": hscore}))
    gate = evaluate_gate(compute_agreement(judge, human), kappa_min=0.6, min_n=10)
    assert gate["status"] == "block"
    assert gate["blocks_report_issuance"] is True


def test_gate_low_n_is_advisory_not_block():
    judge = [_judge_grade(("C0", "p", 0), {"item_diagnosis": 1.0})]
    human = [HumanGrade(run_id="R", case_id="C0", perturbation_id="p", sample_idx=0,
                        grader_id="dr_x", item_scores={"item_diagnosis": 0.0})]  # disagree, but n=1
    gate = evaluate_gate(compute_agreement(judge, human), kappa_min=0.6, min_n=10)
    assert gate["status"] == "advisory_low_n"
    assert gate["blocks_report_issuance"] is False


def test_regrade_does_not_double_count():
    # Grade a unit, then re-grade the SAME unit with the opposite label. The
    # correction must replace, not accumulate: n stays 1 and reflects the latest.
    key = ("C0", "p", 0)
    judge = [_judge_grade(key, {"item_diagnosis": 1.0})]
    human = [
        HumanGrade(run_id="R", case_id="C0", perturbation_id="p", sample_idx=0,
                   grader_id="dr_x", item_scores={"item_diagnosis": 0.0}),  # first: disagree
        HumanGrade(run_id="R", case_id="C0", perturbation_id="p", sample_idx=0,
                   grader_id="dr_x", item_scores={"item_diagnosis": 1.0}),  # re-grade: agree
    ]
    agreement = compute_agreement(judge, human)
    stats = agreement["items"]["item_diagnosis"]
    assert stats["n"] == 1  # not 2
    assert stats["percent_agreement"] == 1.0  # reflects the corrected (agreeing) label


def test_regrade_by_different_grader_counts_separately():
    key = ("C0", "p", 0)
    judge = [_judge_grade(key, {"item_diagnosis": 1.0})]
    human = [
        HumanGrade(run_id="R", case_id="C0", perturbation_id="p", sample_idx=0,
                   grader_id="dr_x", item_scores={"item_diagnosis": 1.0}),
        HumanGrade(run_id="R", case_id="C0", perturbation_id="p", sample_idx=0,
                   grader_id="dr_y", item_scores={"item_diagnosis": 1.0}),
    ]
    assert compute_agreement(judge, human)["items"]["item_diagnosis"]["n"] == 2


def test_judge_error_item_excluded_from_agreement():
    # judge could not grade the item (absent) -> not counted
    judge = [Grade(case_id="C0", perturbation_id="p", sample_idx=0,
                   item_scores={}, judge_notes={}, item_status={"item_diagnosis": "judge_error"})]
    human = [HumanGrade(run_id="R", case_id="C0", perturbation_id="p", sample_idx=0,
                        grader_id="dr_x", item_scores={"item_diagnosis": 1.0})]
    agreement = compute_agreement(judge, human)
    assert agreement["overall"]["n"] == 0
