# SPDX-License-Identifier: AGPL-3.0-or-later
"""ValidationReport rendering and acceptance evaluation.

Acceptance thresholds are interpreted by naming convention: a threshold named
``<metric>_max`` requires the metric to be at or below the limit; ``<metric>_min``
requires it to be at or above. Every number in the report is traceable to the
pinned inputs printed alongside it — the report *is* the QMS evidence artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.models.pack import AcceptanceSpec
from harness.models.results import Pins, RunMeta


def evaluate_acceptance(
    metrics: dict[str, float],
    thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for key in sorted(thresholds):
        limit = thresholds[key]
        if key.endswith("_max"):
            metric_name = key[:-4]
            value = metrics.get(metric_name)
            passed = value is not None and value <= limit
        elif key.endswith("_min"):
            metric_name = key[:-4]
            value = metrics.get(metric_name)
            passed = value is not None and value >= limit
        else:
            metric_name = key
            value = metrics.get(metric_name)
            passed = None
        results.append(
            {
                "threshold": key,
                "metric": metric_name,
                "value": value,
                "limit": limit,
                "passed": passed,
            }
        )
    return results


def build_validation_report(
    pins: Pins,
    run_meta: RunMeta,
    summary: dict[str, Any],
    acceptance: AcceptanceSpec,
) -> dict[str, Any]:
    metrics = {
        name: block["mean"]
        for name, block in summary.items()
        if isinstance(block, dict) and "mean" in block
    }
    results = evaluate_acceptance(metrics, acceptance.thresholds)
    overall = all(r["passed"] for r in results) if results else True

    return {
        "report_type": "validation_report",
        "schema_version": 1,
        "pins": pins.model_dump(mode="json"),
        "run": {
            "run_id": run_meta.run_id,
            "timestamp": run_meta.timestamp,
            "env_hash": run_meta.env_hash,
        },
        "summary": summary,
        "acceptance": {"results": results, "overall_pass": overall},
        "human_agreement": {"status": "not_collected", "note": "calibration UI lands in M2"},
    }


def render_report_json(report: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
