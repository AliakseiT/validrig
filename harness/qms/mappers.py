# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map harness results into structured QMS records (r05 shapes).

Design rule enforced here: the V&V *verdict* and pass/fail counts come from the
baseline (intended-input) condition — rubric items are the requirements/test
cases, the baseline is the validation, and the perturbations are reported as a
separate characterization / input-contract section, never as failed test cases.
Conflating them would render deliberate ablation sabotage as validation
failures.

Records are structured dicts; ``harness.qms.render`` turns them into YAML/Markdown.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from harness.models.pack import BatterySpec, Pack
from harness.models.results import Grade, Pins, RunMeta
from harness.perturb.expand import expand_battery
from harness.qms.attestation import build_attestation, unsigned_signoff
from harness.qms.baseline import TEMPLATE_SOURCES, TEMPLATE_VERSIONS


def _mode_for_sut(pack: Pack, sut_id: str) -> str:
    """Deterministic fake SUTs are dry-run evidence, never formal release."""
    sut = pack.sut(sut_id)
    if sut is not None and sut.binding.model_id == "fake":
        return "dry_run"
    return "formal_release_candidate"


def _mode_for_battery(pack: Pack, battery: BatterySpec) -> str:
    modes = {_mode_for_sut(pack, s) for s in battery.suts}
    return "dry_run" if modes == {"dry_run"} else "formal_release_candidate"


def _baseline_item_status(
    pack: Pack,
    battery: BatterySpec,
    grades: list[Grade],
) -> dict[str, str]:
    """Per-rubric-item pass/fail on the baseline (intended-input) condition.

    Baseline = no element ablated and the primary language. The mapping to units
    is re-derived by re-expanding the (pinned, deterministic) battery and joining
    on the content key, so no provenance needs to be persisted with grades.
    """
    units = expand_battery(pack, battery)
    provenance = {
        (u.case_id, u.perturbation_id, u.sample_idx): u.provenance for u in units
    }
    primary_lang = pack.manifest.languages[0] if pack.manifest.languages else None

    per_item: dict[str, list[float]] = defaultdict(list)
    for grade in grades:
        prov = provenance.get((grade.case_id, grade.perturbation_id, grade.sample_idx), {})
        dropped = prov.get("ablation", {}).get("dropped", [])
        lang = prov.get("language", {}).get("lang")
        if dropped:
            continue
        if lang is not None and primary_lang is not None and lang != primary_lang:
            continue
        for item_id, score in grade.item_scores.items():
            per_item[item_id].append(score)

    status: dict[str, str] = {}
    for item in pack.rubric.items:
        scores = per_item.get(item.id, [])
        if not scores:
            status[item.id] = "not_run"
        elif all(s >= item.max_score for s in scores):
            status[item.id] = "pass"
        else:
            status[item.id] = "fail"
    return status


def build_vv_plan(pack: Pack, battery: BatterySpec) -> dict[str, Any]:
    """Verification & Validation Plan from a battery + acceptance + manifest."""
    acceptance_criteria = [
        f"{metric} {'≤' if metric.endswith('_max') else '≥'} {limit}"
        for metric, limit in sorted(pack.acceptance.thresholds.items())
    ]
    return {
        "version": TEMPLATE_VERSIONS["verification_validation_plan"],
        "record_type": "verification_validation_plan",
        "generated_from_template": TEMPLATE_SOURCES["verification_validation_plan"],
        "required_fields": {
            "plan_id": f"VVP-{pack.manifest.id}-{battery.id}",
            "product_id": pack.manifest.id,
            "target_revision": f"{pack.manifest.version} / battery {battery.id} v{battery.version}",
            "campaign_mode": _mode_for_battery(pack, battery),
            "release_scope_decision_reference": "",
            "activity_type": "validation",
            "software_safety_classification": "not_applicable_with_rationale",
            "software_safety_classification_rationale": pack.manifest.device_status_rationale,
            "linked_inputs": {
                "design_input_baseline_reference": f"pack {pack.manifest.id} v{pack.manifest.version} (hash {pack.pack_hash[:16]})",
                "requirements": [i.id for i in pack.rubric.items],
                "risk_items": [i.id for i in pack.rubric.items if i.critical],
                "design_traceability_reference": "",
                "change_records": [],
                "anomaly_records": [],
            },
            "environments": [
                {
                    "name": "on-prem evaluation harness",
                    "purpose": "characterize and validate the input contract on local data",
                    "configuration_reference": f"engine + pinned SUT(s): {', '.join(sorted(battery.suts))}",
                }
            ],
            "formal_execution_gate": {
                "pre_gate_execution_policy": "dry_run_only",
                "approved_release_readiness_reference": "",
                "binary_deployment_reference": "",
                "configuration_capture_required_for_each_run": True,
            },
            "planned_test_cases": [
                {"test_case_id": i.id, "statement": i.statement.strip(), "critical": i.critical}
                for i in pack.rubric.items
            ],
            "acceptance_criteria": acceptance_criteria,
            "signoff": unsigned_signoff("Approved V&V Plan", ["qa_lead", "engineering_lead"]),
        },
    }


