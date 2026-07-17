# SPDX-License-Identifier: AGPL-3.0-or-later
"""Consolidated validation dossier + printable HTML rendering."""

from pathlib import Path

from harness.execute import run_battery
from harness.packio.loader import load_pack
from harness.qms.dossier import build_dossier
from harness.qms.dossier_html import render_dossier_html
from harness.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _dossier(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    res = run_battery(pack, "smoke", store, seed=1, now=CLOCK)[0]
    run = store.read_run(res.run_id)
    return build_dossier(
        pack, pack.battery("smoke"), run, store.read_grades(res.run_id),
        store.read_report(res.run_id), store.read_contract(res.run_id),
    ), run


def test_dossier_assembles_records(tmp_path):
    d, run = _dossier(tmp_path)
    assert d["record_type"] == "validation_dossier"
    assert d["product_id"] == "demo-tumor-board"
    assert "vv_report" in d and "vv_plan" in d and "contract" in d
    # signing seam present but not implemented
    assert d["signing"]["status"] == "unsigned"
    assert d["signing"]["release_anchor"] is None
    assert "github_immutable_release" in d["signing"]["mechanism"]


def test_dossier_html_is_self_contained_and_printable(tmp_path):
    d, run = _dossier(tmp_path)
    html = render_dossier_html(d)
    assert html.startswith("<!doctype html>")
    # self-contained: no external resources
    assert "http://" not in html and "https://" not in html
    assert "cdn" not in html.lower()
    # printable
    assert "@media print" in html
    # attestation hash printed
    assert d["attestation"]["pinned_inputs_hash"] in html
    # verdict + a rubric item present
    assert "Release recommendation" in html
    assert "item_diagnosis" in html


def test_dossier_html_status_is_label_backed_not_colour_alone(tmp_path):
    d, run = _dossier(tmp_path)
    html = render_dossier_html(d)
    # every status pill carries its text label (grayscale-print safe)
    assert ">pass<" in html
    assert "not measured" in html  # unmeasured elements labelled, not a blank bar


def test_dossier_cli_writes_html(tmp_path):
    from harness.cli import main
    store = RunStore(tmp_path)
    pack = load_pack(PACK)
    res = run_battery(pack, "smoke", store, seed=1, now=CLOCK)[0]
    rc = main(["dossier", str(PACK), "--run", res.run_id, "--out", str(tmp_path)])
    assert rc == 0
    assert (store.runs_dir / res.run_id / "qms" / "dossier.html").exists()
    assert (store.runs_dir / res.run_id / "qms" / "dossier.json").exists()
