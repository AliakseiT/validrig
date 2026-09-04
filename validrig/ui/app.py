# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI app for judge calibration review.

The app factory takes the pack, the run store, and a calibration store, plus the
active grader identity. It renders sampled generations for double-grading and
computes judge-human agreement. It is deliberately small and stateless beyond the
two stores.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from validrig.pathsafe import is_safe_id

from validrig.authoring.adjudicate import adjudicated_case_ids, write_adjudication
from validrig.calibration.agreement import compute_agreement
from validrig.calibration.gate import evaluate_gate
from validrig.calibration.models import HumanGrade
from validrig.calibration.sample import select_calibration_sample
from validrig.calibration.store import CalibrationStore
from validrig.models.pack import Adjudication, Pack
from validrig.perturb.expand import expand_battery
from validrig.perturb.format import DOCUMENT_KEY, FormatTransformer
from validrig.store.runstore import RunStore

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

DEFAULT_KAPPA_MIN = 0.6


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _key_str(key: tuple[str, str, int]) -> str:
    return f"{key[0]}::{key[1]}::{key[2]}"


def _parse_key(s: str) -> tuple[str, str, int]:
    case_id, perturbation_id, sample_idx = s.split("::")
    return (case_id, perturbation_id, int(sample_idx))


def _guard_id(value: str, kind: str) -> str:
    """Reject unsafe path-parameter ids with a 400 before any filesystem use."""
    if not is_safe_id(value):
        raise HTTPException(status_code=400, detail=f"invalid {kind}")
    return value


