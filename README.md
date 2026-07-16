# The Harness Factory

An evaluation **harness factory** for LLM-based clinical workflows. Hospitals run it
on their own data, on-prem, to characterize, validate, and continuously monitor the
empirical *input contract* of every `(model version, intended use, local population)`
triple.

Standing up a rigorous harness for a **new intended use** is a content-authoring
exercise — a *pack* — not a software project. The engine (`harness/`) is
use-case-agnostic; everything use-case-specific lives in declarative, versioned
packs (`packs/`).

## Status

**M1 (engine core)** — pack loader, casebank, LLM-call SUT adapter (with a
deterministic fake model for offline/hermetic runs), ablation + format perturbation
axes, judge grading, append-only run store, basic stats, and the synthetic
`hello-tumor-board` demo pack that runs end-to-end and reproducibly.

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
.venv/bin/harness run packs/hello-tumor-board --battery smoke --out ./runs --seed 1
```

## License

AGPL-3.0-or-later. See `LICENSE`.
