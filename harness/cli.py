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

    out_path = store.runs_dir / args.candidate / "regression_diff.json"
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
