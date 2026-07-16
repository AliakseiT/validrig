# SPDX-License-Identifier: AGPL-3.0-or-later
"""CLI coverage, including a cross-process determinism check.

The in-process determinism test cannot catch cross-process nondeterminism (e.g.
hash-seed effects). This test shells out to the installed CLI twice in separate
processes and asserts the on-disk content artifacts are byte-identical — the real
"replay tomorrow on another box" guarantee.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACK = REPO / "packs" / "hello-tumor-board"


def _run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def test_cli_run_produces_artifacts(tmp_path):
    out = tmp_path / "runs"
    proc = _run_cli(["run", str(PACK), "--battery", "smoke", "--out", str(out), "--seed", "1"], REPO)
    assert "acceptance=PASS" in proc.stdout


def _content_files(store_root: Path, run_id: str):
    run_dir = store_root / "runs" / run_id
    gen = run_dir / "generations.parquet"
    grade = run_dir / "grades.parquet"
    contract = run_dir / "contract.json"
    return gen.read_bytes(), grade.read_bytes(), json.loads(contract.read_text())


def test_cross_process_determinism(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    # separate processes => separate PYTHONHASHSEED unless pinned
    _run_cli(["run", str(PACK), "--battery", "smoke", "--out", str(out_a), "--seed", "1"], REPO)
    _run_cli(["run", str(PACK), "--battery", "smoke", "--out", str(out_b), "--seed", "1"], REPO)

    # find the (single) run id in each store
    run_a = next((out_a / "runs").iterdir()).name
    run_b = next((out_b / "runs").iterdir()).name
    assert run_a == run_b  # run id derives only from pins

    gen_a, grade_a, contract_a = _content_files(out_a, run_a)
    gen_b, grade_b, contract_b = _content_files(out_b, run_b)
    assert gen_a == gen_b
    assert grade_a == grade_b
    assert contract_a == contract_b


def test_cli_diff_reports_regression(tmp_path):
    out = tmp_path / "runs"
    _run_cli(["run", str(PACK), "--battery", "regression", "--out", str(out), "--seed", "1"], REPO)
    run_ids = sorted(p.name for p in (out / "runs").iterdir())
    # two runs produced; diff both orderings and find the regressing one
    a, b = run_ids
    proc = _run_cli(["diff", "--out", str(out), "--baseline", a, "--candidate", b], REPO)
    combined = proc.stdout
    assert "regression diff" in combined
