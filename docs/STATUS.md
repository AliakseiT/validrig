# Harness Factory — Build Status

_Last updated: 2026-07-16 (overnight autonomous build)_

## What runs today

The engine (`harness/`) is use-case-agnostic; all use-case content lives in
`packs/`. Everything below runs fully offline and deterministically via a
first-class **fake model** and **fake judge**.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q                                   # 75 tests, ~2s
.venv/bin/harness run packs/hello-tumor-board --battery smoke --out ./runs --seed 1
.venv/bin/harness run packs/hello-tumor-board --battery regression --out ./runs --seed 1
.venv/bin/harness diff --out ./runs --baseline <run_a> --candidate <run_b>
```

## Milestone status

| Milestone | Status | Notes |
|-----------|--------|-------|
| **M1 engine core** | ✅ complete | pack loader, casebank, LLM-call SUT adapter (+ OpenAI-compatible, mock-tested), ablation+format axes, judge grading, append-only SQLite+parquet store, bootstrap stats, InputContract + ValidationReport, `hello-tumor-board` demo, end-to-end + determinism + zero-leak gates |
| **M2 tumor-board tooling** | 🟡 partial | ✅ DE **language axis** + battery axis-scoping + multilingual demo. ❌ deferred: rubric authoring/adjudication UI, PDF/OCR ingestion (need human/design input — not suitable for unattended build) |
| **M3 regression discipline** | 🟡 core done | ✅ battery pinning, **RegressionDiff** (item + per-element + aggregate w/ bootstrap significance), acceptance gating, CLI `diff`. ❌ deferred: judge calibration workflow (needs the review UI) |
| **M4 agent SUTs** | ⬜ not started | trace protocol/tool mocks/process rubrics — schema seams exist (`SUTSpec.kind`, `Trace`/`Step`) |
| **M5 monitoring** | ⬜ not started | — |

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
- Demo pack: `packs/hello-tumor-board/`
- Tests: `tests/` (one file per subsystem + integration gates)
- Git: local commits per task; nothing pushed.
