# Proposal: Completing M2 (Tumor-Board Pack Tooling)

**Status:** proposal · **Date:** 2026-07-16 · **Depends on:** M1 engine, language axis (shipped)

M2's exit is "first hospital pilot executable." The language axis, InputContract
extraction, and ValidationReport rendering are shipped. The remaining gaps are
the content-authoring and ingestion tooling that turn a pile of hospital
documents into a runnable pack. Each attaches to an existing seam.

---

## Gap 1 — Adjudication ingestion (small but load-bearing)

**The gap.** `packs/*/rubric/adjudication/*.json` files exist in the demo and are
described in the design doc as "per-case physician adjudications (who, when,
values)", but `harness/packio/loader.py` never reads them. The ground truth used
for grading currently lives inline in each case's `ground_truth`. That conflates
two different things: the *evidence* a case contains and the *adjudicated
reference scores* a physician assigned.

**Design.**
- Extend the loader to read `rubric/adjudication/*.json` into an `Adjudication`
  model (`case_id`, `adjudicated_by`, `adjudicated_at`, `values: {item_id:
  score}`), attached to the `Pack`.
- These adjudicated values are the reference for judge-calibration agreement
  (see the M3 proposal) and for the "gold" baseline in the ValidationReport.
- Keep `Case.ground_truth` for the machine-checkable evidence tokens; adjudication
  is the human reference layer on top. Both feed grading, distinctly.

**Verification.** Loader test: demo pack exposes 3 adjudications; a case with a
missing adjudication is flagged (not silently zero — same discipline as the
contract's measured/unmeasured fix).

---

## Gap 2 — Casebank ingestion + pseudonymization boundary

**The gap.** Design doc §5: `ingest → pseudonymize → casebank`. There is no
ingestion path today; cases are hand-authored JSON. A pilot needs to turn real
(PDF/text) hospital documents into pseudonymized, schema-typed cases — and PHI
must never enter the engine's storage.

**Design (the boundary is the product-critical part).**
- New `harness/ingest/` module, explicitly the *only* component that ever sees
  raw PHI. Everything downstream sees pseudonyms.
- **Pseudonymization** is not a naive regex scrubber (a scrubber that looks done
  while missing PHI is worse than none). Design it as: (a) structured-field
  redaction driven by the pack's `ElementSpec` metadata (source_system, modality)
  where fields are known; (b) a pluggable NER-based detector for free text; (c) a
  **re-identification table kept hospital-side, outside engine storage** (design
  doc §5) — the engine only ever persists the pseudonym map's *keys*, never the
  reverse mapping.
- **This gap needs human/clinical design review before build** — it is a safety
  boundary, not a mechanical transform. This proposal defines the interface and
  the invariant ("no raw identifier crosses into `store/`"); the detector policy
  is a deliberate, reviewed decision, not an overnight pass.

**Verification.** An ingestion test asserts the invariant directly: feed a
document with known synthetic identifiers, assert none appear in the resulting
casebank JSON or in any `store/` artifact. A property test over the boundary is
the real gate here.

---

## Gap 3 — PDF/OCR ingestion helpers

**The gap.** Design doc M2 lists "PDF/OCR ingestion helpers." Clinical source
documents arrive as PDFs and scans.

**Design.**
- `harness/ingest/pdf.py`: text-layer extraction first (pdfminer/pypdf); OCR
  fallback (tesseract via `pytesseract`) only when no text layer exists. OCR is
  an optional extra dependency — the core engine stays thin (a hospital without
  scanned docs never installs it).
- Output flows into Gap 2's pseudonymization boundary *before* becoming a case.
  OCR text is PHI-bearing and must not bypass the boundary.
- Per-element provenance (source file, page, OCR-vs-text-layer, confidence) is
  captured into `ElementSpec`-adjacent metadata so the contract can later
  correlate performance with input quality.

**Scope note.** External binary (tesseract) and real documents mean this is not
offline-verifiable in CI beyond a tiny bundled text-layer PDF fixture. Gate OCR
behind an optional extra and a skip-if-missing test.

---

## Gap 4 — Rubric authoring workflow

**The gap.** Standing up a pack should be "a content-authoring exercise, not a
software project" (design goal #1). Rubric authoring is currently raw YAML editing.

**Design (tooling assists; clinicians author + adjudicate).**
- A `harness rubric lint` command: validates `rubric.yaml` against the schema,
  checks every rubric item has grading instructions and (if `evidence_required`)
  an evidence pointer, flags critical items lacking adjudication coverage.
- A scaffold command `harness pack new <id>` that emits the directory skeleton
  (manifest, schema, empty casebank, rubric stub, perturbations, battery, judge,
  acceptance) so a new intended use starts from a valid, documented template —
  reinforcing "new intended use = new pack, zero engine code."
- The interactive authoring/adjudication surface is the UI (separate proposal);
  this gap is the CLI validation + scaffolding underneath it.

**Verification.** `rubric lint` golden tests over a good pack (passes) and
several malformed rubrics (each flagged with a specific message).

---

## Summary of new/changed surfaces

| Surface | Change |
|---|---|
| `harness/packio/loader.py` | read `rubric/adjudication/*.json` into `Adjudication` |
| `harness/models/pack.py` | add `Adjudication` model; attach to `Pack` |
| `harness/ingest/` | new — pseudonymization boundary (needs review), PDF/OCR |
| `harness/cli.py` | add `rubric lint`, `pack new` |
| `pyproject.toml` | optional `ocr` extra (pytesseract) |

**Ordering.** Gap 1 (adjudication ingestion) is small and unblocks M3
calibration — do it first. Gap 2 (pseudonymization) needs a design review before
code. Gaps 3–4 are independent and parallelizable.
