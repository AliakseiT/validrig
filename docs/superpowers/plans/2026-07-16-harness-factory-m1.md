# Harness Factory — M1 Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M1 engine core of the Harness Factory: a pack loader, casebank, LLM-call SUT adapter (with a deterministic fake model), ablation + format perturbation axes, judge grading, an append-only run store, basic stats, and a synthetic `hello-tumor-board` pack that runs end-to-end offline and reproducibly.

**Architecture:** A Python package (`harness`) with a strict separation between *engine code* (use-case-agnostic) and *content* (declarative, versioned packs). The engine treats every system-under-test as an opaque `SystemUnderTest` producing traces. Results (Run/Generation/Grade) are immutable, fully version-pinned records persisted to SQLite (metadata) + parquet (generations/grades). A deterministic fake model makes the whole pipeline runnable and testable offline; the real OpenAI-compatible adapter is built to the same interface and unit-tested with a mocked transport. Determinism is proven by a test that runs the demo pack twice and asserts content (excluding timestamps/env-hash) is byte-identical.

**Tech Stack:** Python 3.12, pydantic v2, pyarrow (parquet), httpx (real adapter), numpy (bootstrap stats), PyYAML (pack files), pytest. SQLite via stdlib. No scipy, no server DB, no web framework in M1.

## Global Constraints

- **Zero engine code per pack.** Engine must contain no use-case strings. Literal test: `grep -ri "tumor\|pathology_report\|molecular_report" harness/` (the engine package) returns zero hits. Use-case logic lives only in `packs/`.
- **Python 3.12** (`python3.12` on this machine; no `uv`, use stdlib `venv` + `pip`).
- **AGPL-3.0-or-later** license; SPDX header on every source file: `# SPDX-License-Identifier: AGPL-3.0-or-later`.
- **Thin pinned deps only:** pydantic v2, pyarrow, httpx, numpy, PyYAML, pytest. No scipy, no pandas, no ORM, no web framework.
- **Immutable, append-only results.** Never mutate a Run/Generation/Grade after write.
- **Content vs run-metadata separation.** Timestamp and env-hash are isolable fields, never mixed into the content blobs that determinism/regression diffs compare.
- **Deterministic replay.** Fake model + fake judge are pure functions of (input, prompt, seed). Record-once/replay seam: grading and analysis read stored generations, never re-invoke the SUT.
- **Cost meter first-class.** Token/cost accounting threaded through execution from day one (fake model returns token counts).
- **Boring > clever.** Readable by a hospital IT generalist. Small focused files.
- **Local git commits per task. Do NOT push.**
- **Scope fence (M1 only):** no FastAPI/UI, no order/noise/language/length axes, no PDF/OCR, no RegressionDiff, no agent SUT, no monitoring. Leave seams (SUT base class, transformer registry, artifact schemas designed for later aggregation); implement none of M2–M5.

---

## File Structure

