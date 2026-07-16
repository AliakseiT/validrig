# Harness Factory — M1 Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** M1 engine core per the Harness Factory design doc: pack loader, casebank, LLM-call SUT adapter, ablation+format perturbation axes, judge grading, run store, basic stats — demonstrated end-to-end on a synthetic `demo-tumor-board` pack with zero network calls.

**Architecture:** A Python package `harness_factory` where all use-case content lives in declarative YAML/JSON "packs" (pydantic-validated), and the engine is a pipeline: `pack load → battery expand → execute (SUT adapters) → grade (judge) → analyze → report`. Results are immutable files (SQLite index + parquet tables) under `runs/<run_id>/`. Everything is deterministic and pinned: pack content hash, SUT snapshot, battery version, judge version, seed.

**Tech Stack:** Python 3.12, pydantic v2, PyYAML, httpx (async), pyarrow (parquet), numpy (bootstrap), stdlib argparse CLI (`hf`), pytest. License AGPL-3.0-or-later.

## Global Constraints

- Python `>=3.12`; interpreter at `/opt/homebrew/bin/python3.12`; venv at `factory/.venv`.
- Runtime deps ONLY: `pydantic>=2`, `pyyaml`, `httpx`, `pyarrow`, `numpy`. Dev deps: `pytest`, `pytest-asyncio`. No pandas, no click, no server DB.
- Every `.py` file starts with the two-line AGPL header comment (defined in Task 1).
- Engine code contains **zero** use-case logic — anything tumor-board-specific lives only under `packs/demo-tumor-board/`.
- Results are append-only/immutable: the engine never mutates or deletes files inside an existing `runs/<run_id>/`.
- All randomness flows from explicit seeds (battery `seed`); no wall-clock in any computed artifact except run timestamps recorded in `run.json`.
- Package layout: `src/harness_factory/`; CLI entrypoint `hf = harness_factory.cli:main`.
- Commit after every task (conventional commits: `feat:`, `test:`, `chore:`).

---

## File Structure (target)

```
factory/
├── LICENSE                          # AGPL-3.0 full text
├── README.md
├── pyproject.toml
├── docs/superpowers/plans/…
├── src/harness_factory/
│   ├── __init__.py                  # __version__
│   ├── ids.py                       # hashing + id helpers
│   ├── schemas/
│   │   ├── __init__.py              # re-exports
│   │   ├── manifest.py              # PackManifest
│   │   ├── casebank.py              # CasebankSchema, ElementSpec, Case
│   │   ├── rubric.py                # Rubric, RubricItem, Adjudication
│   │   ├── perturbations.py         # PerturbationConfig (axes)
│   │   ├── battery.py               # Battery
│   │   ├── judge.py                 # JudgeConfig
│   │   ├── acceptance.py            # AcceptanceCriteria
│   │   └── sut.py                   # SUTSpec (engine-side, not pack content)
│   ├── pack.py                      # IntendedUsePack loader + content hash
│   ├── render.py                    # format renderers (raw_dump / structured / tabular)
│   ├── perturb.py                   # axes registry, Perturbation, grid expansion, apply
│   ├── sut/
│   │   ├── __init__.py              # SUTAdapter protocol, build_sut() factory, SUTResult
│   │   ├── mock.py                  # deterministic scripted adapter
│   │   └── llm_call.py              # OpenAI-compatible chat completions adapter
│   ├── battery.py                   # expand(battery, pack, suts) -> ExecutionPlan (WorkItems)
│   ├── execute.py                   # async executor -> Generation records
│   ├── judge.py                     # grade generations vs rubric -> Grade records
│   ├── store.py                     # RunStore: runs/<id>/{run.json, generations.parquet, grades.parquet} + SQLite index
│   ├── stats.py                     # scores, info-value curves, critical rates, bootstrap CI, acceptance check
│   └── cli.py                       # hf validate-pack | run | report
├── packs/demo-tumor-board/         # synthetic fixture pack (also documentation)
│   ├── manifest.yaml
│   ├── casebank/schema.yaml
│   ├── casebank/cases/*.json        # 4 synthetic cases
│   ├── rubric/rubric.yaml
│   ├── rubric/adjudication/*.json
│   ├── perturbations.yaml
│   ├── battery.yaml
│   ├── judge.yaml
│   └── acceptance.yaml
├── suts/                            # engine-side SUT specs used by demo/tests
│   ├── mock-tumor-board.yaml
│   └── example-openai-compatible.yaml
└── tests/
    ├── conftest.py                  # demo pack path fixture, tmp store fixture
    ├── test_schemas.py
    ├── test_pack_loader.py
    ├── test_render.py
    ├── test_perturb.py
    ├── test_sut_mock.py
    ├── test_sut_llm_call.py
    ├── test_battery_expand.py
    ├── test_execute.py
    ├── test_store.py
    ├── test_judge.py
    ├── test_stats.py
    └── test_e2e.py                  # full pipeline on demo-tumor-board, golden assertions
```

