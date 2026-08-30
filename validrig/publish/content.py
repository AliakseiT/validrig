# SPDX-License-Identifier: AGPL-3.0-or-later
"""Assemble the ``pipeline`` content object from spec + pinned runs.

The output is a plain dict shaped for a data-only site content module: page
identity, narrative arc (authored prose with machine facts substituted), and a
report section embedding the real dossier of the primary run (the first run id
given), its run hash, and the engine version.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from validrig.publish.facts import build_facts, resolve_placeholders
from validrig.publish.fragment import render_dossier_fragment
from validrig.publish.spec import PublishSpec
from validrig.qms.dossier import build_dossier


def _camel(slug: str) -> str:
    parts = [p for p in slug.replace("_", "-").split("-") if p]
    return parts[0] + "".join(p.capitalize() for p in parts[1:]) if parts else "content"


def build_pipeline_content(
    pack,
    store,
    run_ids: list[str],
    spec: PublishSpec,
    spec_dir: str | Path,
    slug: str | None = None,
    title: str | None = None,
    allow_pack_drift: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(content, meta)`` for the pipeline template.

    ``content`` matches the site's data-only interface; ``meta`` carries
    provenance for the emitted header (export name, run ids, pack pins).
    """
    if not run_ids:
        raise ValueError("publish needs at least one --run (the first is the dossier run)")

    # Traceability guard: published numbers must come from runs of THIS pack
    # content. A drifted pack directory means the page would mix eras.
    for run_id in run_ids:
        pinned = store.read_run(run_id).pins.pack_hash
        if pinned != pack.pack_hash and not allow_pack_drift:
            raise ValueError(
                f"run {run_id} was pinned to pack_hash {pinned[:16]}… but the pack "
                f"directory now hashes to {pack.pack_hash[:16]}… — the pack content "
                "changed since the run. Re-run the battery, or pass "
                "--allow-pack-drift if the drift is understood and documented."
            )

    spec_dir = Path(spec_dir)
    fact_files = {k: spec_dir / v for k, v in spec.fact_files.items()}
    facts = build_facts(pack, store, run_ids, diffs=spec.diffs, fact_files=fact_files)

    arc = {
        field: resolve_placeholders(getattr(spec.arc, field).strip(), facts)
        for field in ("task", "risks", "measurement", "findings", "meaning")
    }

    primary = run_ids[0]
    run = store.read_run(primary)
    battery = pack.battery(run.pins.battery_id)
    if battery is None:
        raise KeyError(f"pack has no battery '{run.pins.battery_id}' for run {primary}")
    dossier = build_dossier(
        pack,
        battery,
        run,
        store.read_grades(primary),
        store.read_report(primary) or {},
        store.read_contract(primary) or {},
    )

    content: dict[str, Any] = {
        "slug": slug or spec.slug,
        "title": title or spec.title,
        "summary": resolve_placeholders(spec.summary.strip(), facts),
        "dataNote": resolve_placeholders(spec.data_note.strip(), facts),
        "arc": arc,
        "report": {
            "title": spec.report_title
            or f"Validation dossier — {pack.manifest.id} v{pack.manifest.version}",
            "runHash": primary,
            "generatedDate": dossier["generated_at"],
            "bodyHtml": render_dossier_fragment(dossier),
        },
    }
    meta = {
        "export_name": spec.export_name or _camel(content["slug"]),
        "pack_id": pack.manifest.id,
        "pack_version": pack.manifest.version,
        "pack_hash": pack.pack_hash,
        "run_ids": list(run_ids),
        "run_suts": {r: store.read_run(r).pins.sut_id for r in run_ids},
    }
    return content, meta