```
factory/
├── pyproject.toml              # deps, pytest config, package metadata
├── LICENSE                     # AGPL-3.0
├── README.md
├── .gitignore
├── harness/                    # ENGINE — use-case-agnostic
│   ├── __init__.py
│   ├── version.py              # engine version constant
│   ├── hashing.py              # canonical JSON + content hashing
│   ├── envhash.py              # environment hash (python, deps, engine version)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── pack.py             # IntendedUsePack, Manifest, CaseSchema, Case, Rubric, ...
│   │   ├── sut.py              # SystemUnderTest, SUTBinding, Trace, Step
│   │   └── results.py          # Run, Generation, Grade (immutable, pinned)
│   ├── packio/
│   │   ├── __init__.py
│   │   └── loader.py           # load + validate + content-hash a pack dir
│   ├── perturb/
│   │   ├── __init__.py
│   │   ├── base.py             # Transformer ABC + registry
│   │   ├── ablation.py         # ablation axis
│   │   ├── format.py           # format axis
│   │   └── expand.py           # battery expansion (case × perturbation × sut × sample)
│   ├── sut/
│   │   ├── __init__.py
│   │   ├── base.py             # SUTAdapter ABC, GenerationResult, TokenUsage
│   │   ├── fake.py             # deterministic fake model
│   │   ├── openai_compat.py    # real OpenAI-compatible httpx adapter
│   │   └── registry.py         # build adapter from SUT binding
│   ├── judge/
│   │   ├── __init__.py
│   │   ├── base.py             # Judge ABC
│   │   ├── fake.py             # deterministic fake judge
│   │   └── grading.py          # grade a generation against rubric items
│   ├── store/
│   │   ├── __init__.py
│   │   └── runstore.py         # SQLite metadata + parquet generations/grades
│   ├── stats/
│   │   ├── __init__.py
│   │   ├── bootstrap.py        # bootstrap CIs
│   │   └── analyze.py          # info-value curves, omission/hallucination rates
│   ├── artifacts/
│   │   ├── __init__.py
│   │   ├── contract.py         # InputContract extraction
│   │   └── report.py           # ValidationReport (structured JSON)
│   ├── execute.py              # orchestration: expand → generate → grade → store
│   └── cli.py                  # `harness run <pack> ...`
├── packs/
│   └── hello-tumor-board/      # synthetic demo pack (CONTENT, not engine)
│       ├── manifest.yaml
│       ├── casebank/{schema.yaml, cases/*.json}
│       ├── rubric/{rubric.yaml, adjudication/*.json}
│       ├── perturbations.yaml
│       ├── battery.yaml
│       ├── judge.yaml
│       └── acceptance.yaml
└── tests/
    ├── conftest.py
    ├── test_hashing.py
    ├── test_pack_loader.py
    ├── test_results_models.py
    ├── test_perturb_ablation.py
    ├── test_perturb_format.py
    ├── test_expand.py
    ├── test_sut_fake.py
    ├── test_sut_openai_compat.py
    ├── test_judge.py
    ├── test_runstore.py
    ├── test_stats.py
    ├── test_artifacts.py
    ├── test_no_usecase_leak.py     # grep engine for use-case strings
    └── test_end_to_end.py          # + determinism (run twice, compare content)
```

---

### Task 1: Repo scaffold, deps, license, git

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `README.md`, `.gitignore`, `harness/__init__.py`, `harness/version.py`

**Interfaces:**
- Produces: package `harness` importable; `harness.version.ENGINE_VERSION: str`.

- [ ] Step 1: Create `pyproject.toml` (pydantic>=2.6, pyarrow>=15, httpx>=0.27, numpy>=1.26, PyYAML>=6, pytest as dev), pytest config pointing at `tests/`.
- [ ] Step 2: Create AGPL-3.0 `LICENSE`, `.gitignore` (`.venv`, `__pycache__`, `*.pyc`, `runs/`, `*.parquet`, `*.sqlite`), `README.md` stub.
- [ ] Step 3: Create `harness/__init__.py` and `harness/version.py` with `ENGINE_VERSION = "0.1.0"`.
- [ ] Step 4: `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`; verify `import pyarrow, pydantic, httpx, numpy, yaml`.
- [ ] Step 5: `git init`, add SPDX headers, commit `chore: scaffold harness factory engine (M1)`.

---

### Task 2: Canonical hashing + env hash

**Files:**
- Create: `harness/hashing.py`, `harness/envhash.py`, `tests/test_hashing.py`

**Interfaces:**
- Produces: `canonical_json(obj) -> bytes` (sorted keys, no whitespace, UTF-8); `content_hash(obj) -> str` (sha256 hex of canonical_json); `env_hash() -> str` (sha256 of python version + engine version + sorted installed dep versions).

