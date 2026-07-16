# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only store for human calibration grades (and adjudications).

Kept separate from the run store so the immutable judge grades are never
touched. Human grades are appended as JSON lines, one file per run; re-grading is
an append, and agreement reads the latest grade per (grader, content key, item).
"""

from __future__ import annotations

import json
from pathlib import Path

from harness.calibration.models import HumanGrade
from harness.pathsafe import confined_path, require_safe_id


class CalibrationStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.calib_dir = self.root / "calibration"
        self.calib_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        # run_id reaches here from URL input; validate and confine.
        require_safe_id(run_id, "run_id")
        return confined_path(self.calib_dir, f"{run_id}.jsonl")

    def append_human_grade(self, grade: HumanGrade) -> None:
        path = self._path(grade.run_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(grade.model_dump(mode="json"), sort_keys=True) + "\n")

    def read_human_grades(self, run_id: str) -> list[HumanGrade]:
        path = self._path(run_id)
        if not path.exists():
            return []
        out: list[HumanGrade] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(HumanGrade(**json.loads(line)))
        return out

    def latest_by_key(self, run_id: str) -> dict[tuple[str, tuple], HumanGrade]:
        """Latest human grade per (grader_id, content_key) — append-only wins."""
        latest: dict[tuple[str, tuple], HumanGrade] = {}
        for g in self.read_human_grades(run_id):
            latest[(g.grader_id, g.content_key())] = g  # later lines overwrite
        return latest

    def graded_keys(self, run_id: str) -> set[tuple]:
        return {g.content_key() for g in self.read_human_grades(run_id)}
