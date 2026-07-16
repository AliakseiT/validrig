# Harness Factory — Build Status

_Last updated: 2026-07-16 (overnight autonomous build)_

## What runs today

The engine (`harness/`) is use-case-agnostic; all use-case content lives in
`packs/`. Everything below runs fully offline and deterministically via a
first-class **fake model** and **fake judge**.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q                                   # 120 tests, ~3s
.venv/bin/harness new packs/my-pack --id my-pack      # scaffold a new pack
.venv/bin/harness lint packs/demo-tumor-board         # check a pack for authoring gaps
.venv/bin/harness run packs/demo-tumor-board --battery smoke --out ./runs --seed 1
.venv/bin/harness run packs/demo-tumor-board --battery regression --out ./runs --seed 1
.venv/bin/harness diff --out ./runs --baseline <run_a> --candidate <run_b>
.venv/bin/harness qms packs/demo-tumor-board --run <run_id> --out ./runs
.venv/bin/harness ui packs/demo-tumor-board --out ./runs   # calibration review UI (needs [ui] extra)
```

## Milestone status

| Milestone | Status | Notes |
|-----------|--------|-------|
| **M1 engine core** | ✅ complete | pack loader, casebank, LLM-call SUT adapter (+ OpenAI-compatible, mock-tested), ablation+format axes, judge grading, append-only SQLite+parquet store, bootstrap stats, InputContract + ValidationReport, `demo-tumor-board` demo, end-to-end + determinism + zero-leak gates |
| **M2 tumor-board tooling** | 🟡 authoring done | ✅ DE **language axis** + battery axis-scoping; **adjudication ingestion** (loader reads `rubric/adjudication/*.json` with referential integrity; gold flows into `pack_hash`); **`harness lint`** (rubric + adjudication-coverage checks); **`harness new`** scaffold (loads + runs out of the box). ❌ deferred (each needs real data / a clinical decision): **pseudonymization boundary** (Presidio+OpenMed; recall unverifiable on synthetic data), **PDF/OCR ingestion**, judge-vs-gold metric |
| **M3 regression discipline** | 🟢 done (core) | ✅ battery pinning, **RegressionDiff**, acceptance gating, CLI `diff`, native **G-Eval `LLMJudge`** (Gap 1), and now the **judge-calibration loop** (Gap 2): deterministic sampling, append-only human grades, Cohen's κ + % agreement, and a standalone **calibration gate** (advisory when underpowered). Surfaced in the review UI. Gate is kept out of the synchronous run/report path by design (calibration is asynchronous) |
| **Review UI (M2/M3)** | 🟡 v1 (calibration) | ✅ FastAPI + Jinja2 calibration review (dashboard, grade sampled generations, agreement/κ + gate), behind the `[ui]` extra; binds localhost by default; never mutates immutable grades. Data path tested via TestClient + live uvicorn smoke. ❌ deferred: clinical UX review, adjudication authoring (write-only until loader ingests it), multi-rater, SSO |
| **M4 agent SUTs** | ⬜ not started | trace protocol/tool mocks/process rubrics — schema seams exist (`SUTSpec.kind`, `Trace`/`Step`) |
| **M5 monitoring** | ⬜ not started | — |
| **QMS integration (§6)** | 🟡 core done | ✅ maps runs → **r05** (`QMS-2026-07-09-R005`) V&V plan, V&V report (baseline verdict; perturbations as characterization), and change request (from RegressionDiff); attestation over pinned inputs; unsigned drafts; `harness qms` / `qms-change`. ❌ deferred: PMS periodic report + AIMS event (need M5 monitoring inputs) |

## Proposals

- `docs/proposals/2026-07-16-m3-regression-fixes.md` — LLM judge ✅ shipped; calibration gate ✅ shipped
- `docs/proposals/2026-07-16-adjudication-calibration-ui.md` — calibration review UI ✅ v1 shipped
- `docs/proposals/2026-07-16-m2-tooling-fixes.md` — adjudication ingestion ✅ + rubric authoring CLI ✅ shipped; pseudonymization boundary + PDF/OCR not yet built

## Design guarantees proven by tests

- **Deterministic replay** (`test_end_to_end.py`, `test_cli.py`): two runs at the
  same seed produce byte-identical content (generations/grades/contract),
  in-process *and* across separate processes. Run id derives only from pins.
- **Zero use-case code in engine** (`test_no_usecase_leak.py`): the engine
  contains no use-case vocabulary. This gate already caught one real leak.
- **Contract distinguishes unknown from zero**: an element ablated only in a
  bundle (or never) is reported `measured: false, information_value: null`, not
  `0.0` — load-bearing for RegressionDiff (a newly-dropped dependency vs. a
  never-measured one).
- **Acceptance gates on the baseline** (intended-input) condition; ablation
  feeds the input contract and a separate robustness section, so a battery
  containing deliberate sabotage does not fail the baseline validation.

## Key demonstrations

- **Input contract** (`smoke`): pathology/molecular/imaging each carry
  information value ~0.33; prior_notes/meds are unmeasured (never isolated).
- **"What the new version broke"** (`regression`): a deliberately-regressed SUT
  that stopped reporting molecular findings. Both models still *pass* baseline
  acceptance (mean 0.67 > 0.60), but the diff pinpoints it: −0.27 mean score
  (significant), 36 item regressions, molecular_report information value
  −0.33. This is why acceptance thresholds alone are insufficient and the diff
  is the product.
- **Language sensitivity** (`multilingual`): in DE, diagnosis extraction fails
  (English-phrasing-dependent) while molecular/staging survive (language-
  invariant tokens).

## Deliberately deferred (need human input, not an overnight pass)

- **Pseudonymization boundary** (§5): a naive scrubber looks done while missing
  PHI. Demo data is synthetic, so nothing verifies it. Needs design attention.
- **Rubric adjudication / judge-calibration UI** (M2/M4): FastAPI review UI —
  design decisions + human-in-the-loop; can't be verified offline.
- **PDF/OCR ingestion** (M2): needs external binaries and real documents.
- **QMS templating** (§6): needs the `dearauditor-qms-baseline` templates to map
  against; risky to guess their structure.
- **Real model endpoints**: OpenAI-compatible adapter is built and mock-tested;
  no live call is made (no keys, and it would break the offline guarantee).

## Where the code is

- Plan: `docs/superpowers/plans/2026-07-16-harness-factory-m1.md`
- Engine: `harness/` — `models/`, `packio/`, `perturb/`, `sut/`, `judge/`,
  `store/`, `stats/`, `artifacts/`, `execute.py`, `diff.py`, `cli.py`
- Demo pack: `packs/demo-tumor-board/`
- Tests: `tests/` (one file per subsystem + integration gates)
- Git: local commits per task; nothing pushed.
