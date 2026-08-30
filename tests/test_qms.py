# SPDX-License-Identifier: AGPL-3.0-or-later
"""QMS record mapping (r05 shapes).

The load-bearing check: the V&V report verdict must come from the baseline
(intended-input) condition, so a battery full of deliberate ablation never
renders as failed test cases; the perturbation degradation appears only in the
characterization section.
"""

from pathlib import Path

from validrig.diff import diff_runs
from validrig.execute import run_battery
from validrig.hashing import content_hash
from validrig.packio.loader import load_pack
from validrig.qms.mappers import build_change_request, build_vv_plan, build_vv_report
from validrig.qms.render import render_change_request_md, render_vv_report_md
from validrig.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _smoke_run(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    res = run_battery(pack, "smoke", store, seed=1, now=CLOCK)[0]
    return pack, store, res


def test_vv_plan_maps_requirements_and_is_dry_run(tmp_path):
    pack = load_pack(PACK)
    plan = build_vv_plan(pack, pack.battery("smoke"))
    rf = plan["required_fields"]
    assert plan["record_type"] == "verification_validation_plan"
    assert rf["product_id"] == "demo-tumor-board"
    # fake SUT => dry-run evidence, never formal release
    assert rf["campaign_mode"] == "dry_run"
    # rubric items become the requirements / planned test cases
    assert rf["linked_inputs"]["requirements"] == [i.id for i in pack.rubric.items]
    # acceptance thresholds carried across
    assert any("critical_omission_rate_max" in c for c in rf["acceptance_criteria"])
    # signature block left unsigned
    assert rf["signoff"]["signatures"] == []


def test_vv_report_verdict_is_baseline_not_ablation(tmp_path):
    pack, store, res = _smoke_run(tmp_path)
    run = store.read_run(res.run_id)
    report = build_vv_report(
        pack,
        pack.battery("smoke"),
        run.pins,
        run.meta,
        store.read_grades(res.run_id),
        store.read_report(res.run_id),
        store.read_contract(res.run_id),
    )
    s = report["summary_of_results"]
    # baseline is clean: every rubric item passes, nothing failed
    assert s["total_test_cases"] == len(pack.rubric.items)
    assert s["passed"] == len(pack.rubric.items)
    assert s["failed"] == 0
    assert report["release_recommendation"] == "approved_for_release"
    # ... yet the characterization still shows ablation-driven information value
    elems = {e["name"]: e for e in report["characterization"]["input_contract"]["elements"]}
    assert elems["molecular_report"]["information_value"] > 0
    assert "molecular_report" in report["characterization"]["input_contract"]["minimal_sufficient_set_candidate"]


def test_vv_report_signatures_unsigned_and_attested(tmp_path):
    pack, store, res = _smoke_run(tmp_path)
    run = store.read_run(res.run_id)
    report = build_vv_report(
        pack, pack.battery("smoke"), run.pins, run.meta,
        store.read_grades(res.run_id), store.read_report(res.run_id), store.read_contract(res.run_id),
    )
    assert report["signatures"]["signatures"] == []
    # attestation hashes the pins, not the rendered doc (report_date excluded)
    assert report["attestation"]["pinned_inputs_hash"] == content_hash(run.pins.model_dump(mode="json"))
    md = render_vv_report_md(report)
    assert "requires human approval" in md
    assert "dry_run" in md


def test_change_request_names_the_regression(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    results = run_battery(pack, "regression", store, seed=1, now=CLOCK)
    by_sut = {r.sut_id: r for r in results}
    diff = diff_runs(store, by_sut["fake-baseline"].run_id, by_sut["fake-regressed"].run_id)

    change = build_change_request(diff)
    assert change["record_type"] == "change_request"
    ia = change["impact_assessment"]
    # the molecular regression is named in the impact assessment
    assert any("molecular_report" in line for line in ia["regressed_elements"])
    assert "significant" in ia["safety_performance_impact"]
    md = render_change_request_md(change)
    assert "molecular_report" in md
    assert change["signatures"]["signatures"] == []


def test_change_request_attests_both_runs(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    results = run_battery(pack, "regression", store, seed=1, now=CLOCK)
    by_sut = {r.sut_id: r for r in results}
    diff = diff_runs(store, by_sut["fake-baseline"].run_id, by_sut["fake-regressed"].run_id)
    change = build_change_request(diff)
    assert change["attestation"]["baseline"]["pinned_inputs_hash"]
    assert change["attestation"]["candidate"]["pinned_inputs_hash"]
    assert (
        change["attestation"]["baseline"]["pinned_inputs_hash"]
        != change["attestation"]["candidate"]["pinned_inputs_hash"]
    )
