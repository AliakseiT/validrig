# SPDX-License-Identifier: AGPL-3.0-or-later
"""RegressionDiff: compare two fully-pinned runs.

This is the product's headline capability — "here is what the new version
broke". A diff is taken between two immutable, pinned snapshots and surfaces
change at three levels:

* per (case, perturbation, sample, rubric-item) score deltas,
* per-element input-contract deltas (including the measured/unmeasured
  transitions that a naive numeric diff would hide), and
* an aggregate mean-score delta with a bootstrap significance flag.

The diff reads only stored results and artifacts, so it is itself deterministic
and reproducible.
"""

from __future__ import annotations

from typing import Any

from harness.models.results import Grade
from harness.stats.bootstrap import bootstrap_ci

_EPS = 1e-9


def _overall(grade: Grade) -> float:
    scores = list(grade.item_scores.values())
    return sum(scores) / len(scores) if scores else 0.0


def _index_grades(grades: list[Grade]) -> dict[tuple[str, str, int], Grade]:
    return {(g.case_id, g.perturbation_id, g.sample_idx): g for g in grades}


def diff_grades(
    baseline: list[Grade],
    candidate: list[Grade],
) -> list[dict[str, Any]]:
    """Per (case, perturbation, sample, item) score deltas, changed items only."""
    base_idx = _index_grades(baseline)
    cand_idx = _index_grades(candidate)
    common = sorted(set(base_idx) & set(cand_idx))

    deltas: list[dict[str, Any]] = []
    for key in common:
        b, c = base_idx[key], cand_idx[key]
        items = sorted(set(b.item_scores) & set(c.item_scores))
        for item_id in items:
            sb = b.item_scores[item_id]
            sc = c.item_scores[item_id]
            if abs(sc - sb) <= _EPS:
                continue
            deltas.append(
                {
                    "case_id": key[0],
                    "perturbation_id": key[1],
                    "sample_idx": key[2],
                    "item_id": item_id,
                    "score_baseline": sb,
                    "score_candidate": sc,
                    "delta": sc - sb,
                }
            )
    return deltas


def diff_contracts(
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Per-element input-contract deltas, including measured/unmeasured shifts."""
    if not baseline or not candidate:
        return []
    base_elems = {e["name"]: e for e in baseline.get("elements", [])}
    cand_elems = {e["name"]: e for e in candidate.get("elements", [])}

    out: list[dict[str, Any]] = []
    for name in sorted(set(base_elems) | set(cand_elems)):
        b = base_elems.get(name, {})
        c = cand_elems.get(name, {})
        mb = bool(b.get("measured"))
        mc = bool(c.get("measured"))
        ivb = b.get("information_value")
        ivc = c.get("information_value")

        if mb and mc:
            delta = ivc - ivb
            status = "changed" if abs(delta) > _EPS else "unchanged"
        elif mb and not mc:
            delta = None
            status = "no_longer_measured"
        elif not mb and mc:
            delta = None
            status = "newly_measured"
        else:
            delta = None
            status = "unmeasured_both"

        out.append(
            {
                "element": name,
                "measured_baseline": mb,
                "measured_candidate": mc,
                "iv_baseline": ivb,
                "iv_candidate": ivc,
                "delta": delta,
                "status": status,
            }
        )
    return out


def _aggregate(
    baseline: list[Grade],
    candidate: list[Grade],
    seed: int,
) -> dict[str, Any]:
    base_idx = _index_grades(baseline)
    cand_idx = _index_grades(candidate)
    common = sorted(set(base_idx) & set(cand_idx))

    base_overall = [_overall(base_idx[k]) for k in common]
    cand_overall = [_overall(cand_idx[k]) for k in common]
    paired_diffs = [c - b for b, c in zip(base_overall, cand_overall)]

    mean_b = sum(base_overall) / len(base_overall) if base_overall else 0.0
    mean_c = sum(cand_overall) / len(cand_overall) if cand_overall else 0.0

    _, lo, hi = bootstrap_ci(paired_diffs, seed=seed)
    # significant if the CI on the paired difference excludes zero
    significant = bool(paired_diffs) and (lo > _EPS or hi < -_EPS)

    return {
        "n_units": len(common),
        "mean_score_baseline": mean_b,
        "mean_score_candidate": mean_c,
        "delta": mean_c - mean_b,
        "ci": [lo, hi],
        "significant": significant,
    }


def diff_runs(store, baseline_run_id: str, candidate_run_id: str, seed: int = 0) -> dict[str, Any]:
    base_grades = store.read_grades(baseline_run_id)
    cand_grades = store.read_grades(candidate_run_id)
    base_contract = store.read_contract(baseline_run_id)
    cand_contract = store.read_contract(candidate_run_id)

    item_deltas = diff_grades(base_grades, cand_grades)
    element_deltas = diff_contracts(base_contract, cand_contract)
    aggregate = _aggregate(base_grades, cand_grades, seed)

    n_regressions = sum(1 for d in item_deltas if d["delta"] < 0)
    n_improvements = sum(1 for d in item_deltas if d["delta"] > 0)

    return {
        "diff_type": "regression_diff",
        "schema_version": 1,
        "baseline": {
            "run_id": baseline_run_id,
            "pins": store.read_run(baseline_run_id).pins.model_dump(mode="json"),
        },
        "candidate": {
            "run_id": candidate_run_id,
            "pins": store.read_run(candidate_run_id).pins.model_dump(mode="json"),
        },
        "aggregate": aggregate,
        "item_deltas": item_deltas,
        "element_deltas": element_deltas,
        "n_regressions": n_regressions,
        "n_improvements": n_improvements,
    }