## Core interfaces (single source of truth for all tasks)

```python
# schemas/casebank.py
ElementType = Literal["text", "text_list", "keyvalue", "table"]
class ElementSpec(BaseModel):
    type: ElementType
    label: str                      # human heading used by renderers
    modality: str = "note"          # free taxonomy: report|note|list|structured
    language: str = "en"
    source_system: str | None = None
    required: bool = False          # required elements are never ablated
class CasebankSchema(BaseModel):
    elements: dict[str, ElementSpec]   # element name -> spec
class Case(BaseModel):
    id: str
    elements: dict[str, Any]        # values typed per ElementSpec.type
    ground_truth: dict[str, Any]    # opaque to engine; judge prompts may reference it
    metadata: dict[str, Any] = {}

# schemas/rubric.py
class RubricItem(BaseModel):
    id: str
    statement: str
    type: Literal["binary", "graded"]     # graded = 0..4 integer
    critical: bool = False
    grading_instructions: str
    requires_evidence_pointer: bool = False
class Rubric(BaseModel):
    items: list[RubricItem]

# schemas/perturbations.py
class AblationAxis(BaseModel):
    mode: Literal["none", "single", "powerset"] = "single"
    elements: list[str] | None = None   # None = all non-required elements
    include_baseline: bool = True
    budget: int = 16                     # cap on powerset variants (sampled with battery seed)
class FormatAxis(BaseModel):
    levels: list[Literal["structured", "raw_dump", "tabular"]] = ["structured"]
class PerturbationConfig(BaseModel):
    ablation: AblationAxis = AblationAxis(mode="none")
    format: FormatAxis = FormatAxis()

# perturb.py
@dataclass(frozen=True)
class Perturbation:
    id: str                # e.g. "ablation=drop:pathology_report|format=raw_dump"
    dropped: tuple[str, ...]
    format: str
def expand_grid(cfg: PerturbationConfig, schema: CasebankSchema, seed: int) -> list[Perturbation]
def apply(p: Perturbation, case: Case) -> Case            # returns copy without dropped elements

# render.py
def render_case(case: Case, schema: CasebankSchema, fmt: str) -> str

# schemas/sut.py  (engine-side spec files in suts/*.yaml)
class SUTSpec(BaseModel):
    id: str
    version: str
    kind: Literal["llm_call", "mock"]
    binding: dict[str, Any]   # llm_call: endpoint, model, params{}, system_prompt,
                              #   api_key_env, price_per_1k_input, price_per_1k_output
                              # mock: rules (see sut/mock.py)

# sut/__init__.py
class SUTResult(BaseModel):
    output_text: str
    steps: list[dict[str, Any]] = []       # trace protocol placeholder (M4)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_chf: float = 0.0
class SUTAdapter(Protocol):
    spec: SUTSpec
    async def generate(self, rendered_input: str, seed: int) -> SUTResult
def build_sut(spec: SUTSpec) -> SUTAdapter

# battery.py
class WorkItem(BaseModel):
    case_id: str; perturbation_id: str; sut_id: str; sample_idx: int
    rendered_input: str; input_hash: str
class ExecutionPlan(BaseModel):
    battery_id: str; battery_version: str; seed: int
    items: list[WorkItem]
    dedup_note: str   # human-readable count of removed duplicate rendered inputs
def expand(battery: Battery, pack: IntendedUsePack, suts: dict[str, SUTSpec]) -> ExecutionPlan

# execute.py
class Generation(BaseModel):
    run_id: str; case_id: str; perturbation_id: str; sut_id: str; sample_idx: int
    rendered_input: str; output_text: str; steps_json: str
    input_tokens: int; output_tokens: int; cost_chf: float
    latency_ms: float; error: str | None = None
async def execute_plan(plan, suts, run_id, concurrency=4) -> list[Generation]

# judge.py
class Grade(BaseModel):
    run_id: str; case_id: str; perturbation_id: str; sut_id: str; sample_idx: int
    rubric_item_id: str
    value: float          # binary: 0/1; graded: 0..4
    passed: bool          # binary: value==1; graded: value >= pass_threshold (judge.yaml)
    rationale: str
    judge_id: str; judge_version: str
async def grade_generations(gens, pack, judge_sut) -> list[Grade]

# store.py
class RunStore:
    def __init__(self, root: Path)                       # root = runs dir
    def create_run(self, snapshot: dict) -> str          # writes run.json, returns run_id
    def write_generations(self, run_id, gens: list[Generation]) -> None   # parquet, write-once
    def write_grades(self, run_id, grades: list[Grade]) -> None
    def read_generations(self, run_id) -> list[Generation]
    def read_grades(self, run_id) -> list[Grade]
    def get_run(self, run_id) -> dict
    def list_runs(self) -> list[dict]

# stats.py
def analyze(gens, grades, pack) -> dict   # JSON-safe analysis artifact (schema in Task 12)
def check_acceptance(analysis: dict, acceptance: AcceptanceCriteria) -> dict
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `README.md`, `.gitignore`, `src/harness_factory/__init__.py`, `tests/test_smoke.py`

**Interfaces:** Produces importable package `harness_factory` with `__version__ = "0.1.0"` and the AGPL header convention.

AGPL header (every .py file, first two lines):
```python
# Harness Factory — hospital-side LLM evaluation engine
# SPDX-License-Identifier: AGPL-3.0-or-later
```

- [ ] Step 1: `git init`, write `.gitignore` (`.venv/`, `__pycache__/`, `*.pyc`, `runs/`, `.pytest_cache/`, `.DS_Store`)
- [ ] Step 2: `pyproject.toml` with `[project] name="harness-factory" version="0.1.0" requires-python=">=3.12"`, deps per Global Constraints, `[project.scripts] hf = "harness_factory.cli:main"`, setuptools src-layout, `[tool.pytest.ini_options] asyncio_mode = "auto"`.
- [ ] Step 3: Download/write AGPL-3.0 full text to `LICENSE`; minimal `README.md` (what it is, quickstart placeholder filled in Task 13).
- [ ] Step 4: `python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- [ ] Step 5: `tests/test_smoke.py`: `import harness_factory; assert harness_factory.__version__` → run pytest → PASS.
- [ ] Step 6: Commit `chore: scaffold harness-factory package (AGPL, src layout)`

