# SPDX-License-Identifier: AGPL-3.0-or-later
"""The per-pack publish spec (``publish.yaml``).

Authored, plain-language content lives here — page identity (slug/title),
summary, data provenance note, and the narrative arc prose. It is a plain file
in the pack directory that the pack loader ignores, so adding or editing it
never changes the pack hash and never invalidates pinned runs.

The honesty rule: authored prose must not hand-type machine numbers. Any number
that exists in a run artifact is referenced via a ``{{fact|format}}``
placeholder and resolved at publish time (see ``facts.py``).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ArcSpec(BaseModel):
    """The fixed narrative arc of a published pipeline page (HTML fragments)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str
    risks: str
    measurement: str
    findings: str
    meaning: str


class DiffSpec(BaseModel):
    """A named regression comparison computed from two pinned runs' grades."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline: str
    candidate: str


class PublishSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    title: str
    summary: str
    data_note: str
    arc: ArcSpec
    # Title printed on the embedded report sheet; defaults to a generic one.
    report_title: str | None = None
    # TS export identifier; defaults to lowerCamelCase of the slug.
    export_name: str | None = None
    # Named diffs: key -> {baseline, candidate}; exposed as diff.<key>.* facts.
    diffs: dict[str, DiffSpec] = Field(default_factory=dict)
    # Extra committed evidence files (JSON), relative to the spec file:
    # key -> path; exposed as file.<key>.<flattened.path> facts.
    fact_files: dict[str, str] = Field(default_factory=dict)


def load_publish_spec(path: str | Path) -> PublishSpec:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"publish spec not found: {p} — author a publish.yaml with the page "
            "prose (slug, title, summary, data_note, arc: task/risks/"
            "measurement/findings/meaning)"
        )
    with p.open("r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return PublishSpec(**doc)