- [ ] Step 1: Write `tests/test_hashing.py`: `content_hash({"a":1,"b":2}) == content_hash({"b":2,"a":1})`; hash is stable string of len 64; changing a value changes the hash.
- [ ] Step 2: Run — expect FAIL (module missing).
- [ ] Step 3: Implement `canonical_json` (`json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()`) and `content_hash`; implement `env_hash` in `envhash.py`.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: canonical hashing and environment hash`.

---

### Task 3: Result records — the versioning spine

**Files:**
- Create: `harness/models/__init__.py`, `harness/models/results.py`, `tests/test_results_models.py`

**Interfaces:**
- Produces (pydantic v2 models, all `frozen=True`):
  - `TokenUsage(prompt_tokens:int, completion_tokens:int, total_tokens:int, cost_chf:float=0.0)` with `__add__`.
  - `Pins(pack_id:str, pack_version:str, pack_hash:str, battery_id:str, battery_version:str, sut_id:str, sut_hash:str, judge_id:str|None, judge_version:str|None, seed:int, engine_version:str)`.
  - `RunMeta(run_id:str, timestamp:str, env_hash:str)` — the ISOLATED run-metadata (excluded from content comparisons).
  - `Generation(case_id:str, perturbation_id:str, sample_idx:int, raw_output:str, trace:dict, usage:TokenUsage)` — content only.
  - `Grade(case_id:str, perturbation_id:str, sample_idx:int, item_scores:dict[str,float], judge_notes:dict[str,str], human_agreement:dict[str,bool]|None=None)` — content only.
  - `Run(pins:Pins, meta:RunMeta)`; helper `run_id_for(pins) -> str` = `content_hash(pins)[:16]`.
  - `content_key(gen_or_grade) -> tuple` = `(case_id, perturbation_id, sample_idx)`.

- [ ] Step 1: Write `tests/test_results_models.py`: models are frozen (mutation raises); `TokenUsage(1,2,3)+TokenUsage(1,1,2)==TokenUsage(2,3,5)`; `run_id_for(pins)` deterministic and independent of any timestamp; `Generation` has no timestamp field.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement models in `results.py` (`model_config = ConfigDict(frozen=True)`).
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: immutable version-pinned result records`.

---

### Task 4: Pack schema models

**Files:**
- Create: `harness/models/pack.py`, `tests/` (covered in Task 5)

**Interfaces:**
- Produces (pydantic v2):
  - `ElementSpec(name:str, type:str, modality:str, language:str, source_system:str|None=None, required:bool=True)`.
  - `CaseSchema(elements:list[ElementSpec])`.
  - `Case(case_id:str, elements:dict[str,Any], ground_truth:dict[str,Any])`.
  - `RubricItem(id:str, statement:str, type:Literal["binary","graded"], critical:bool=False, grading_instructions:str, evidence_required:bool=False, max_score:float=1.0)`.
  - `Rubric(items:list[RubricItem])`.
  - `PerturbationSpec(axes:dict[str,list[dict]])` — axis name → list of level configs.
  - `BatterySpec(id:str, version:str, cases:list[str]|Literal["all"], perturbations:list[str]|Literal["all"], suts:list[str], n_samples:int)`.
  - `SUTSpec` (see Task 8; imported).
  - `JudgeSpec(id:str, version:str, kind:str, binding:dict, calibration_fraction:float=0.1)`.
  - `AcceptanceSpec(thresholds:dict[str,float])`.
  - `Manifest(id:str, version:str, intended_use:str, device_status_rationale:str, population:str, languages:list[str])`.
  - `Pack(manifest, case_schema, cases:list[Case], rubric, perturbations, batteries:list[BatterySpec], suts:list[SUTSpec], judge:JudgeSpec, acceptance:AcceptanceSpec, pack_hash:str)`.

- [ ] Step 1: (test written in Task 5).
- [ ] Step 2: Implement all models in `pack.py`.
- [ ] Step 3: Commit `feat: declarative pack schema models`.

---

### Task 5: Pack loader (load + validate + content-hash)

**Files:**
- Create: `harness/packio/__init__.py`, `harness/packio/loader.py`, `tests/test_pack_loader.py`
- Also create the demo pack files here (needed as loader fixture): `packs/hello-tumor-board/**`

