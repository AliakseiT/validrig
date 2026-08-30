# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load, validate, and content-hash an intended-use pack from a directory.

The loader reads the declarative files, validates them against the pack schema
models, and computes a stable ``pack_hash`` over the full canonicalized content.
The hash is independent of file read order, so two loads of the same pack always
agree — a precondition for deterministic replay and regression diffs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from validrig.hashing import content_hash
from validrig.models.pack import (
    AcceptanceSpec,
    Adjudication,
    BatterySpec,
    Case,
    CaseSchema,
    JudgeSpec,
    Manifest,
    Pack,
    PerturbationSpec,
    Rubric,
)
from validrig.models.sut import SUTSpec


class PackValidationError(Exception):
    """Raised when a pack directory fails schema validation or is malformed."""


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise PackValidationError(f"missing required file: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_pack(path: str | Path) -> Pack:
    root = Path(path)
    if not root.is_dir():
        raise PackValidationError(f"pack path is not a directory: {root}")

    try:
        manifest = Manifest(**_read_yaml(root / "manifest.yaml"))
        case_schema = CaseSchema(**_read_yaml(root / "casebank" / "schema.yaml"))

        case_dir = root / "casebank" / "cases"
        case_files = sorted(case_dir.glob("*.json")) if case_dir.is_dir() else []
        cases = [Case(**_read_json(p)) for p in case_files]

        rubric = Rubric(**_read_yaml(root / "rubric" / "rubric.yaml"))

        perturbations = PerturbationSpec(**_read_yaml(root / "perturbations.yaml"))

        battery_doc = _read_yaml(root / "battery.yaml") or {}
        batteries = [BatterySpec(**b) for b in battery_doc.get("batteries", [])]

        suts_doc = _read_yaml(root / "suts.yaml") or {}
        suts = [SUTSpec(**s).with_hash() for s in suts_doc.get("suts", [])]

        judge = JudgeSpec(**_read_yaml(root / "judge.yaml"))
        acceptance = AcceptanceSpec(**(_read_yaml(root / "acceptance.yaml") or {}))

        monitoring_doc = _read_yaml(root / "monitoring.yaml") if (root / "monitoring.yaml").exists() else {}
        monitoring = (monitoring_doc or {}).get("thresholds", {})

        adj_dir = root / "rubric" / "adjudication"
        adj_files = sorted(adj_dir.glob("*.json")) if adj_dir.is_dir() else []
        adjudications = [Adjudication(**_read_json(p)) for p in adj_files]

        mock_dir = root / "mocks"
        mocks = {p.stem: _read_json(p) for p in sorted(mock_dir.glob("*.json"))} if mock_dir.is_dir() else {}
    except ValidationError as exc:
        raise PackValidationError(str(exc)) from exc
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise PackValidationError(f"could not parse pack file: {exc}") from exc

    # Referential integrity: an adjudication must name a real case and only real
    # rubric items. A dangling reference is a malformed pack, not a silent skip.
    case_ids = {c.case_id for c in cases}
    item_ids = {i.id for i in rubric.items}
    for adj in adjudications:
        if adj.case_id not in case_ids:
            raise PackValidationError(
                f"adjudication references unknown case_id '{adj.case_id}'"
            )
        for item_id in adj.values:
            if item_id not in item_ids:
                raise PackValidationError(
                    f"adjudication for case '{adj.case_id}' references unknown "
                    f"rubric item '{item_id}'"
                )

    pack = Pack(
        manifest=manifest,
        case_schema=case_schema,
        cases=cases,
        rubric=rubric,
        perturbations=perturbations,
        batteries=batteries,
        suts=suts,
        judge=judge,
        acceptance=acceptance,
        monitoring=monitoring,
        adjudications=adjudications,
        mocks=mocks,
    )
    pack_hash = content_hash(pack.model_dump(mode="json", exclude={"pack_hash"}))
    return pack.model_copy(update={"pack_hash": pack_hash})
