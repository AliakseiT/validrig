# SPDX-License-Identifier: AGPL-3.0-or-later
"""QMS records from monitoring: PMS always, AIMS event only on real drift."""

import json
from pathlib import Path

from validrig.execute import run_battery
from validrig.monitoring.drift import evaluate_drift
from validrig.monitoring.models import ProductionEvent
from validrig.monitoring.snapshot import build_snapshot
from validrig.packio.loader import load_pack
from validrig.qms.pms import build_aims_event, build_pms_report
from validrig.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731

_CONTRACT = {
    "pins": {"pack_id": "demo", "seed": 1},
    "minimal_sufficient_set_candidate": ["a"],
    "elements": [{"name": "a"}],
}
_THRESH = {"override_rate_max": 0.30}


def _events(n, n_over):
    return [ProductionEvent(period="2026-Q3", elements_present={"a": True}, overridden=(i < n_over))
            for i in range(n)]


def test_clean_snapshot_pms_has_no_signals_and_no_aims_event():
    snap = build_snapshot(_events(20, 2), _CONTRACT, "2026-Q3")  # 0.1, clean
    drift = evaluate_drift(snap, _THRESH)
    pms = build_pms_report(snap, drift)
    assert pms["signal_assessment"]["signals_identified"] == ["none"]
    assert pms["attestation"]["pinned_inputs_hash"]
    assert pms["signatures"]["signatures"] == []
    # no drift -> no AIMS event fabricated
    assert build_aims_event(snap, drift) is None


def test_drift_snapshot_pms_signals_and_aims_event():
    snap = build_snapshot(_events(20, 10), _CONTRACT, "2026-Q3")  # 0.5 > 0.30 -> drift
    drift = evaluate_drift(snap, _THRESH)
    pms = build_pms_report(snap, drift)
    assert pms["signal_assessment"]["drift_status"] == "drift"
    assert pms["signal_assessment"]["signals_identified"] != ["none"]

    event = build_aims_event(snap, drift)
    assert event is not None
    assert event["event_type"] == "drift"
    assert event["status"] == "open"
    assert event["signatures"]["signatures"] == []


def test_advisory_snapshot_no_aims_event():
    snap = build_snapshot(_events(5, 4), _CONTRACT, "2026-Q3")  # 0.8 but n=5 -> advisory
    drift = evaluate_drift(snap, _THRESH)
    assert build_aims_event(snap, drift) is None  # advisory is not a confirmed drift


def _write_events(path, n, n_over, period):
    lines = [json.dumps({"period": period, "elements_present": {
        "pathology_report": True, "molecular_report": True, "imaging_text": True,
        "prior_notes": True, "meds": True}, "overridden": i < n_over}) for i in range(n)]
    Path(path).write_text("\n".join(lines) + "\n")


def test_monitor_cli_end_to_end_raises_aims_on_degradation(tmp_path):
    from validrig.cli import main

    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    run_id = run_battery(pack, "smoke", store, seed=1, now=CLOCK)[0].run_id

    prior = tmp_path / "prior.jsonl"
    current = tmp_path / "current.jsonl"
    _write_events(prior, 20, 2, "2026-Q2")     # 0.10
    _write_events(current, 20, 8, "2026-Q3")   # 0.40 -> absolute + trend

    rc = main(["monitor", str(PACK), "--run", run_id, "--events", str(current),
               "--prior", str(prior), "--out", str(tmp_path)])
    assert rc == 0
    mon = store.runs_dir / run_id / "monitoring" / "2026-Q3"
    assert (mon / "snapshot.json").exists()
    assert (mon / "pms_report.md").exists()
    assert (mon / "aims_event.json").exists()  # degradation raised an event
    drift = json.loads((mon / "drift.json").read_text())
    assert drift["status"] == "drift"
