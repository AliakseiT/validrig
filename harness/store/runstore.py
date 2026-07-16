# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only run store.

Run metadata lives in a small SQLite database (easy to query, no server); the
bulk content — generations and grades — lives in parquet files, one directory
per run. Everything is a plain file on disk: git-friendly, auditable,
exportable. Writes are append-only: re-writing an existing run id is refused, so
results are immutable once recorded.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from harness.models.results import Generation, Grade, Pins, Run, RunMeta, TokenUsage


class RunStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "runs.sqlite"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    pins_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    env_hash TEXT NOT NULL
                )
                """
            )

    # ---- runs -------------------------------------------------------------

    def write_run(self, run: Run) -> None:
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (run.meta.run_id,)
            ).fetchone()
            if exists:
                raise ValueError(
                    f"run {run.meta.run_id} already exists; results are append-only"
                )
            conn.execute(
                "INSERT INTO runs (run_id, pins_json, timestamp, env_hash) VALUES (?, ?, ?, ?)",
                (
                    run.meta.run_id,
                    json.dumps(run.pins.model_dump(mode="json")),
                    run.meta.timestamp,
                    run.meta.env_hash,
                ),
            )
        (self.runs_dir / run.meta.run_id).mkdir(parents=True, exist_ok=True)

    def read_run(self, run_id: str) -> Run:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT run_id, pins_json, timestamp, env_hash FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"no such run: {run_id}")
        pins = Pins(**json.loads(row[1]))
        meta = RunMeta(run_id=row[0], timestamp=row[2], env_hash=row[3])
        return Run(pins=pins, meta=meta)

    def list_runs(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT run_id FROM runs ORDER BY run_id").fetchall()
        return [r[0] for r in rows]

    # ---- derived artifacts ------------------------------------------------

    def read_contract(self, run_id: str) -> dict | None:
        path = self.runs_dir / run_id / "contract.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def read_report(self, run_id: str) -> dict | None:
        path = self.runs_dir / run_id / "validation_report.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ---- generations ------------------------------------------------------

    def _gen_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "generations.parquet"

    def write_generations(self, run_id: str, generations: list[Generation]) -> None:
        path = self._gen_path(run_id)
        if path.exists():
            raise ValueError(f"generations for {run_id} already written (append-only)")
        table = pa.table(
            {
                "case_id": [g.case_id for g in generations],
                "perturbation_id": [g.perturbation_id for g in generations],
                "sample_idx": [g.sample_idx for g in generations],
                "raw_output": [g.raw_output for g in generations],
                "trace_json": [json.dumps(g.trace) for g in generations],
                "usage_json": [json.dumps(g.usage.model_dump(mode="json")) for g in generations],
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path)

    def read_generations(self, run_id: str) -> list[Generation]:
        path = self._gen_path(run_id)
        if not path.exists():
            return []
        table = pq.read_table(path)
        rows = table.to_pylist()
        out = []
        for r in rows:
            out.append(
                Generation(
                    case_id=r["case_id"],
                    perturbation_id=r["perturbation_id"],
                    sample_idx=r["sample_idx"],
                    raw_output=r["raw_output"],
                    trace=json.loads(r["trace_json"]),
                    usage=TokenUsage(**json.loads(r["usage_json"])),
                )
            )
        return out

    # ---- grades -----------------------------------------------------------

    def _grade_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "grades.parquet"

    def write_grades(self, run_id: str, grades: list[Grade]) -> None:
        path = self._grade_path(run_id)
        if path.exists():
            raise ValueError(f"grades for {run_id} already written (append-only)")
        table = pa.table(
            {
                "case_id": [g.case_id for g in grades],
                "perturbation_id": [g.perturbation_id for g in grades],
                "sample_idx": [g.sample_idx for g in grades],
                "item_scores_json": [json.dumps(g.item_scores) for g in grades],
                "judge_notes_json": [json.dumps(g.judge_notes) for g in grades],
                "item_status_json": [json.dumps(g.item_status) for g in grades],
                "human_agreement_json": [json.dumps(g.human_agreement) for g in grades],
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path)

    def read_grades(self, run_id: str) -> list[Grade]:
        path = self._grade_path(run_id)
        if not path.exists():
            return []
        table = pq.read_table(path)
        rows = table.to_pylist()
        out = []
        for r in rows:
            out.append(
                Grade(
                    case_id=r["case_id"],
                    perturbation_id=r["perturbation_id"],
                    sample_idx=r["sample_idx"],
                    item_scores=json.loads(r["item_scores_json"]),
                    judge_notes=json.loads(r["judge_notes_json"]),
                    item_status=json.loads(r.get("item_status_json") or "{}"),
                    human_agreement=json.loads(r["human_agreement_json"]),
                )
            )
        return out
