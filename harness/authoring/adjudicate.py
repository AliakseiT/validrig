# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write physician adjudications (per-case gold) into a pack.

Adjudications are *pack content* — the loader reads them from
``<pack>/rubric/adjudication/<case>.json`` and folds them into ``pack_hash``.
So, unlike calibration human-grades (which live in the run store), adjudication
authoring writes into the pack directory. That is intended: adjudicating is
authoring the gold standard, and a change to the gold is meant to change the
pack hash.
"""

from __future__ import annotations

import json
from pathlib import Path

from harness.models.pack import Adjudication


def adjudication_path(pack_dir: str | Path, case_id: str) -> Path:
    return Path(pack_dir) / "rubric" / "adjudication" / f"{case_id}.json"


def write_adjudication(pack_dir: str | Path, adjudication: Adjudication) -> Path:
    path = adjudication_path(pack_dir, adjudication.case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(adjudication.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def adjudicated_case_ids(pack_dir: str | Path) -> set[str]:
    adj_dir = Path(pack_dir) / "rubric" / "adjudication"
    if not adj_dir.is_dir():
        return set()
    return {p.stem for p in adj_dir.glob("*.json")}
