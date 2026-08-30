# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

from validrig.artifacts.contract import extract_contract
from validrig.artifacts.report import (
    build_validation_report,
    evaluate_acceptance,
    render_report_json,
)
from validrig.models.pack import AcceptanceSpec, CaseSchema, ElementSpec
from validrig.models.results import Pins, RunMeta


def _pins():
    return Pins(
        pack_id="p", pack_version="1", pack_hash="h", battery_id="b", battery_version="1",
        sut_id="s", sut_hash="sh", judge_id="j", judge_version="1", seed=7, engine_version="0.1.0",
    )


def _schema():
    return CaseSchema(
        elements=[
            ElementSpec(name="pathology_report", type="text", modality="pathology", language="en"),
            ElementSpec(name="molecular_report", type="text", modality="genomics", language="en"),
            ElementSpec(name="prior_notes", type="text", modality="note", language="en", required=False),
        ]
    )


def test_contract_is_serializable_with_pins_and_elements():
    iv = {"pathology_report": 0.4, "molecular_report": 0.2, "prior_notes": 0.0}
    critical = {"critical_omission_rate": {"mean": 0.1, "lo": 0.0, "hi": 0.2}}
    contract = extract_contract(_pins(), iv, critical, _schema())
    json.dumps(contract)  # must be serializable
    assert contract["pins"]["seed"] == 7
    names = {e["name"] for e in contract["elements"]}
    assert names == {"pathology_report", "molecular_report", "prior_notes"}
    # minimal sufficient set keeps the informative elements, drops the useless one
    assert "pathology_report" in contract["minimal_sufficient_set_candidate"]
    assert "prior_notes" not in contract["minimal_sufficient_set_candidate"]


def test_unmeasured_element_is_null_not_zero():
    # molecular_report and prior_notes were never ablated in isolation, so they
    # are unmeasured — reported as null, distinct from a measured ~0.
    iv = {"pathology_report": 0.0}
    critical = {"critical_omission_rate": {"mean": 0.0, "lo": 0.0, "hi": 0.0}}
    contract = extract_contract(_pins(), iv, critical, _schema())
    by_name = {e["name"]: e for e in contract["elements"]}
    assert by_name["pathology_report"]["measured"] is True
    assert by_name["pathology_report"]["information_value"] == 0.0
    assert by_name["molecular_report"]["measured"] is False
    assert by_name["molecular_report"]["information_value"] is None
    assert by_name["prior_notes"]["measured"] is False


def test_contract_contains_no_phi_values():
    iv = {"pathology_report": 0.4}
    critical = {"critical_omission_rate": {"mean": 0.0, "lo": 0.0, "hi": 0.0}}
    contract = extract_contract(_pins(), iv, critical, _schema())
    blob = json.dumps(contract)
    # only element names + aggregate stats, never the case text
    assert "adenocarcinoma" not in blob
    assert "EGFR" not in blob


def test_evaluate_acceptance_min_and_max():
    metrics = {"critical_omission_rate": 0.05, "mean_score": 0.8}
    thresholds = {"critical_omission_rate_max": 0.10, "mean_score_min": 0.60}
    results = evaluate_acceptance(metrics, thresholds)
    assert all(r["passed"] for r in results)

    metrics_bad = {"critical_omission_rate": 0.5, "mean_score": 0.2}
    results_bad = evaluate_acceptance(metrics_bad, thresholds)
    assert not any(r["passed"] for r in results_bad)


def test_validation_report_flags_pass_and_carries_pins(tmp_path):
    summary = {
        "mean_score": {"mean": 0.8, "lo": 0.7, "hi": 0.9, "n": 45},
        "critical_omission_rate": {"mean": 0.05, "lo": 0.0, "hi": 0.1},
    }
    report = build_validation_report(
        _pins(),
        RunMeta(run_id="r", timestamp="2026-07-16T00:00:00Z", env_hash="e"),
        summary,
        AcceptanceSpec(thresholds={"critical_omission_rate_max": 0.10, "mean_score_min": 0.60}),
    )
    assert report["acceptance"]["overall_pass"] is True
    assert report["pins"]["seed"] == 7
    out = tmp_path / "report.json"
    render_report_json(report, out)
    assert json.loads(Path(out).read_text())["report_type"] == "validation_report"
