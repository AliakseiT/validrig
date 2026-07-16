# SPDX-License-Identifier: AGPL-3.0-or-later
"""RegressionDiff: prove the diff names a known regression precisely.

The demo pack ships a deliberately-regressed SUT (``fake-regressed``) that has
"stopped reporting molecular findings". The diff must surface that at both
(case, perturbation, rubric-item) granularity and per-element contract
granularity — not merely as an aggregate score drop.
"""

from pathlib import Path

from harness.diff import diff_runs
from harness.execute import run_battery
from harness.packio.loader import load_pack
from harness.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "hello-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _run_regression(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    results = run_battery(pack, "regression", store, seed=1, now=CLOCK)
    by_sut = {r.sut_id: r for r in results}
    return store, by_sut["fake-baseline"].run_id, by_sut["fake-regressed"].run_id


def test_item_level_regression_is_surfaced(tmp_path):
    store, baseline_id, candidate_id = _run_regression(tmp_path)
    diff = diff_runs(store, baseline_id, candidate_id)

    molecular_regressions = [
        d for d in diff["item_deltas"]
        if d["item_id"] == "item_molecular" and d["delta"] < 0
    ]
    # every unit that still contained molecular evidence should regress
    assert len(molecular_regressions) > 0
    # the diff pinpoints case + perturbation, not just an aggregate
    sample = molecular_regressions[0]
    assert sample["case_id"] in {"C001", "C002", "C003"}
    assert "perturbation_id" in sample
    assert sample["score_baseline"] == 1.0
    assert sample["score_candidate"] == 0.0


def test_diagnosis_and_staging_do_not_regress(tmp_path):
    store, baseline_id, candidate_id = _run_regression(tmp_path)
    diff = diff_runs(store, baseline_id, candidate_id)
    for d in diff["item_deltas"]:
        if d["item_id"] in {"item_diagnosis", "item_staging"}:
            assert d["delta"] >= 0


def test_element_contract_delta_is_surfaced(tmp_path):
    store, baseline_id, candidate_id = _run_regression(tmp_path)
    diff = diff_runs(store, baseline_id, candidate_id)
    by_elem = {d["element"]: d for d in diff["element_deltas"]}
    mol = by_elem["molecular_report"]
    # the model no longer relies on molecular_report: its information value falls
    assert mol["iv_baseline"] > 0
    assert mol["iv_candidate"] == 0.0
    assert mol["delta"] < 0
    assert mol["status"] == "changed"


def test_aggregate_regression_is_significant(tmp_path):
    store, baseline_id, candidate_id = _run_regression(tmp_path)
    diff = diff_runs(store, baseline_id, candidate_id)
    agg = diff["aggregate"]
    assert agg["mean_score_candidate"] < agg["mean_score_baseline"]
    assert agg["delta"] < 0
    assert agg["significant"] is True


def test_identical_runs_show_no_regression(tmp_path):
    # diffing a run against itself yields zero deltas and no significance
    store, baseline_id, _ = _run_regression(tmp_path)
    diff = diff_runs(store, baseline_id, baseline_id)
    assert diff["item_deltas"] == []
    assert diff["aggregate"]["delta"] == 0.0
    assert diff["aggregate"]["significant"] is False