**Interfaces:**
- Consumes: `harness.models.pack.*`, `harness.hashing.content_hash`.
- Produces: `load_pack(path:str|Path) -> Pack`. Raises `PackValidationError` on schema violation. `pack_hash` = `content_hash` of the full canonicalized pack content (manifest+schema+cases+rubric+perturbations+batteries+suts+judge+acceptance), stable across load order.

- [ ] Step 1: Author the `hello-tumor-board` pack files (synthetic, PHI-free): `manifest.yaml`; `casebank/schema.yaml` with elements `pathology_report`, `molecular_report`, `imaging_text`, `prior_notes`, `meds`; 3 `cases/*.json` with pseudonymized synthetic content + `ground_truth`; `rubric/rubric.yaml` (≥3 items incl. one `critical`); `rubric/adjudication/*.json`; `perturbations.yaml` (ablation + format axes); `battery.yaml`; `judge.yaml` (kind: fake); `acceptance.yaml`.
- [ ] Step 2: Write `tests/test_pack_loader.py`: loads demo pack; asserts 3 cases, ≥3 rubric items, one critical; `load_pack` twice yields identical `pack_hash`; malformed pack raises `PackValidationError`.
- [ ] Step 3: Run — expect FAIL.
- [ ] Step 4: Implement `loader.py` (read YAML/JSON, validate via pydantic, compute pack_hash).
- [ ] Step 5: Run — expect PASS.
- [ ] Step 6: Commit `feat: pack loader + hello-tumor-board demo pack`.

---

### Task 6: Perturbation base + registry + ablation axis

**Files:**
- Create: `harness/perturb/__init__.py`, `harness/perturb/base.py`, `harness/perturb/ablation.py`, `tests/test_perturb_ablation.py`

**Interfaces:**
- Consumes: `Case`, `CaseSchema`, `ElementSpec`.
- Produces:
  - `PerturbedCase(perturbation_id:str, case:Case, provenance:dict)` — a transformed case + how it was made.
  - `Transformer(ABC)`: `axis_name:str`; `expand(case, schema, level_cfg) -> list[PerturbedCase]`.
  - `REGISTRY: dict[str,Transformer]`; `register(transformer)`; `get_transformer(axis) -> Transformer`.
  - `AblationTransformer`: drops declared elements per `level_cfg` (`{"drop":[names]}` or `{"powerset":true,"budget":N}` with deterministic sampling by index — no RNG that breaks replay; use sorted combinations capped at budget). perturbation_id includes axis + sorted dropped names.

- [ ] Step 1: Write `tests/test_perturb_ablation.py`: dropping `["molecular_report"]` yields a case whose elements lack that key; perturbation_id is deterministic; powerset with budget=3 yields exactly 3 deterministic subsets; identity level (drop nothing) yields the original.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement `base.py` + `ablation.py`; register ablation.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: perturbation base, registry, ablation axis`.

---

### Task 7: Format axis

**Files:**
- Create: `harness/perturb/format.py`, `tests/test_perturb_format.py`

**Interfaces:**
- Consumes: `Transformer`, `PerturbedCase`.
- Produces: `FormatTransformer` axis `format`; renders the case's elements into a single prompt-ready `document` string per level: `raw_dump` (concatenated raw text), `structured` (labeled sections `## <name>\n<value>`), `tabular` (key/value table). Stores rendered doc in `case.elements["__document__"]`; perturbation_id includes axis + level name. Deterministic (sorted element order by schema declaration order).

