# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adjudication authoring in the review UI (blind mode, writes pack gold)."""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from harness.calibration.store import CalibrationStore
from harness.packio.loader import load_pack
from harness.store.runstore import RunStore
from harness.ui.app import create_app

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _client(tmp_path):
    pack_dir = tmp_path / "pack"
    shutil.copytree(PACK, pack_dir)
    pack = load_pack(pack_dir)
    store = RunStore(tmp_path / "runs")
    calib = CalibrationStore(tmp_path / "runs")
    app = create_app(pack, store, calib, grader_id="dr_gold", now=CLOCK, pack_dir=pack_dir)
    return pack_dir, TestClient(app)


def test_adjudicate_list_shows_cases(tmp_path):
    _, client = _client(tmp_path)
    r = client.get("/adjudicate")
    assert r.status_code == 200
    assert "C001" in r.text


def test_adjudicate_form_is_blind(tmp_path):
    _, client = _client(tmp_path)
    r = client.get("/adjudicate/C001")
    assert r.status_code == 200
    # blind: the source document is shown, but no model-output panel
    assert "Source document" in r.text
    assert "System-under-test output" not in r.text  # that panel is calibration-only
    assert "STRUCTURED SUMMARY" not in r.text  # no fake-model output content
    # rubric items present to grade
    assert "item_diagnosis" in r.text


def test_posting_adjudication_writes_pack_gold(tmp_path):
    pack_dir, client = _client(tmp_path)
    # overwrite C001's gold via the UI
    resp = client.post("/adjudicate/C001", data={
        "score__item_diagnosis": "1.0",
        "score__item_molecular": "0.0",
        "score__item_staging": "1.0",
    })
    assert resp.status_code == 200  # followed redirect to the list

    # the pack now loads with the new adjudication (referential integrity holds)
    pack = load_pack(pack_dir)
    adj = pack.adjudication("C001")
    assert adj is not None
    assert adj.adjudicated_by == "dr_gold"
    assert adj.values["item_molecular"] == 0.0


def test_read_only_when_no_pack_dir(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path / "runs")
    calib = CalibrationStore(tmp_path / "runs")
    app = create_app(pack, store, calib, grader_id="dr_gold", now=CLOCK)  # no pack_dir
    client = TestClient(app)
    r = client.get("/adjudicate")
    assert "Read-only" in r.text
    # a post is a no-op redirect, writes nothing
    resp = client.post("/adjudicate/C001", data={"score__item_diagnosis": "1.0"})
    assert resp.status_code == 200
