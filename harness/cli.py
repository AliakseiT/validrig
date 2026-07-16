# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line interface: run a battery from a pack and emit artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