- [ ] Step 1: Write `tests/test_perturb_format.py`: each level produces a distinct deterministic `__document__`; `structured` contains `## pathology_report`; element order follows schema declaration; running twice is identical.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement `format.py`; register.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: format perturbation axis`.

---

### Task 8: SUT models + base adapter + fake model

**Files:**
- Create: `harness/models/sut.py`, `harness/sut/__init__.py`, `harness/sut/base.py`, `harness/sut/fake.py`, `harness/sut/registry.py`, `tests/test_sut_fake.py`

**Interfaces:**
- Produces:
  - `models/sut.py`: `Step(name:str, content:str, data:dict={})`, `Trace(steps:list[Step], final_output:str)`, `SUTBinding(model_id:str, model_version:str, endpoint:str|None, params:dict, system_prompt:str|None)`, `SUTSpec(id:str, kind:Literal["llm_call","chain","agent","external_api"], binding:SUTBinding, tools:list=[], sut_hash:str="")` with `sut_hash` computed via `content_hash` over binding+kind+id.
  - `sut/base.py`: `GenerationOutput(raw_output:str, trace:Trace, usage:TokenUsage)`; `SUTAdapter(ABC)`: `generate(document:str, seed:int) -> GenerationOutput`.
  - `sut/fake.py`: `FakeModel(SUTAdapter)` — pure function: output derived deterministically from `content_hash((document, system_prompt, seed))`; emits a rubric-friendly output (e.g. echoes which known keywords/sections it "found"); token usage = deterministic function of lengths.
  - `sut/registry.py`: `build_adapter(sut_spec:SUTSpec) -> SUTAdapter` (fake for `kind=="llm_call"` binding with `model_id=="fake"`, else openai_compat).

- [ ] Step 1: Write `tests/test_sut_fake.py`: `FakeModel.generate(doc, seed=7)` twice → identical output+usage; different doc → different output; usage totals are consistent (`total==prompt+completion`).
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement models + base + fake + registry.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: SUT models, adapter base, deterministic fake model`.

---

### Task 9: Real OpenAI-compatible adapter (mocked transport)

**Files:**
- Create: `harness/sut/openai_compat.py`, `tests/test_sut_openai_compat.py`

**Interfaces:**
- Consumes: `SUTAdapter`, `SUTBinding`, `httpx`.
- Produces: `OpenAICompatModel(SUTAdapter)` — builds a `/chat/completions` request from binding (model, system_prompt, params), posts via an injectable `httpx.Client` (default real), maps response → `GenerationOutput` incl. usage. Accepts `transport` for testing. Live calls are flagged (`reproducible=False` attribute) but NOT made in tests.

- [ ] Step 1: Write `tests/test_sut_openai_compat.py`: using `httpx.MockTransport` returning a canned chat-completions JSON, `generate()` returns the assistant content and maps `usage` fields correctly; request body contains system prompt + document as user message.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement `openai_compat.py`.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: OpenAI-compatible SUT adapter (mock-tested)`.

---

### Task 10: Battery expansion

**Files:**
- Create: `harness/perturb/expand.py`, `tests/test_expand.py`

**Interfaces:**
- Consumes: `Pack`, `BatterySpec`, transformer `REGISTRY`, `PerturbedCase`.
- Produces: `expand_battery(pack, battery) -> list[ExpansionUnit]` where `ExpansionUnit(case_id, perturbation_id, sample_idx, sut_id, document, provenance)`. Applies each configured axis level to each selected case (cartesian across axes is out-of-scope for M1 — apply axes independently: identity + each single-axis level), dedups by perturbation_id, multiplies by n_samples and suts. Deterministic ordering (sorted).

- [ ] Step 1: Write `tests/test_expand.py`: demo battery expands to the expected deterministic count (cases × (1 identity + ablation levels + format levels) × suts × n_samples); no duplicate (case_id, perturbation_id, sample_idx, sut_id); every unit has a non-empty `document`.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement `expand.py`.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: battery expansion`.

---

### Task 11: Judge (fake) + grading

**Files:**
- Create: `harness/judge/__init__.py`, `harness/judge/base.py`, `harness/judge/fake.py`, `harness/judge/grading.py`, `tests/test_judge.py`

**Interfaces:**
- Consumes: `RubricItem`, `Generation`, `Grade`.
- Produces:
  - `judge/base.py`: `Judge(ABC)`: `grade_item(item:RubricItem, document:str, output:str, ground_truth:dict, seed:int) -> tuple[float, str]` (score, note).
  - `judge/fake.py`: `FakeJudge(Judge)` — deterministic: score derived from whether the output contains the ground-truth evidence for that item (keyword/section match against `ground_truth[item.id]`), pure function of inputs+seed.
  - `judge/grading.py`: `grade_generation(rubric, generation, case, judge, seed) -> Grade` iterating items; `build_judge(judge_spec) -> Judge`.