### Task 2: Pack content schemas

**Files:**
- Create: `src/harness_factory/schemas/{__init__,manifest,casebank,rubric,perturbations,battery,judge,acceptance,sut}.py`
- Test: `tests/test_schemas.py`

**Interfaces:** Produces all pydantic models from the Core interfaces block plus:

```python
# manifest.py
class PackManifest(BaseModel):
    id: str; version: str
    intended_use: str                  # QMS wording
    device_status_rationale: str = ""
    population: str = ""
    languages: list[str] = ["en"]

# battery.py (schema)
class Battery(BaseModel):
    id: str; version: str
    cases: list[str] | Literal["all"] = "all"
    suts: list[str]                    # SUT ids resolved from suts dir at run time
    n_samples: int = 1
    seed: int = 42

# judge.py (schema)
class JudgeConfig(BaseModel):
    sut: str                            # SUT id of the judge model
    version: str
    graded_pass_threshold: int = 3      # graded item passes if value >= this
    prompts: dict[str, str]             # keys "binary","graded"; templates with
                                        # {statement} {grading_instructions} {ground_truth} {output}
    calibration_fraction: float = 0.1   # recorded in snapshot; human UI is M2

# acceptance.py
class Threshold(BaseModel):
    metric: str                         # e.g. "critical_failure_rate"
    op: Literal["<=", ">="]
    value: float
class AcceptanceCriteria(BaseModel):
    thresholds: list[Threshold]
```

