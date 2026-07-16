# SPDX-License-Identifier: AGPL-3.0-or-later
"""Battery execution orchestration.

Ties the pipeline together: expand a battery, generate with the SUT adapter,
grade each generation, analyze, and persist immutable results plus the derived
artifacts. One ``Run`` is produced per system under test (a run is a battery
snapshot against one SUT).

Content (generations, grades, contract) is a pure function of the pinned inputs
and the seed; wall-clock time enters only through an injected clock and lives in
run metadata, never in the compared content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import harness.perturb  # noqa: F401  (registers built-in axes)
from harness.artifacts.contract import extract_contract
from harness.artifacts.report import build_validation_report, render_report_json
from harness.envhash import env_hash
from harness.judge.grading import build_judge, grade_generation
from harness.models.pack import Case, Pack
from harness.models.results import (
    Generation,
    Grade,
    Pins,
    Run,
    RunMeta,
    TokenUsage,
    run_id_for,
)
from harness.perturb.expand import ExpansionUnit, expand_battery
from harness.perturb.format import DOCUMENT_KEY
from harness.stats.analyze import (
    GradedRecord,
    critical_rates,
    information_value,
    mean_score,
)
from harness.store.runstore import RunStore
from harness.sut.registry import build_adapter
from harness.version import ENGINE_VERSION


@dataclass(frozen=True)
class RunResult:
    run_id: str
    sut_id: str
    n_units: int
    usage: TokenUsage
    contract: dict
    report: dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _grading_case(pack: Pack, unit: ExpansionUnit) -> Case:
    """A minimal case for grading: the rendered document + adjudicated truth."""
    source = pack.case(unit.case_id)
    ground_truth = source.ground_truth if source else {}
    return Case(
        case_id=unit.case_id,
        elements={DOCUMENT_KEY: unit.document},
        ground_truth=ground_truth,
    )


def run_battery(
    pack: Pack,
    battery_id: str,
    store: RunStore,
    seed: int = 0,
    now: Callable[[], str] | None = None,
) -> list[RunResult]:
    battery = pack.battery(battery_id)
    if battery is None:
        raise KeyError(f"no such battery: {battery_id}")
    clock = now or _utc_now

    units = expand_battery(pack, battery)
    judge = build_judge(pack.judge)
    critical_items = tuple(i.id for i in pack.rubric.items if i.critical)

    results: list[RunResult] = []
    for sut_id in sorted(battery.suts):
        sut_spec = pack.sut(sut_id)
        if sut_spec is None:
            raise KeyError(f"battery references unknown SUT: {sut_id}")
        adapter = build_adapter(sut_spec)
        sut_units = [u for u in units if u.sut_id == sut_id]

        generations: list[Generation] = []
        grades: list[Grade] = []
        records: list[GradedRecord] = []
        total_usage = TokenUsage.zero()

        for unit in sut_units:
            out = adapter.generate(unit.document, seed)
            gen = Generation(
                case_id=unit.case_id,
                perturbation_id=unit.perturbation_id,
                sample_idx=unit.sample_idx,
                raw_output=out.raw_output,
                trace=out.trace.model_dump(mode="json"),
                usage=out.usage,
            )
            generations.append(gen)
            total_usage = total_usage + out.usage

            grade = grade_generation(pack.rubric, gen, _grading_case(pack, unit), judge, seed)
            grades.append(grade)

            dropped = tuple(unit.provenance.get("ablation", {}).get("dropped", []))
            records.append(
                GradedRecord(
                    perturbation_id=unit.perturbation_id,
                    dropped=dropped,
                    item_scores=grade.item_scores,
                    critical_items=critical_items,
                )
            )

        pins = Pins(
            pack_id=pack.manifest.id,
            pack_version=pack.manifest.version,
            pack_hash=pack.pack_hash,
            battery_id=battery.id,
            battery_version=battery.version,
            sut_id=sut_spec.id,
            sut_hash=sut_spec.sut_hash,
            judge_id=pack.judge.id,
            judge_version=pack.judge.version,
            seed=seed,
            engine_version=ENGINE_VERSION,
        )
        run_id = run_id_for(pins)
        run = Run(
            pins=pins,
            meta=RunMeta(run_id=run_id, timestamp=clock(), env_hash=env_hash()),
        )
        store.write_run(run)
        store.write_generations(run_id, generations)
        store.write_grades(run_id, grades)

        # Acceptance gates on the baseline (intended-input) condition: does the
        # system perform when given the information it is supposed to receive?
        # Ablation-driven degradation feeds the input contract and a separate
        # robustness section, not the acceptance verdict.
        baseline_records = [r for r in records if not r.dropped]
        ms_base = mean_score(baseline_records, seed=seed)
        cr_base = critical_rates(baseline_records, seed=seed)

        iv = information_value(records)
        cr_full = critical_rates(records, seed=seed)
        ms_full = mean_score(records, seed=seed)

        summary = {
            "condition": "baseline",
            "mean_score": ms_base,
            "critical_omission_rate": cr_base["critical_omission_rate"],
            "robustness_full_battery": {
                "mean_score": ms_full,
                "critical_omission_rate": cr_full["critical_omission_rate"],
                "n_units": len(records),
            },
        }
        contract = extract_contract(pins, iv, cr_full, pack.case_schema)
        report = build_validation_report(pins, run.meta, summary, pack.acceptance)

        run_dir = store.runs_dir / run_id
        (run_dir / "contract.json").write_text(
            json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8"
        )
        render_report_json(report, run_dir / "validation_report.json")

        results.append(
            RunResult(
                run_id=run_id,
                sut_id=sut_id,
                n_units=len(sut_units),
                usage=total_usage,
                contract=contract,
                report=report,
            )
        )

    return results
