# Proposal: Completing M3 (Regression Discipline)

**Status:** proposal · **Date:** 2026-07-16 · **Depends on:** M1 engine, RegressionDiff (shipped)

M3's exit is "model-swap demo — here's what the new version broke." The
RegressionDiff, battery pinning, and acceptance gating are shipped. Two gaps
remain before M3 is trustworthy end-to-end. Both attach to seams that already
exist in the code.

---

## Gap 1 — A real, pinned LLM judge (not only the fake)

**Why it matters.** Today grading runs through `FakeJudge` (substring match on
adjudicated evidence). That is correct for hermetic tests and offline demos, but
a real harness grades free-text output with an LLM judge. The whole M3 discipline
("a judge upgrade is a revalidation event") is inert until there is a real judge
to pin.

**The seam that already exists.** `harness/judge/grading.py:build_judge` already
branches on `judge_spec.kind` and references an unimplemented
`harness.judge.llm.LLMJudge` for `kind == "openai_compat"`. `JudgeSpec`
(`harness/models/pack.py`) already carries `id`, `version`, `binding`. The
`Judge` ABC (`harness/judge/base.py`) already defines the exact contract:
`grade_item(item, document, output, ground_truth, seed) -> (score, note)`.

**Design.**
- Implement `harness/judge/llm.py:LLMJudge(Judge)`. It reuses the SUT transport
  layer (`OpenAICompatModel`'s httpx client pattern) — the judge is just another
  pinned model call. Per-item grading prompts come from the pack (`judge.yaml`
  gains a `grading_prompts` map keyed by rubric item `type`, per design doc §2).
- The judge model id + version go into `Pins.judge_id` / `Pins.judge_version`
  (already present). So a judge swap changes the run id — a judge upgrade is
  already, structurally, a new run and therefore a diffable revalidation event.
  **No new versioning machinery is required**; it falls out of the spine.
- Determinism: LLM judge calls are `reproducible = False` (same flag as live
  SUTs). A judge-graded run is excluded from a regression *baseline* unless its
  grades are frozen (recorded). This mirrors the SUT record/replay rule.

**Don't reinvent the judging metrics — hook into maintained OSS.**

- **DeepEval** (Apache-2.0) — a local-first LLM-eval framework. It runs
  LLM-as-judge metrics **locally with a custom/local judge model** (not tied to
  OpenAI), and its cloud platform (Confident AI) is **opt-in only** — no data
  leaves the node unless a user runs `deepeval login`. For PHI-never-leaves,
  document "do not authenticate, disable telemetry" as a deployment control.
  Its **G-Eval** metric is the strongest fit: you write criteria, inspect the
  generated `evaluation_steps`, then **lock them in** for reproducible scores —
  which is exactly our judge-pinning discipline. Pin the G-Eval `evaluation_steps`
  + judge model id/version into `Pins`; a change to either is a revalidation event.
- **Inspect** (`inspect_ai`, MIT) — worth adopting when M4 lands: it is built for
  reproducible, tool-using-agent evaluation and log-based replay, aligning with
  our agent-SUT and determinism goals.
- **RAGAS** — reference-free RAG metrics, for chain/RAG SUTs.

**Architecture: library behind our `Judge` ABC, control stays here.** The harness
keeps the pinning, the run store, and the determinism spine; DeepEval/G-Eval is an
optional *grading backend* behind `Judge.grade_item`, not a replacement engine —
otherwise we lose our versioning discipline. Keep it behind an optional extra
(`pip install harness-factory[judge]`) so the core stays thin.

**Verification.** Unit-test `LLMJudge` request/response mapping with
`httpx.MockTransport` (exactly as `test_sut_openai_compat.py` does). For a
DeepEval-backed judge, test with a stubbed local model so CI stays offline. Add a
diff test: two runs identical except `judge_version` (or the pinned G-Eval steps)
produce different run ids and a RegressionDiff that attributes the score change to
the judge, not the SUT.

---

## Gap 2 — The judge-calibration workflow (the report-issuance gate)

**Why it matters.** Design doc §4: "Judge disagreement or drift beyond threshold
blocks report issuance." Right now `ValidationReport.human_agreement` is a
hard-coded `{"status": "not_collected"}` placeholder (`harness/artifacts/report.py`).
Nothing samples, nothing compares, nothing gates. Without this, an LLM judge's
grades are unvalidated and the validation report overclaims.

**The seams that already exist.**
- `JudgeSpec.calibration_fraction` (default 0.1) — the sampling rate, already in
  the schema and the demo `judge.yaml`.
- `Grade.human_agreement: dict[str, bool] | None` — the per-item slot for
  agreement, already on the immutable record.
- `packs/*/rubric/adjudication/*.json` — the physician-adjudication file
  structure already exists (though the loader does not yet read it; see the M2
  proposal, which wires adjudication ingestion).

**Design.**
1. **Sampling** (`harness/calibration/sample.py`): deterministically select
   `ceil(calibration_fraction * n)` generations for double-grading, seeded by the
   run's `seed` so the sample is reproducible and auditable. Selection is a pure
   function of `(sorted content keys, seed, fraction)` — no RNG state.
2. **Collection**: the sampled generations are handed to the adjudication UI
   (see the UI proposal) which writes human grades back as
   `Grade.human_agreement` per item. Human grades live in an append-only
   `calibration/` record family alongside `generations.parquet`.
3. **Agreement stats** (`harness/calibration/agreement.py`): per rubric item and
   per grader, compute percent agreement and Cohen's κ (binary items) between
   judge score and human score. Keep it simple and citable — κ, not a bespoke
   metric. Bootstrap CI reuses `harness/stats/bootstrap.py`.
4. **The gate** (`harness/calibration/gate.py`): `acceptance.yaml` gains
   `judge_agreement_kappa_min` (interpreted by the existing
   `evaluate_acceptance` naming convention — no new evaluator). If κ is below the
   threshold, or drifts beyond a delta versus the previous calibrated run,
   `build_validation_report` sets `release_recommendation = blocked_calibration`
   and refuses `overall_pass`. This slots directly into the acceptance results
   list already rendered in the report and the QMS V&V report.

**Drift as a first-class diff.** A drop in judge–human κ between two runs is
itself a RegressionDiff dimension. Extend `diff_contracts`-style logic with a
`calibration` block so "the judge got less reliable" is surfaced with the same
machinery as "the model got worse."

**Verification.** Golden test: a synthetic calibration set where judge and human
agree fully → κ = 1.0, report issues. Flip 40% of human grades → κ drops below
threshold → report blocked. Assert the QMS V&V report reflects
`blocked_calibration` and stays unsigned.

---

## Non-goals for this proposal

- The adjudication UI itself (separate proposal) — this defines the data model
  and gate it must satisfy.
- Multi-rater consensus beyond two-way κ (future; the record model already allows
  multiple graders keyed by grader id).

## Summary of new/changed surfaces

| Surface | Change |
|---|---|
| `harness/judge/llm.py` | new — pinned OpenAI-compatible judge; optional DeepEval/G-Eval backend behind an extra |
| `pyproject.toml` | optional `judge` extra (deepeval / inspect_ai) |
| `judge.yaml` | add `grading_prompts` per item type; optional pinned G-Eval `evaluation_steps` |
| `harness/calibration/{sample,agreement,gate}.py` | new module |
| `acceptance.yaml` | add `judge_agreement_kappa_min` |
| `harness/artifacts/report.py` | replace `human_agreement` placeholder with real stats + gate |
| `harness/diff.py` | add `calibration` delta block |

## Open-source building blocks (verified 2026-07-16)

- DeepEval — Apache-2.0, local-first LLM-as-judge, custom/local judge models,
  cloud opt-in only; G-Eval supports lockable `evaluation_steps`.
  <https://github.com/confident-ai/deepeval>
- Inspect (`inspect_ai`) — MIT, reproducible agent/tool evaluation.
  <https://github.com/UKGovernmentBEIS/inspect_ai>
- RAGAS — RAG evaluation metrics. <https://github.com/explodinggradients/ragas>
