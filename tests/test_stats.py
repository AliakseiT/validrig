# SPDX-License-Identifier: AGPL-3.0-or-later
from validrig.stats.bootstrap import bootstrap_ci
from validrig.stats.analyze import (
    GradedRecord,
    critical_rates,
    information_value,
    mean_score,
)


def test_bootstrap_deterministic_and_ordered():
    vals = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.5, 0.75]
    a = bootstrap_ci(vals, n_boot=500, seed=42)
    b = bootstrap_ci(vals, n_boot=500, seed=42)
    assert a == b
    mean, lo, hi = a
    assert lo <= mean <= hi


def test_bootstrap_empty():
    assert bootstrap_ci([], n_boot=100, seed=0) == (0.0, 0.0, 0.0)


def _records():
    critical = ("item_diagnosis",)
    baseline = GradedRecord(
        perturbation_id="ablation:none",
        dropped=(),
        item_scores={"item_diagnosis": 1.0, "item_molecular": 1.0, "item_staging": 1.0},
        critical_items=critical,
    )
    no_mol = GradedRecord(
        perturbation_id="ablation:molecular_report",
        dropped=("molecular_report",),
        item_scores={"item_diagnosis": 1.0, "item_molecular": 0.0, "item_staging": 1.0},
        critical_items=critical,
    )
    no_path = GradedRecord(
        perturbation_id="ablation:pathology_report",
        dropped=("pathology_report",),
        item_scores={"item_diagnosis": 0.0, "item_molecular": 1.0, "item_staging": 1.0},
        critical_items=critical,
    )
    return [baseline, no_mol, no_path]


def test_information_value_positive_for_ablated_element():
    iv = information_value(_records(), baseline_dropped=())
    assert iv["molecular_report"] > 0
    assert iv["pathology_report"] > 0


def test_critical_rates_in_unit_interval():
    rates = critical_rates(_records(), n_boot=200, seed=0)
    r = rates["critical_omission_rate"]
    assert 0.0 <= r["lo"] <= r["mean"] <= r["hi"] <= 1.0
    # one of three records misses the critical item -> ~0.33
    assert r["mean"] > 0


def test_mean_score_summary():
    ms = mean_score(_records(), n_boot=200, seed=0)
    assert 0.0 <= ms["lo"] <= ms["mean"] <= ms["hi"] <= 1.0
    assert ms["n"] == 3
