# validrig

**validrig** — the engine of **DearAuditor Eval** (CLI: `rig`). An evaluation
**harness factory** for LLM-based clinical workflows. Hospitals run it
on their own data, on-prem, to characterize, validate, and continuously monitor the
empirical *input contract* of every `(model version, intended use, local population)`
triple.

Standing up a rigorous harness for a **new intended use** is a content-authoring
exercise — a *pack* — not a software project. The engine (`validrig/`) is
use-case-agnostic; everything use-case-specific lives in declarative, versioned
packs (`packs/`).

## Status

**M1 (engine core)** complete, plus slices of M2 and M3. See
[`docs/STATUS.md`](docs/STATUS.md) for the full picture.

- **M1** — pack loader, casebank, LLM-call SUT adapter (deterministic fake model
  for offline/hermetic runs, plus an OpenAI-compatible adapter), ablation +
  format perturbation axes, judge grading, append-only run store, bootstrap
  stats, InputContract + ValidationReport, and the synthetic `demo-tumor-board`
  demo pack that runs end-to-end and reproducibly.
- **M3 (core)** — **RegressionDiff**: diff two pinned runs at (case,
  perturbation, rubric-item), per-element contract, and aggregate granularity
  with bootstrap significance. `rig diff` surfaces "what the new version
  broke".
- **M2 (slice)** — DE **language axis** and battery axis-scoping.

## Design principles

- **New intended use = new pack, zero engine code.**
- **Deterministic replay + total versioning.** Every result is reproducible and
  attributable (model version, prompt, pack version, battery version, judge
  version, seed).
- **On-prem, PHI never leaves.** No external calls except explicitly configured
  model endpoints. The default SUT/judge are deterministic local fakes.
- **Immutable, append-only results.** Everything is a plain versioned file.

## Quick start

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q

# characterize the input contract for the demo pack
.venv/bin/rig run packs/demo-tumor-board --battery smoke --out ./runs --seed 1

# compare a baseline model against a (deliberately regressed) new version
.venv/bin/rig run packs/demo-tumor-board --battery regression --out ./runs --seed 1
.venv/bin/rig diff --out ./runs --baseline <baseline_run_id> --candidate <candidate_run_id>
```

## License

AGPL-3.0-or-later. See `LICENSE`.
