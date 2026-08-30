# SPDX-License-Identifier: AGPL-3.0-or-later
"""Machine-derived facts for published content.

Every number that appears on a published page resolves through this table, and
the table is built exclusively from pinned artifacts: the run store (contract,
validation report, grades), regression diffs recomputed from those grades, and
committed evidence JSON files the publish spec names explicitly. Authored prose
references facts as ``{{key}}`` or ``{{key|format-spec}}``; an unknown key or a
leftover unresolved placeholder is a hard error, never silently kept text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from validrig.version import ENGINE_VERSION

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*(?:\|([^}]+))?\}\}")


class FactError(ValueError):
    """A placeholder referenced a fact that does not exist, or one survived."""


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _flatten(f"{prefix}.{i}", v, out)
    else:
        out[prefix] = value


def _run_facts(store, run_id: str) -> dict[str, Any]:
    run = store.read_run(run_id)
    contract = store.read_contract(run_id) or {}
    report = store.read_report(run_id) or {}

    facts: dict[str, Any] = {
        "sut": run.pins.sut_id,
        "battery": run.pins.battery_id,
        "seed": run.pins.seed,
        "pack_hash": run.pins.pack_hash,
        "timestamp": run.meta.timestamp,
        "date": run.meta.timestamp[:10],
    }
    summary = report.get("summary", {})
    if "mean_score" in summary:
        facts["mean_score"] = summary["mean_score"]["mean"]
    acceptance = report.get("acceptance", {})
    if "overall_pass" in acceptance:
        facts["overall"] = "PASS" if acceptance["overall_pass"] else "FAIL"
    for r in acceptance.get("results", []):
        m = r["metric"]
        facts[f"acceptance.{m}.value"] = r["value"]
        facts[f"acceptance.{m}.limit"] = r["limit"]
        facts[f"acceptance.{m}.result"] = "pass" if r["passed"] else "fail"
    for e in contract.get("elements", []):
        base = f"element.{e['name']}"
        facts[f"{base}.information_value"] = e.get("information_value")
        facts[f"{base}.measured"] = "yes" if e.get("measured") else "no"
        facts[f"{base}.necessary"] = (
            "yes" if e["name"] in contract.get("minimal_sufficient_set_candidate", []) else "no"
        )
    if "critical_omission_rate" in contract:
        facts["critical_omission_rate"] = contract["critical_omission_rate"]["mean"]
    return facts


def build_facts(
    pack,
    store,
    run_ids: list[str],
    diffs: dict[str, Any] | None = None,
    fact_files: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Assemble the fact table: flat dict of dotted key -> scalar value."""
    from validrig.diff import diff_runs

    facts: dict[str, Any] = {
        "engine.version": ENGINE_VERSION,
        "pack.id": pack.manifest.id,
        "pack.version": pack.manifest.version,
        "pack.hash": pack.pack_hash,
        "pack.n_cases": len(pack.cases),
    }
    for run_id in run_ids:
        for k, v in _run_facts(store, run_id).items():
            facts[f"run.{run_id}.{k}"] = v

    for key, spec in (diffs or {}).items():
        d = diff_runs(store, spec.baseline, spec.candidate)
        agg = d["aggregate"]
        facts[f"diff.{key}.delta"] = agg["delta"]
        facts[f"diff.{key}.mean_baseline"] = agg["mean_score_baseline"]
        facts[f"diff.{key}.mean_candidate"] = agg["mean_score_candidate"]
        facts[f"diff.{key}.significant"] = "yes" if agg["significant"] else "no"
        facts[f"diff.{key}.n_regressions"] = d["n_regressions"]
        facts[f"diff.{key}.n_improvements"] = d["n_improvements"]
        facts[f"diff.{key}.baseline_run"] = spec.baseline
        facts[f"diff.{key}.candidate_run"] = spec.candidate
        facts[f"diff.{key}.baseline_sut"] = d["baseline"]["pins"]["sut_id"]
        facts[f"diff.{key}.candidate_sut"] = d["candidate"]["pins"]["sut_id"]

    for key, path in (fact_files or {}).items():
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        flat: dict[str, Any] = {}
        _flatten("", doc, flat)
        for k, v in flat.items():
            facts[f"file.{key}.{k}"] = v

    return facts


def _format(value: Any, fmt: str | None) -> str:
    if fmt:
        return format(value, fmt.strip())
    if isinstance(value, float):
        return format(value, "g")
    return str(value)


def resolve_placeholders(text: str, facts: dict[str, Any]) -> str:
    """Substitute every ``{{key|fmt}}`` in ``text`` from the fact table."""

    def _sub(match: re.Match[str]) -> str:
        key, fmt = match.group(1), match.group(2)
        if key not in facts:
            close = [k for k in facts if key.rsplit(".", 1)[0] in k][:6]
            hint = f" (nearby facts: {', '.join(close)})" if close else ""
            raise FactError(f"unknown fact '{key}' in placeholder{hint}")
        value = facts[key]
        if value is None:
            raise FactError(f"fact '{key}' is null (not measured) — cannot publish it")
        try:
            return _format(value, fmt)
        except (ValueError, TypeError) as exc:
            raise FactError(f"cannot format fact '{key}' with '{fmt}': {exc}") from exc

    resolved = _PLACEHOLDER.sub(_sub, text)
    if "{{" in resolved:
        raise FactError(f"unresolved placeholder remains in: {resolved[:120]!r}")
    return resolved
