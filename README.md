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

## Publishing pinned evidence (`rig publish`)

`rig publish` turns a pack plus pinned runs into a site-ready content object —
authored plain-language prose merged with machine-derived numbers, and the real
validation dossier embedded as an HTML fragment:

```bash
.venv/bin/rig publish <pack-dir> \
  --runs ./runs \                      # run store root
  --run <dossier_run_id> --run <id2> \ # pinned runs (first supplies the dossier)
  --template pipeline \                # content shape (only 'pipeline' for now)
  --format ts \                        # ts (typed data module) or json
  --out site/src/pipelines/<slug>.ts
```

Split of responsibilities:

- **Authored prose** lives in a per-pack `publish.yaml` (default
  `<pack>/publish.yaml`, override with `--spec`): slug, title, summary, data
  provenance note, and the narrative arc (`task`, `risks`, `measurement`,
  `findings`, `meaning`) as HTML fragments. `--slug`/`--title` override the
  spec. The pack loader ignores `publish.yaml`, so authoring it never changes
  the pack hash or invalidates pinned runs (adding publish fields to the
  manifest would — that is why it is a separate file).
- **Machine numbers** are never hand-typed: prose references them as
  `{{fact|format-spec}}` placeholders resolved from run artifacts — e.g.
  `{{run.<id>.element.<name>.information_value|.3f}}`,
  `{{run.<id>.acceptance.<metric>.value}}`, `{{diff.<key>.delta|+.2f}}`
  (regression diffs recomputed from grades, declared under `diffs:` in the
  spec), and `{{file.<key>.<path>}}` for committed evidence JSON files declared
  under `fact_files:`. An unknown or unmeasured fact is a hard error.
- **The dossier** section embeds the first `--run`'s real dossier (rendered as
  an embeddable fragment) with its run hash and engine version. Publishing is
  refused when the pack directory no longer hashes to the runs' pinned
  `pack_hash` (override consciously with `--allow-pack-drift`).

## License

AGPL-3.0-or-later. See `LICENSE`.
