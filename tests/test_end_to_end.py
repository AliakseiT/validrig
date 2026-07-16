# SPDX-License-Identifier: AGPL-3.0-or-later
"""End-to-end demo run and the M1 determinism exit gate."""

from pathlib import Path

from harness.execute import run_battery
from harness.packio.loader import load_pack
from harness.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"

FIXED_CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def test_demo_pack_runs_end_to_end(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    results = run_battery(pack, "smoke", store, seed=1, now=FIXED_CLOCK)
    assert len(results) == 1
    r = results[0]
    assert r.n_units == 45
    assert r.usage.total_tokens > 0
    # baseline acceptance passes: all evidence present in the unperturbed input
    assert r.report["acceptance"]["overall_pass"] is True
    # the contract identifies the informative elements
    msc = set(r.contract["minimal_sufficient_set_candidate"])
    assert {"pathology_report", "molecular_report", "imaging_text"} <= msc
    assert "meds" not in msc
    # prior_notes and meds are only ablated bundled (never in isolation), so the
    # contract must report them as unmeasured, not as measured-zero.
    by_name = {e["name"]: e for e in r.contract["elements"]}
    assert by_name["meds"]["measured"] is False
    assert by_name["meds"]["information_value"] is None
    assert by_name["pathology_report"]["measured"] is True
    # artifacts written to disk
    assert (store.runs_dir / r.run_id / "contract.json").exists()
    assert (store.runs_dir / r.run_id / "validation_report.json").exists()


def _content_snapshot(store: RunStore, run_id: str):
    gens = store.read_generations(run_id)
    grades = store.read_grades(run_id)
    return (
        [g.model_dump(mode="json") for g in gens],
        [g.model_dump(mode="json") for g in grades],
    )


def test_determinism_content_is_identical_across_runs(tmp_path):
    """The M1 exit gate: two runs with the same seed produce byte-identical
    content (generations, grades, contract), proving deterministic replay. Only
    run metadata (timestamp, env_hash) is allowed to differ."""
    pack = load_pack(PACK)

    store_a = RunStore(tmp_path / "a")
    store_b = RunStore(tmp_path / "b")

    res_a = run_battery(pack, "smoke", store_a, seed=1, now=lambda: "2020-01-01T00:00:00+00:00")[0]
    res_b = run_battery(pack, "smoke", store_b, seed=1, now=lambda: "2099-12-31T23:59:59+00:00")[0]

    # run id derives only from pins, not wall-clock time
    assert res_a.run_id == res_b.run_id

    gens_a, grades_a = _content_snapshot(store_a, res_a.run_id)
    gens_b, grades_b = _content_snapshot(store_b, res_b.run_id)
    assert gens_a == gens_b
    assert grades_a == grades_b

    # the derived contract is identical despite different timestamps
    assert res_a.contract == res_b.contract

    # ... and the report's content differs only in the run-metadata block
    report_a = dict(res_a.report)
    report_b = dict(res_b.report)
    assert report_a.pop("run")["timestamp"] != report_b.pop("run")["timestamp"]
    assert report_a == report_b