All models use `model_config = ConfigDict(extra="forbid")` (catch typos in hospital-authored YAML — this is the product's error surface).

- [ ] Step 1: Write `tests/test_schemas.py` — key tests:

```python
def test_case_roundtrip():
    c = Case(id="c1", elements={"pathology_report": "ER+"}, ground_truth={"er": "positive"})
    assert Case.model_validate(c.model_dump()) == c

def test_rubric_rejects_unknown_field():
    with pytest.raises(ValidationError):
        RubricItem(id="r1", statement="s", type="binary", grading_instructions="g", typo_field=1)

def test_graded_item_type_literal():
    with pytest.raises(ValidationError):
        RubricItem(id="r1", statement="s", type="percentage", grading_instructions="g")

def test_ablation_axis_defaults():
    cfg = PerturbationConfig()
    assert cfg.ablation.mode == "none" and cfg.format.levels == ["structured"]
```
- [ ] Step 2: Run pytest → FAIL (modules missing).
- [ ] Step 3: Implement all schema modules; `schemas/__init__.py` re-exports everything.
- [ ] Step 4: pytest → PASS. Commit `feat: pack content schemas (pydantic v2, extra=forbid)`

### Task 3: Pack loader + content hash

**Files:**
- Create: `src/harness_factory/pack.py`, `src/harness_factory/ids.py`
- Test: `tests/test_pack_loader.py`

**Interfaces:**
```python
# ids.py
def sha256_file(path: Path) -> str
def content_hash(paths: list[Path]) -> str      # sha256 over sorted (relpath, filehash) pairs
def new_run_id(now: datetime) -> str            # "run-YYYYMMDD-HHMMSS-<6 hex of uuid4>"

# pack.py
class PackValidationError(Exception): ...       # carries list[str] of problems
class IntendedUsePack(BaseModel):
    root: Path; manifest: PackManifest; casebank_schema: CasebankSchema
    cases: list[Case]; rubric: Rubric; perturbations: PerturbationConfig
    battery: Battery; judge: JudgeConfig; acceptance: AcceptanceCriteria
    content_hash: str
    def case(self, case_id: str) -> Case
def load_pack(root: Path) -> IntendedUsePack    # raises PackValidationError with ALL problems
```

Cross-validation rules (each produces a listed problem, not an early raise): every case element name exists in schema; every schema-`required` element present in every case; element value type matches ElementSpec.type (text→str, text_list→list[str], keyvalue→dict, table→list[dict]); rubric item ids unique; battery case ids exist (when not "all"); ablation axis `elements` exist in schema and are not `required`.

- [ ] Step 1: Tests — build a minimal valid pack in `tmp_path` via a `make_pack(tmp_path, **overrides)` helper inside the test file; cases:
```python
def test_load_valid_pack(tmp_path): ...            # loads, content_hash is 64-hex
def test_unknown_element_in_case_reported(tmp_path): ...
def test_missing_required_element_reported(tmp_path): ...
def test_wrong_element_value_type_reported(tmp_path): ...
def test_duplicate_rubric_ids_reported(tmp_path): ...
def test_battery_unknown_case_reported(tmp_path): ...
def test_all_problems_collected_in_one_error(tmp_path): ...   # two seeded errors -> both listed
def test_content_hash_changes_when_case_edited(tmp_path): ...
```
- [ ] Step 2: pytest → FAIL. Step 3: implement. Step 4: PASS. Step 5: Commit `feat: pack loader with cross-validation and content hash`

### Task 4: demo-tumor-board demo pack

**Files:**
- Create: everything under `packs/demo-tumor-board/` and `suts/mock-tumor-board.yaml`
- Test: `tests/conftest.py` (fixture `demo_pack` returning loaded pack), extend `tests/test_pack_loader.py` with `test_demo_pack_loads()`

**Content (synthetic, English + one German element to exercise metadata):**
- Elements: `pathology_report` (text, required), `molecular_report` (text), `imaging_text` (text), `prior_notes` (text_list), `meds` (keyvalue).
- 4 cases (`case-001..004`), e.g. case-001: ER+/HER2− early breast ca; ground_truth: `{"receptor_status": "ER-positive, HER2-negative", "recommended_option": "adjuvant endocrine therapy", "forbidden_claims": ["trastuz