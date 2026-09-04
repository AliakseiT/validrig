# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calibration UI: verifies the endpoints, storage, and the loop closing.

Tests the DATA PATH (endpoints, human-grade persistence, agreement, gate) fully
offline via TestClient. It does NOT verify that the workflow is right for a
clinician — that UX review is out of scope here.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from validrig.calibration.store import CalibrationStore
from validrig.execute import run_battery
from validrig.packio.loader import load_pack
from validrig.store.runstore import RunStore
from validrig.ui.app import create_app

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _setup(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path / "runs")
    res = run_battery(pack, "smoke", store, seed=1, now=CLOCK)[0]
    calib = CalibrationStore(tmp_path / "runs")
    app = create_app(pack, store, calib, grader_id="dr_test", now=CLOCK)
    return pack, store, calib, res.run_id, TestClient(app)


def _post_grade(client, run_id, grade, transform):
    key = f"{grade.case_id}::{grade.perturbation_id}::{grade.sample_idx}"
    data = {"key": key, "note": ""}
    for item_id, score in grade.item_scores.items():
        data[f"score__{item_id}"] = str(transform(score))
    return client.post(f"/calibrate/{run_id}/unit", data=data)


def test_dashboard_lists_the_run(tmp_path):
    _, _, _, run_id, client = _setup(tmp_path)
    r = client.get("/")
    assert r.status_code == 200
    assert run_id in r.text
    assert "Calibration dashboard" in r.text


def test_calibrate_list_and_unit_form(tmp_path):
    pack, _, _, run_id, client = _setup(tmp_path)
    r = client.get(f"/calibrate/{run_id}")
    assert r.status_code == 200
    # unit form renders the rubric items
    r2 = client.get(
        f"/calibrate/{run_id}/unit",
        params={"key": "C001::ablation:none|format:structured::0"},
    )
    assert r2.status_code == 200
    for item in pack.rubric.items:
        assert item.id in r2.text


def test_calibrate_unit_form_shows_grading_instructions(tmp_path):
    pack, _, _, run_id, client = _setup(tmp_path)
    r = client.get(
        f"/calibrate/{run_id}/unit",
        params={"key": "C001::ablation:none|format:structured::0"},
    )
    assert r.status_code == 200
    assert "Score 1.0 if the output names the histological diagnosis" in r.text


def test_posting_a_grade_persists_to_calibration_store(tmp_path):
    _, store, calib, run_id, client = _setup(tmp_path)
    grade = store.read_grades(run_id)[0]
    resp = _post_grade(client, run_id, grade, transform=lambda s: s)
    assert resp.status_code == 200  # followed the 303 redirect back to the list
    human = calib.read_human_grades(run_id)
    assert len(human) == 1
    assert human[0].grader_id == "dr_test"


def test_loop_closes_gate_passes_when_human_agrees(tmp_path):
    _, store, _, run_id, client = _setup(tmp_path)
    for grade in store.read_grades(run_id)[:12]:
        _post_grade(client, run_id, grade, transform=lambda s: s)  # agree exactly
    r = client.get(f"/agreement/{run_id}")
    assert r.status_code == 200
    assert 'pill pass' in r.text
    assert "report issuance blocked" not in r.text


def test_loop_closes_gate_blocks_when_human_disagrees(tmp_path):
    _, store, _, run_id, client = _setup(tmp_path)
    # human gives the opposite binary label on every item (scores are 0/1)
    for grade in store.read_grades(run_id)[:12]:
        _post_grade(client, run_id, grade, transform=lambda s: 0.0 if s > 0 else 1.0)
    r = client.get(f"/agreement/{run_id}")
    assert r.status_code == 200
    assert 'pill block' in r.text
    assert "report issuance blocked" in r.text


def test_never_binds_all_interfaces_by_default():
    # the CLI default host must be localhost, not 0.0.0.0 (PHI on a hospital LAN)
    from validrig.cli import build_parser

    args = build_parser().parse_args(["ui", "packs/demo-tumor-board"])
    assert args.host == "127.0.0.1"