def build_vv_report(
    pack: Pack,
    battery: BatterySpec,
    pins: Pins,
    run_meta: RunMeta,
    grades: list[Grade],
    validation_report: dict[str, Any],
    contract: dict[str, Any],
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """V&V Report from a run: verdict from the baseline, characterization aside.

    ``calibration`` (agreement + gate) is optional and supplied by the async QMS
    step, not the synchronous run — a human grades over time, so at run time
    there is no calibration data. If the calibration gate blocks, the release
    recommendation is overridden accordingly.
    """
    item_status = _baseline_item_status(pack, battery, grades)
    passed = sum(1 for s in item_status.values() if s == "pass")
    failed = sum(1 for s in item_status.values() if s == "fail")
    not_run = sum(1 for s in item_status.values() if s == "not_run")

    acceptance = validation_report.get("acceptance", {})
    overall_pass = acceptance.get("overall_pass", False)
    recommendation = "approved_for_release" if overall_pass else "not_approved_for_release"

    calibration_block = calibration or {"status": "not_collected"}
    if calibration and calibration.get("gate", {}).get("blocks_report_issuance"):
        recommendation = "blocked_pending_calibration"

    deviations = [
        {"test_case_id": item_id, "status": status}
        for item_id, status in sorted(item_status.items())
        if status in ("fail", "not_run")
    ]

    # Characterization: NOT pass/fail. The input contract and robustness under
    # perturbation, reported separately so it can never inflate the failure count.
    characterization = {
        "input_contract": {
            "minimal_sufficient_set_candidate": contract.get("minimal_sufficient_set_candidate"),
            "elements": contract.get("elements"),
        },
        "robustness_full_battery": validation_report.get("summary", {}).get(
            "robustness_full_battery"
        ),
        "note": (
            "Perturbation results characterize the input contract and robustness; "
            "they are not release test-case pass/fail and do not affect the verdict."
        ),
    }

    return {
        "version": TEMPLATE_VERSIONS["verification_validation_report"],
        "record_type": "verification_validation_report",
        "generated_from_template": TEMPLATE_SOURCES["verification_validation_report"],
        "metadata": {
            "report_id": f"VVR-{pack.manifest.id}-{run_meta.run_id}",
            "product_id": pack.manifest.id,
            "plan_reference": f"VVP-{pack.manifest.id}-{battery.id}",
            "target_revision": f"{pack.manifest.version} / SUT {pins.sut_id} (hash {pins.sut_hash[:16]})",
            "report_date": run_meta.timestamp,
            "execution_mode": _mode_for_sut(pack, pins.sut_id),
        },
        "scope": {
            "activity_type": "validation",
            "covered_requirements": [i.id for i in pack.rubric.items],
            "covered_risk_controls": [i.id for i in pack.rubric.items if i.critical],
            "environment_tooling_references": build_attestation(pins, run_meta)["generated_by"],
            "configuration_capture_references": f"env_hash {run_meta.env_hash[:16]}",
            "reference_standard": sorted(
                {f"{a.adjudicated_by} ({a.adjudicated_at})" for a in pack.adjudications}
            )
            or ["none recorded"],
        },
        "summary_of_results": {
            "condition": "baseline (intended input)",
            "total_test_cases": len(pack.rubric.items),
            "passed": passed,
            "failed": failed,
            "blocked": 0,
            "not_run": not_run,
            "per_test_case": item_status,
        },
        "characterization": characterization,
        "calibration": calibration_block,
        "deviations_and_open_issues": deviations,
        "release_recommendation": recommendation,
        "attestation": build_attestation(pins, run_meta),
        "signatures": unsigned_signoff(
            "Approved V&V Evidence and Report", ["qa_lead", "engineering_lead"]
        ),
    }


def build_change_request(diff: dict[str, Any]) -> dict[str, Any]:
    """Change request + impact assessment from a RegressionDiff."""
    agg = diff["aggregate"]
    baseline = diff["baseline"]
    candidate = diff["candidate"]

    regressed_elements = [
        e for e in diff.get("element_deltas", [])
        if e["status"] in ("changed", "no_longer_measured") and (e["delta"] is None or e["delta"] < 0)
    ]
    elem_lines = [
        (
            f"{e['element']}: {e['status']}"
            + (f" (information value {e['delta']:+.4f})" if e["delta"] is not None else "")
        )
        for e in regressed_elements
    ]

    significant = agg.get("significant", False)
    direction = "regression" if agg["delta"] < 0 else "improvement"
    safety_impact = (
        f"Baseline mean score {agg['mean_score_baseline']:.4f} -> "
        f"{agg['mean_score_candidate']:.4f} (delta {agg['delta']:+.4f}, "
        f"{'significant' if significant else 'not significant'}). "
        f"{diff.get('n_regressions', 0)} rubric-item regressions across the battery."
    )

    return {
        "version": TEMPLATE_VERSIONS["change_request"],
        "record_type": "change_request",
        "generated_from_template": TEMPLATE_SOURCES["change_request"],
        "metadata": {
            "change_id": f"CHG-{candidate['run_id']}",
            "product_or_process_id": candidate["pins"]["pack_id"],
            "change_owner": "",
            "opened_on": "",
            "change_type": f"system-under-test version change ({direction})",
        },
        "change_summary": {
            "description": (
                f"System under test changed from '{baseline['pins']['sut_id']}' "
                f"(run {baseline['run_id']}) to '{candidate['pins']['sut_id']}' "
                f"(run {candidate['run_id']}) on the same pinned battery."
            ),
            "rationale": "Evaluate the impact of the system-under-test change before release.",
            "affected_baseline": {
                "pack": f"{baseline['pins']['pack_id']} v{baseline['pins']['pack_version']}",
                "baseline_run": baseline["run_id"],
                "candidate_run": candidate["run_id"],
            },
        },
        "impact_assessment": {
            "safety_performance_impact": safety_impact,
            "regressed_elements": elem_lines,
            "regulatory_compliance_impact": (
                "Revalidation event: a system-under-test change requires re-running "
                "validation and re-issuing the V&V report."
            ),
            "risk_records_affected": [],
            "verification_validation_impact": "Re-run the pinned battery and re-issue the V&V report.",
            "release_inclusion_decision": "deferred_pending_review",
            "binary_upgrade_regression_impact": (
                f"{diff.get('n_regressions', 0)} regressions / "
                f"{diff.get('n_improvements', 0)} improvements at rubric-item granularity."
            ),
        },
        "controls_and_actions": {
            "required_approvals": ["qa_lead", "engineering_lead"],
            "required_record_updates": ["verification_validation_report"],
            "verification_activities": ["re-run pinned battery", "review RegressionDiff"],
            "rollback_or_containment_plan": "",
        },
        "closure": {"linked_pr_or_release": "", "closure_summary": "", "closed_on": ""},
        "attestation": {
            "baseline": build_attestation(_pins_from(baseline["pins"])),
            "candidate": build_attestation(_pins_from(candidate["pins"])),
        },
        "signatures": unsigned_signoff(
            "Approved Change and Impact Assessment", ["qa_lead", "engineering_lead"]
        ),
    }


def _pins_from(pins_json: dict[str, Any]) -> Pins:
    return Pins(**pins_json)
