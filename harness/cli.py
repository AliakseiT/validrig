# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line interface: run a battery from a pack and emit artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness.diff import diff_runs
from harness.execute import run_battery
from harness.packio.loader import load_pack
from harness.qms.mappers import build_change_request, build_vv_plan, build_vv_report
from harness.qms.render import (
    render_change_request_md,
    render_vv_report_md,
    render_yaml,
    write_text,
)
from harness.store.runstore import RunStore
from harness.version import ENGINE_VERSION


def _cmd_run(args: argparse.Namespace) -> int:
    pack = load_pack(args.pack)
    store = RunStore(args.out)
    results = run_battery(pack, args.battery, store, seed=args.seed)

    print(f"harness {ENGINE_VERSION} — pack {pack.manifest.id} v{pack.manifest.version}")
    print(f"pack_hash={pack.pack_hash[:16]} battery={args.battery} seed={args.seed}")
    for r in results:
        verdict = "PASS" if r.report["acceptance"]["overall_pass"] else "FAIL"
        print(
            f"  sut={r.sut_id} run={r.run_id} units={r.n_units} "
            f"tokens={r.usage.total_tokens} cost_chf={r.usage.cost_chf:.6f} "
            f"acceptance={verdict}"
        )
        print(f"    contract:  {store.runs_dir / r.run_id / 'contract.json'}")
        print(f"    report:    {store.runs_dir / r.run_id / 'validation_report.json'}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    store = RunStore(args.out)
    diff = diff_runs(store, args.baseline, args.candidate)

    # A diff is a fact about a pair of runs, not about one run, so it lives in a
    # neutral diffs/ directory rather than inside either run's immutable record.
    diffs_dir = store.root / "diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)
    out_path = diffs_dir / f"{args.baseline}__{args.candidate}.json"
    out_path.write_text(json.dumps(diff, indent=2, sort_keys=True), encoding="utf-8")

    agg = diff["aggregate"]
    flag = "SIGNIFICANT" if agg["significant"] else "not significant"
    print(f"regression diff: {args.baseline} -> {args.candidate}")
    print(
        f"  mean score {agg['mean_score_baseline']:.4f} -> {agg['mean_score_candidate']:.4f} "
        f"(delta {agg['delta']:+.4f}, {flag})"
    )
    print(f"  item regressions={diff['n_regressions']} improvements={diff['n_improvements']}")
    changed_elems = [
        e for e in diff["element_deltas"]
        if e["status"] not in ("unchanged", "unmeasured_both")
    ]
    for e in changed_elems:
        d = "n/a" if e["delta"] is None else f"{e['delta']:+.4f}"
        print(f"    element {e['element']}: {e['status']} (iv delta {d})")
    print(f"  written: {out_path}")
    return 0


def _cmd_qms(args: argparse.Namespace) -> int:
    pack = load_pack(args.pack)
    store = RunStore(args.out)
    run = store.read_run(args.run)
    battery = pack.battery(run.pins.battery_id)
    if battery is None:
        raise KeyError(f"pack has no battery '{run.pins.battery_id}' for this run")
    grades = store.read_grades(args.run)
    validation_report = store.read_report(args.run) or {}
    contract = store.read_contract(args.run) or {}

    qms_dir = store.runs_dir / args.run / "qms"
    qms_dir.mkdir(parents=True, exist_ok=True)

    plan = build_vv_plan(pack, battery)
    report = build_vv_report(
        pack, battery, run.pins, run.meta, grades, validation_report, contract
    )
    write_text(qms_dir / "vv_plan.yml", render_yaml(plan))
    write_text(qms_dir / "vv_report.md", render_vv_report_md(report))
    write_text(qms_dir / "vv_report.json", json.dumps(report, indent=2, sort_keys=True))

    s = report["summary_of_results"]
    print(f"QMS records for run {args.run} (baseline {report['attestation']['qms_baseline_tag']}):")
    print(f"  V&V plan:   {qms_dir / 'vv_plan.yml'}")
    print(
        f"  V&V report: {qms_dir / 'vv_report.md'} "
        f"[{s['passed']}/{s['total_test_cases']} passed, "
        f"recommendation={report['release_recommendation']}]"
    )
    return 0


def _cmd_qms_change(args: argparse.Namespace) -> int:
    store = RunStore(args.out)
    diff = diff_runs(store, args.baseline, args.candidate)
    record = build_change_request(diff)

    qms_dir = store.root / "qms"
    qms_dir.mkdir(parents=True, exist_ok=True)
    stem = f"change_{args.baseline}__{args.candidate}"
    write_text(qms_dir / f"{stem}.md", render_change_request_md(record))
    write_text(qms_dir / f"{stem}.json", json.dumps(record, indent=2, sort_keys=True))

    print(f"QMS change request: {record['metadata']['change_id']}")
    print(f"  {record['impact_assessment']['safety_performance_impact']}")
    print(f"  written: {qms_dir / f'{stem}.md'}")
    return 0


def _cmd_ui(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from harness.calibration.store import CalibrationStore
        from harness.ui.app import create_app
    except ImportError:
        print(
            "The review UI needs the 'ui' extra: pip install 'harness-factory[ui]'",
            file=sys.stderr,
        )
        return 1

    pack = load_pack(args.pack)
    store = RunStore(args.out)
    calib_store = CalibrationStore(args.out)
    app = create_app(pack, store, calib_store, grader_id=args.grader)
    print(f"Calibration review UI for pack {pack.manifest.id} at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness", description="The Harness Factory engine")
    parser.add_argument("--version", action="version", version=f"harness {ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a battery from a pack")
    run.add_argument("pack", type=Path, help="path to the pack directory")
    run.add_argument("--battery", required=True, help="battery id to run")
    run.add_argument("--out", type=Path, default=Path("./runs"), help="run store root")
    run.add_argument("--seed", type=int, default=0, help="deterministic seed")
    run.set_defaults(func=_cmd_run)

    diff = sub.add_parser("diff", help="diff two runs in a store (baseline vs candidate)")
    diff.add_argument("--out", type=Path, default=Path("./runs"), help="run store root")
    diff.add_argument("--baseline", required=True, help="baseline run id")
    diff.add_argument("--candidate", required=True, help="candidate run id")
    diff.set_defaults(func=_cmd_diff)

    qms = sub.add_parser("qms", help="emit QMS V&V plan + report for a run")
    qms.add_argument("pack", type=Path, help="path to the pack directory")
    qms.add_argument("--run", required=True, help="run id to render QMS records for")
    qms.add_argument("--out", type=Path, default=Path("./runs"), help="run store root")
    qms.set_defaults(func=_cmd_qms)

    qms_change = sub.add_parser("qms-change", help="emit a QMS change request from a run diff")
    qms_change.add_argument("--out", type=Path, default=Path("./runs"), help="run store root")
    qms_change.add_argument("--baseline", required=True, help="baseline run id")
    qms_change.add_argument("--candidate", required=True, help="candidate run id")
    qms_change.set_defaults(func=_cmd_qms_change)

    ui = sub.add_parser("ui", help="launch the calibration review UI (needs the 'ui' extra)")
    ui.add_argument("pack", type=Path, help="path to the pack directory")
    ui.add_argument("--out", type=Path, default=Path("./runs"), help="run store root")
    ui.add_argument("--grader", default="reviewer", help="grader identity for recorded grades")
    ui.add_argument("--host", default="127.0.0.1", help="bind host (default localhost only)")
    ui.add_argument("--port", type=int, default=8080, help="bind port")
    ui.set_defaults(func=_cmd_ui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
