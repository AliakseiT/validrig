# SPDX-License-Identifier: AGPL-3.0-or-later
"""Scaffold a new, valid, runnable pack skeleton.

The output loads with ``load_pack`` and runs its ``smoke`` battery immediately
(fake SUT + fake judge, so it needs no endpoint), giving a pack author a working
starting point to edit. Content is intentionally generic — the engine and its
tooling carry no use-case vocabulary.
"""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST = """\
id: {pack_id}
version: "0.1.0"
intended_use: >
  TODO: state the intended use in QMS wording. Scaffold pack — replace the
  synthetic content below with your own cases, rubric, and adjudications.
device_status_rationale: >
  TODO: state the device-status rationale for your deployment context.
population: >
  TODO: describe the target population and language(s).
languages: ["en"]
"""

_SCHEMA = """\
elements:
  - name: section_a
    type: text
    modality: text
    language: en
    required: true
  - name: section_b
    type: text
    modality: text
    language: en
    required: false
"""

_CASE = {
    "case_id": "EX001",
    "elements": {
        "section_a": "Primary section (synthetic). Key finding: ALPHA present.",
        "section_b": "Secondary section (synthetic). Additional detail: BETA noted.",
    },
    "ground_truth": {
        "item_key_finding": {"evidence": ["ALPHA"], "expected": True},
        "item_secondary": {"evidence": ["BETA"], "expected": True},
    },
}

_RUBRIC = """\
items:
  - id: item_key_finding
    statement: The output states the key finding.
    type: binary
    critical: true
    evidence_required: true
    grading_instructions: Score 1.0 if the key finding is stated; else 0.0.
    max_score: 1.0
  - id: item_secondary
    statement: The output states the secondary detail.
    type: binary
    critical: false
    evidence_required: true
    grading_instructions: Score 1.0 if the secondary detail is stated; else 0.0.
    max_score: 1.0
"""

_ADJUDICATION = {
    "case_id": "EX001",
    "adjudicated_by": "TODO-replace-with-reviewer",
    "adjudicated_at": "2026-01-01",
    "values": {"item_key_finding": 1.0, "item_secondary": 1.0},
}

_PERTURBATIONS = """\
# Mutation axes (ablation) must precede the rendering axis (format).
axes:
  ablation:
    - id: baseline
      drop: []
    - id: no_section_b
      drop: ["section_b"]
  format:
    - id: structured
      style: structured
    - id: raw_dump
      style: raw_dump
"""

_BATTERY = """\
batteries:
  - id: smoke
    version: "1"
    cases: all
    perturbations: all
    axes: ["ablation", "format"]
    suts: ["fake-baseline"]
    n_samples: 1
"""

_SUTS = """\
suts:
  - id: fake-baseline
    kind: llm_call
    binding:
      model_id: fake
      model_version: "1"
      system_prompt: >
        TODO: replace with the system under test. This scaffold uses the
        deterministic fake model so the pack runs offline out of the box.
      params:
        temperature: 0
"""

_JUDGE = """\
id: fake-judge
version: "1"
kind: fake
binding: {}
calibration_fraction: 0.1
"""

_ACCEPTANCE = """\
thresholds:
  critical_omission_rate_max: 0.10
  mean_score_min: 0.60
"""


def scaffold_pack(dest: str | Path, pack_id: str) -> Path:
    """Write a runnable pack skeleton under ``dest``. Returns the pack directory."""
    root = Path(dest)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"destination is not empty: {root}")

    files: dict[str, str] = {
        "manifest.yaml": _MANIFEST.format(pack_id=pack_id),
        "casebank/schema.yaml": _SCHEMA,
        "casebank/cases/EX001.json": json.dumps(_CASE, indent=2) + "\n",
        "rubric/rubric.yaml": _RUBRIC,
        "rubric/adjudication/EX001.json": json.dumps(_ADJUDICATION, indent=2) + "\n",
        "perturbations.yaml": _PERTURBATIONS,
        "battery.yaml": _BATTERY,
        "suts.yaml": _SUTS,
        "judge.yaml": _JUDGE,
        "acceptance.yaml": _ACCEPTANCE,
    }
    for relpath, content in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root