def create_app(
    pack: Pack,
    store: RunStore,
    calib_store: CalibrationStore,
    grader_id: str = "reviewer",
    now: Callable[[], str] | None = None,
    pack_dir: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="validrig — Review")
    clock = now or _utc_now
    kappa_min = pack.acceptance.thresholds.get("judge_agreement_kappa_min", DEFAULT_KAPPA_MIN)
    fraction = pack.judge.calibration_fraction

    def _documents_for(run_id: str) -> dict[tuple, str]:
        run = store.read_run(run_id)
        battery = pack.battery(run.pins.battery_id)
        if battery is None:
            return {}
        return {
            (u.case_id, u.perturbation_id, u.sample_idx): u.document
            for u in expand_battery(pack, battery)
        }

    def _sample_for(run_id: str) -> list[tuple]:
        run = store.read_run(run_id)
        gens = store.read_generations(run_id)
        keys = [(g.case_id, g.perturbation_id, g.sample_idx) for g in gens]
        return select_calibration_sample(keys, fraction, seed=run.pins.seed)

    def _run_summary(run_id: str) -> dict[str, Any]:
        sample = _sample_for(run_id)
        graded = calib_store.graded_keys(run_id)
        agreement = compute_agreement(
            store.read_grades(run_id), calib_store.read_human_grades(run_id)
        )
        gate = evaluate_gate(agreement, kappa_min)
        run = store.read_run(run_id)
        return {
            "run_id": run_id,
            "sut_id": run.pins.sut_id,
            "sample_size": len(sample),
            "graded_count": len(graded & set(sample)),
            "gate": gate,
            "overall": agreement["overall"],
        }

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        runs = [_run_summary(rid) for rid in store.list_runs()]
        return _TEMPLATES.TemplateResponse(
            request,
            "dashboard.html",
            {"runs": runs, "grader_id": grader_id, "kappa_min": kappa_min, "fraction": fraction},
        )

    @app.get("/calibrate/{run_id}", response_class=HTMLResponse)
    def calibrate_run(request: Request, run_id: str):
        _guard_id(run_id, "run_id")
        sample = _sample_for(run_id)
        graded = calib_store.graded_keys(run_id)
        rows = [
            {"key": _key_str(k), "case_id": k[0], "perturbation_id": k[1],
             "graded": k in graded}
            for k in sample
        ]
        return _TEMPLATES.TemplateResponse(
            request, "calibrate_list.html", {"run_id": run_id, "rows": rows}
        )

    @app.get("/calibrate/{run_id}/unit", response_class=HTMLResponse)
    def calibrate_unit(request: Request, run_id: str, key: str):
        _guard_id(run_id, "run_id")
        content_key = _parse_key(key)
        documents = _documents_for(run_id)
        gens = {(g.case_id, g.perturbation_id, g.sample_idx): g for g in store.read_generations(run_id)}
        gen = gens.get(content_key)
        return _TEMPLATES.TemplateResponse(
            request,
            "calibrate_unit.html",
            {
                "run_id": run_id,
                "key": key,
                "case_id": content_key[0],
                "perturbation_id": content_key[1],
                "document": documents.get(content_key, ""),
                "output": gen.raw_output if gen else "(generation not found)",
                "items": pack.rubric.items,
            },
        )

    @app.post("/calibrate/{run_id}/unit")
    async def submit_unit(request: Request, run_id: str):
        _guard_id(run_id, "run_id")
        form = await request.form()
        content_key = _parse_key(str(form["key"]))
        item_scores: dict[str, float] = {}
        for item in pack.rubric.items:
            field = f"score__{item.id}"
            if field in form and str(form[field]) != "":
                item_scores[item.id] = float(str(form[field]))
        grade = HumanGrade(
            run_id=run_id,
            case_id=content_key[0],
            perturbation_id=content_key[1],
            sample_idx=content_key[2],
            grader_id=grader_id,
            item_scores=item_scores,
            note=str(form.get("note", "")),
            created_at=clock(),
        )
        calib_store.append_human_grade(grade)
        return RedirectResponse(url=f"/calibrate/{run_id}", status_code=303)

    @app.get("/agreement/{run_id}", response_class=HTMLResponse)
    def agreement_view(request: Request, run_id: str):
        _guard_id(run_id, "run_id")
        agreement = compute_agreement(
            store.read_grades(run_id), calib_store.read_human_grades(run_id)
        )
        gate = evaluate_gate(agreement, kappa_min)
        return _TEMPLATES.TemplateResponse(
            request,
            "agreement.html",
            {"run_id": run_id, "agreement": agreement, "gate": gate, "kappa_min": kappa_min},
        )

    # ---- adjudication (per-case gold authoring; blind mode) ---------------

    def _render_case_document(case) -> str:
        rendered = FormatTransformer().expand(case, pack.case_schema, {"style": "structured"})
        return str(rendered[0].case.elements[DOCUMENT_KEY])

    @app.get("/adjudicate", response_class=HTMLResponse)
    def adjudicate_list(request: Request):
        done = adjudicated_case_ids(pack_dir) if pack_dir else set()
        rows = [
            {"case_id": c.case_id, "adjudicated": c.case_id in done}
            for c in sorted(pack.cases, key=lambda c: c.case_id)
        ]
        total = len(rows)
        completed = sum(1 for r in rows if r["adjudicated"])
        return _TEMPLATES.TemplateResponse(
            request,
            "adjudicate_list.html",
            {
                "rows": rows,
                "writable": pack_dir is not None,
                "total": total,
                "completed": completed,
            },
        )

    @app.get("/adjudicate/{case_id}", response_class=HTMLResponse)
    def adjudicate_case(request: Request, case_id: str):
        _guard_id(case_id, "case_id")
        case = pack.case(case_id)
        existing = pack.adjudication(case_id)
        elements = []
        if case:
            for spec in pack.case_schema.elements:
                val = case.elements.get(spec.name)
                if val is not None:
                    elements.append({
                        "name": spec.name,
                        "label": spec.name.replace("_", " ").title(),
                        "required": spec.required,
                        "value": val,
                    })
        return _TEMPLATES.TemplateResponse(
            request,
            "adjudicate_form.html",
            {
                "case_id": case_id,
                "elements": elements,
                "items": pack.rubric.items,
                "ground_truth": case.ground_truth if case else {},
                "existing": existing,
                "writable": pack_dir is not None,
            },
        )

    @app.post("/adjudicate/{case_id}")
    async def submit_adjudication(request: Request, case_id: str):
        if pack_dir is None:
            return RedirectResponse(url="/adjudicate", status_code=303)
        _guard_id(case_id, "case_id")
        if pack.case(case_id) is None:
            raise HTTPException(status_code=400, detail="unknown case_id")
        form = await request.form()
        values: dict[str, float] = {}
        for item in pack.rubric.items:
            field = f"score__{item.id}"
            if field in form and str(form[field]) != "":
                values[item.id] = float(str(form[field]))
        write_adjudication(
            pack_dir,
            Adjudication(
                case_id=case_id,
                adjudicated_by=grader_id,
                adjudicated_at=clock(),
                values=values,
            ),
        )
        return RedirectResponse(url="/adjudicate", status_code=303)

    return app
