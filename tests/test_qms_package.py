# SPDX-License-Identifier: AGPL-3.0-or-later
"""QMS package: calibration status folded into the V&V report + package manifest."""

from pathlib import Path

from harness.calibration.models import HumanGrade
from harness.calibration.store import CalibrationStore
from harness.execute import run_battery
from harness.hashing import content_hash
from harness.packio.loader import load_pack
from harness.qms.calibration_record import build_calibration_status
from harness.qms.mappers import build_vv_report
from harness.qms.package import build_package_manifest
from harness.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _run(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    res = run_battery(pack, "smoke", store, seed=1, now=CLOCK)[0]
    return pack, store, res


def test_vv_report_calibration_not_collected_by_default(tmp_path):
    pack, store, res = _run(tmp_path)
    run = store.read_run(res.run_id)
    report = build_vv_report(
        pack, pack.battery("smoke"), run.pins, run.meta,
        store.read_grades(res.run_id), store.read_report(res.run_id),
        store.read_contract(res.run_id),
    )
    assert report["calibration"]["status"] == "not_collected"
    assert report["release_recommendation"] == "approved_for_release"


def test_calibration_gate_block_overrides_recommendation(tmp_path):
    pack, store, res = _run(tmp_path)
    run = store.read_run(res.run_id)
    calibration = {
        "agreement": {"overall": {"n": 12, "kappa": 0.0}, "items": {}},
        "gate": {"status": "block", "blocks_report_issuance": True},
    }
    report = build_vv_report(
        pack, pack.battery("smoke"), run.pins, run.meta,
        store.read_grades(res.run_id), store.read_report(res.run_id),
        store.read_contract(res.run_id), calibration=calibration,
    )
    # even though the baseline passed acceptance, a blocking gate overrides
    assert report["release_recommendation"] == "blocked_pending_calibration"
    assert report["calibration"]["gate"]["status"] == "block"


def test_calibration_status_record_is_attested(tmp_path):
    pack, store, res = _run(tmp_path)
    run = store.read_run(res.run_id)
    status = build_calibration_status(
        run.pins, run.meta,
        {"overall": {"n": 12, "kappa": 1.0}, "items": {}},
        {"status": "pass", "blocks_report_issuance": False},
    )
    assert status["record_type"] == "calibration_status"
    assert status["attestation"]["pinned_inputs_hash"] == content_hash(run.pins.model_dump(mode="json"))


def test_package_manifest_ties_documents_to_pins(tmp_path):
    pack, store, res = _run(tmp_path)
    run = store.read_run(res.run_id)
    manifest = build_package_manifest(
        run.pins, run.meta,
        [{"type": "verification_validation_report", "path": "qms/vv_report.md"}],
        "approved_for_release", "not_collected",
    )
    assert manifest["record_type"] == "qms_package_manifest"
    assert manifest["product_id"] == "demo-tumor-board"
    assert manifest["run_id"] == run.meta.run_id
    assert manifest["attestation"]["pinned_inputs_hash"]


def test_qms_cli_emits_calibration_status_when_grades_exist(tmp_path):
    from harness.cli import main

    pack, store, res = _run(tmp_path)
    # append a human grade so calibration data exists
    calib = CalibrationStore(tmp_path)
    calib.append_human_grade(HumanGrade(
        run_id=res.run_id, case_id="C001",
        perturbation_id="ablation:none|format:structured", sample_idx=0,
        grader_id="dr_x", item_scores={"item_diagnosis": 1.0},
    ))
    rc = main(["qms", str(PACK), "--run", res.run_id, "--out", str(tmp_path)])
    assert rc == 0
    assert (store.runs_dir / res.run_id / "qms" / "calibration_status.json").exists()
    assert (store.runs_dir / res.run_id / "qms" / "package_manifest.json").exists()