- [ ] Step 1: Write `tests/test_judge.py`: `FakeJudge` deterministic across two calls; an output containing the ground-truth evidence scores higher than one without; `grade_generation` returns a `Grade` with a score for every rubric item.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement base + fake + grading.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: fake judge and rubric grading`.

---

### Task 12: Run store (SQLite + parquet, append-only)

**Files:**
- Create: `harness/store/__init__.py`, `harness/store/runstore.py`, `tests/test_runstore.py`

**Interfaces:**
- Consumes: `Run`, `Generation`, `Grade`, `pyarrow`.
- Produces: `RunStore(root:Path)`:
  - `write_run(run:Run) -> None` (SQLite `runs` table: run_id, pins JSON, timestamp, env_hash; refuses to overwrite an existing run_id → append-only).
  - `write_generations(run_id, list[Generation]) -> None` (parquet at `root/runs/<run_id>/generations.parquet`).
  - `write_grades(run_id, list[Grade]) -> None` (parquet `.../grades.parquet`).
  - `read_run(run_id) -> Run`; `read_generations(run_id) -> list[Generation]`; `read_grades(run_id) -> list[Grade]`; `list_runs() -> list[str]`.

- [ ] Step 1: Write `tests/test_runstore.py`: write then read round-trips a Run/Generations/Grades identically (content equality); writing the same run_id twice raises; parquet files exist on disk.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement `runstore.py` (json-encode nested fields into parquet columns; decode on read).
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: append-only SQLite+parquet run store`.

---

### Task 13: Stats — bootstrap CIs + analysis

**Files:**
- Create: `harness/stats/__init__.py`, `harness/stats/bootstrap.py`, `harness/stats/analyze.py`, `tests/test_stats.py`

**Interfaces:**
- Consumes: `Grade`, `RubricItem`, `numpy`; grades tagged with their perturbation provenance (which elements were ablated).
- Produces:
  - `bootstrap.py`: `bootstrap_ci(values:list[float], n_boot:int=1000, seed:int=0, ci:float=0.95) -> tuple[float,float,float]` (mean, lo, hi) using a seeded numpy RNG (deterministic).
  - `analyze.py`:
    - `information_value(grades_by_perturbation, baseline_perturbation_id) -> dict[element_name, score_delta]` (mean score drop when element ablated vs baseline).
    - `critical_rates(grades, rubric) -> dict` critical-omission rate + hallucination proxy (critical items scored 0) with bootstrap CI.

