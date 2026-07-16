# Proposal: Adjudication & Calibration Review UI

**Status:** proposal · **Date:** 2026-07-16 · **Depends on:** M2 adjudication ingestion, M3 calibration workflow

This is the human-in-the-loop surface for two jobs the engine deliberately does
not automate (design doc: "rubrics are authored + adjudicated by clinicians"):

1. **Adjudication** (M2) — a clinician assigns reference scores to cases against
   the rubric, producing the gold standard.
2. **Calibration** (M3) — a clinician double-grades a sampled slice of a run's
   generations, producing the judge–human agreement that gates report issuance.

Both are the *same interaction* — a person reads context and scores rubric items
— so they share one UI and one data path.

## Design principles

- **Minimal web form, not notebooks.** Physicians won't run notebooks (design
  doc open questions). A plain server-rendered form, fast and legible.
- **Boring, thin, on-prem.** FastAPI + server-rendered HTML (Jinja2), no SPA
  framework, no build step — consistent with "readable by a hospital IT
  generalist" and the `ui` service already named in the docker-compose plan
  (design doc §5). It reads the same SQLite + parquet store the engine writes.
- **Append-only, attributable.** Every human grade is an immutable record with
  grader identity and timestamp — it becomes QMS evidence.
- **PHI stays on-prem.** The UI is served only on the single node; it renders
  pseudonymized case content already in the store. No external calls.

## What it reads and writes (attaches to existing seams)

- **Reads:** `RunStore.read_generations` / `read_grades` / `read_run` (exist);
  the pack's `Rubric` and `Case` content; the calibration sample from
  `harness/calibration/sample.py` (M3 proposal).
- **Writes:**
  - adjudications → `rubric/adjudication/<case>.json` (the `Adjudication` model,
    M2 proposal).
  - calibration grades → an append-only `calibration/` record family, folded
    into `Grade.human_agreement` (the slot already on the immutable `Grade`).
- **Never mutates** a `Generation` or the judge's `Grade` — human grades are a
  parallel, additive layer.

## Screens

### 1. Queue / dashboard
- Two work queues: **Adjudication needed** (cases with no/partial adjudication)
  and **Calibration needed** (sampled generations awaiting a second grade).
- Per queue: count, progress bar, and current judge–human κ per rubric item
  (green/amber/red against `judge_agreement_kappa_min`). This is where a reviewer
  sees "the judge is drifting on item_staging" at a glance.

### 2. Grading form (shared by both jobs)
```
┌ Case C001 · perturbation ablation:none|format:structured ─────────────┐
│ CONTEXT (pseudonymized, rendered document)          [collapsible per   │
│   ## pathology_report … ## molecular_report … …      element section]   │
├───────────────────────────────────────────────────────────────────────┤
│ MODEL OUTPUT (calibration only — hidden during blind adjudication)      │
│   TUMOR BOARD BRIEF … FINDINGS … (the SUT generation being graded)      │
├───────────────────────────────────────────────────────────────────────┤
│ RUBRIC                                                                   │
│  ▸ item_diagnosis (critical)  [ pass | fail ]  evidence:[__________]    │
│  ▸ item_molecular             [ pass | fail ]  evidence:[__________]    │
│  ▸ item_staging               [ 0 · 0.5 · 1 ]  note:[_______________]   │
├───────────────────────────────────────────────────────────────────────┤
│ grader: dr_x   [ Save & next ]   [ Skip ]   [ Flag for discussion ]     │
└───────────────────────────────────────────────────────────────────────┘
```
- Binary items render as pass/fail; graded items as a scale — driven by
  `RubricItem.type` (already in the schema).
- **Blind mode for adjudication:** the model output panel is hidden so the gold
  standard is not anchored by the model. For calibration it is shown (the point
  is to grade the model's output).
- Evidence-pointer capture when `RubricItem.evidence_required` (already a field).

### 3. Agreement / calibration report
- Per item, per grader: percent agreement, Cohen's κ, confusion of judge vs
  human, and the specific generations where they disagree (click through to the
  form). Drift versus the previous calibrated run is shown as a delta.
- A **"issue-blocked" banner** when κ is below threshold — mirrors the
  `blocked_calibration` state the ValidationReport/QMS V&V report will carry.

## Endpoints (thin)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | queues + κ dashboard |
| GET | `/adjudicate/{case_id}` | blind grading form for a case |
| POST | `/adjudicate/{case_id}` | write `Adjudication` record |
| GET | `/calibrate/{run_id}/next` | next sampled generation for this grader |
| POST | `/calibrate/{run_id}/{content_key}` | write human grade → `human_agreement` |
| GET | `/agreement/{run_id}` | κ / disagreement report |

## Identity & audit

- Grader identity from a simple configured login (single-node; hospital SSO is a
  later option). Every write records `grader_id` + timestamp → the append-only
  record. This is what makes double-grading attributable QMS evidence and feeds
  the "who, when, values" the adjudication record requires.

## Verification

- API tests with FastAPI's `TestClient`: posting an adjudication writes a
  well-formed `Adjudication` JSON; posting a calibration grade updates
  `human_agreement` and never mutates the judge `Grade`; κ dashboard reflects a
  seeded agreement fixture.
- A blind-mode test: the adjudication form response does not contain the model
  output string.

## Scope / phasing

- **v1 (pilot-blocking):** queues, the two grading flows, agreement report, the
  issue-blocked gate. Server-rendered, single grader-at-a-time.
- **Deferred:** multi-rater consensus/discussion threads, SSO, live re-grading,
  rubric *authoring* in the browser (CLI `rubric lint` + scaffold covers authoring
  first; browser authoring is a later convenience).

## Why this ordering

The engine already produces everything the UI displays and consumes everything
the UI writes back — the seams (`human_agreement`, `Adjudication`,
`calibration_fraction`, the store readers) exist or are defined in the M2/M3
proposals. The UI is therefore the *last* piece, not the first: it operationalizes
a data path that is already closed, which is why it was correctly deferred out of
the autonomous build (it needs product/clinical design decisions and can't be
verified offline the way the engine can).