- [ ] Step 1: Write `tests/test_stats.py`: `bootstrap_ci` deterministic with fixed seed and lo≤mean≤hi; `information_value` reports a positive delta for an element whose ablation lowers scores; `critical_rates` returns rate in [0,1] with CI bounds.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement bootstrap + analyze.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: bootstrap CIs and analysis stats`.

---

### Task 14: Artifacts — InputContract + ValidationReport

**Files:**
- Create: `harness/artifacts/__init__.py`, `harness/artifacts/contract.py`, `harness/artifacts/report.py`, `tests/test_artifacts.py`

**Interfaces:**
- Consumes: analysis outputs, `Pins`, `Rubric`, `AcceptanceSpec`.
- Produces:
  - `contract.py`: `extract_contract(pins, info_value, critical, schema) -> dict` (JSON-serializable: per-element information value, ranked minimal-sufficient-set candidate = elements above a delta threshold, pins). Designed for later aggregation (no PHI, aggregate stats only).
  - `report.py`: `build_validation_report(pins, run_meta, grades, stats, acceptance) -> dict` (pass/fail per acceptance threshold, summary scores, agreement placeholder, pinned inputs + hashes). `render_report_json(report, path)`.

- [ ] Step 1: Write `tests/test_artifacts.py`: contract JSON is serializable, contains per-element info value + pins, contains no PHI element *values* (only names + stats); validation report flags pass/fail vs acceptance thresholds and includes all pins.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement contract + report.
- [ ] Step 4: Run — expect PASS.
- [ ] Step 5: Commit `feat: InputContract + ValidationReport artifacts`.

---

### Task 15: Orchestration + CLI

**Files:**
- Create: `harness/execute.py`, `harness/cli.py`, `tests/` (end-to-end in Task 16)

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `execute.py`: `run_battery(pack, battery_id, store, seed) -> str` (returns run_id): expand → for each unit call adapter.generate (record generations with usage) → grade each generation (fake judge) → accumulate cost → write Run+Generations+Grades → returns run_id. Separates content (generations/grades) from RunMeta (timestamp via injected clock, env_hash). Timestamp is injected (`now:callable`) so tests can pin it; cost meter aggregated and logged.
  - `cli.py`: `main(argv)` supporting `harness run <pack_dir> --battery <id> --out <runs_dir> [--seed N]`; prints run_id, unit count, total tokens/CHF, and writes artifacts (contract + report) to the run dir.

- [ ] Step 1: Implement `execute.py` with injectable clock + seed.
- [ ] Step 2: Implement `cli.py` (argparse); register console entry point in pyproject (`harness = "harness.cli:main"`).
- [ ] Step 3: Manual smoke: `.venv/bin/harness run packs/hello-tumor-board --battery <id> --out ./runs --seed 1` prints a run_id + cost.
- [ ] Step 4: Commit `feat: battery execution orchestration + CLI`.

---

### Task 16: End-to-end + determinism + no-leak tests

**Files:**
- Create: `tests/test_no_usecase_leak.py`, `tests/test_end_to_end.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `run_battery`, `RunStore`, demo pack.

- [ ] Step 1: Write `tests/test_no_usecase_leak.py`: walk `harness/` source, assert no occurrence of `tumor`, `pathology_report`, `molecular_report`, `imaging_text` (case-insensitive) in engine code.
- [ ] Step 2: Write `tests/test_end_to_end.py`:
  - (a) Run the demo battery once with fake model+judge, fixed seed, pinned clock → produces a run_id, generations, grades, contract, report; report has a pass/fail verdict.
  - (b) **Determinism:** run twice (fresh stores, same seed) → `run_id` identical; generations and grades content byte-identical after excluding RunMeta (timestamp/env_hash); contract identical.
- [ ] Step 3: Run full suite `.venv/bin/pytest -q` — expect PASS (fix any leaks/nondeterminism found).
- [ ] Step 4: Commit `test: end-to-end, determinism, and zero-use-case-leak gates`.

---

## Self-Review

**Spec coverage (M1 exit = demo pack end-to-end):**
- Pack loader → Tasks 4,5 · Casebank → Task 5 (schema + cases) · LLM-call SUT adapter → Tasks 8,9 · ablation+format axes → Tasks 6,7 · judge grading → Task 11 · run store → Task 12 · basic stats → Task 13 · demo pack end-to-end → Tasks 5,16.
- Design goal #3 (deterministic replay + versioning) → Tasks 2,3,16. Goal #1 (zero engine code per pack) → Task 16 leak test. Goal #4 (on-prem/no external calls) → fake model default, no live calls in tests. Cost visibility → Tasks 8,15.
- Explicitly deferred (scope fence): order/noise/language/length axes, agent SUT, RegressionDiff, monitoring, UI, PDF/OCR, QMS templating — none in M1.

**Type consistency:** `TokenUsage`, `GenerationOutput`, `Trace`, `Step`, `SUTSpec`, `SUTBinding`, `Pins`, `Generation`, `Grade`, `PerturbedCase`, `ExpansionUnit` names are used identically across tasks. Adapter interface `generate(document, seed) -> GenerationOutput` consistent (Tasks 8,9,15). Judge interface `grade_item(...) -> (float,str)` consistent (Tasks 11,15).

**Placeholders:** none — each task has concrete signatures, test intent, and commit message.
