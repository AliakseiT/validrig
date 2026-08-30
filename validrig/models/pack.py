# SPDX-License-Identifier: AGPL-3.0-or-later
"""Declarative pack schema — the content that defines an intended use.

An ``IntendedUsePack`` is authored, versioned content: manifest, case schema,
adjudicated cases, rubric, perturbation grid, batteries, systems under test,
judge config, and pre-registered acceptance thresholds. The engine validates
and executes packs but contains no pack-specific logic.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from validrig.models.sut import SUTSpec


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ElementSpec(_Frozen):
    """One typed element of a case's input (e.g. a report, prior notes, meds)."""

    name: str
    type: str
    modality: str
    language: str
    source_system: str | None = None
    required: bool = True
    # How the ingestion boundary must treat this element for PHI:
    #   "free_text"  -> run NER pseudonymization (default; unclassified is never
    #                   skipped — safe default).
    #   "identifier" -> the whole value IS a direct identifier (MRN, accession,
    #                   name field): capture it before redaction, hard-scrub that
    #                   exact value from every element, then reversibly encrypt it.
    #   "non_phi"    -> a coded / non-identifying value (e.g. a stage code); left
    #                   as-is. Choose this only when the field cannot carry PHI.
    pii: Literal["free_text", "identifier", "non_phi"] = "free_text"


class CaseSchema(_Frozen):
    elements: list[ElementSpec]

    def element_names(self) -> list[str]:
        return [e.name for e in self.elements]

    def by_name(self, name: str) -> ElementSpec | None:
        for e in self.elements:
            if e.name == name:
                return e
        return None


class Case(_Frozen):
    case_id: str
    elements: dict[str, Any]
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    # Optional pre-translated element variants: language code -> {element: text}.
    # Prepared and human-checked at pack build; the language axis selects among
    # them. Absent translations fall back to the original element text.
    translations: dict[str, dict[str, str]] = Field(default_factory=dict)


class Adjudication(_Frozen):
    """A physician's reference (gold) scores for one case against the rubric.

    The human reference layer, distinct from ``Case.ground_truth`` (machine-
    checkable evidence tokens). It records who established the gold and when, so
    it doubles as reference-standard provenance for QMS evidence.
    """

    case_id: str
    adjudicated_by: str
    adjudicated_at: str
    values: dict[str, float] = Field(default_factory=dict)


class RubricItem(_Frozen):
    id: str
    statement: str
    type: Literal["binary", "graded"]
    grading_instructions: str
    critical: bool = False
    evidence_required: bool = False
    max_score: float = 1.0
    # What the item grades: the final "output", or the agent "trace" (a process
    # rubric — did it query the right source, call the right tool). Output and
    # process scores are kept separate; a right answer via the wrong process
    # must fail the process item while the output item passes.
    target: Literal["output", "trace"] = "output"


class Rubric(_Frozen):
    items: list[RubricItem]

    def by_id(self, item_id: str) -> RubricItem | None:
        for i in self.items:
            if i.id == item_id:
                return i
        return None


class PerturbationSpec(_Frozen):
    """The perturbation grid: axis name -> list of level configurations."""

    axes: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class BatterySpec(_Frozen):
    """A pinned, named, versioned selection of cases x perturbations x SUTs."""

    id: str
    version: str
    cases: Union[list[str], Literal["all"]] = "all"
    perturbations: Union[list[str], Literal["all"]] = "all"
    # Which perturbation axes participate in this battery. Restricting the axes
    # is how a battery bounds its cartesian expansion (e.g. a robustness battery
    # uses ablation+format; a multilingual battery uses language+format).
    axes: Union[list[str], Literal["all"]] = "all"
    suts: list[str]
    n_samples: int = 1
    # Which declared judge grades this battery: a judge id from judge.yaml (the
    # default judge or one of its ``alternates``). ``None`` means the pack's
    # default judge. Selection is content, so it flows into pack_hash, and the
    # run pins the judge that actually graded — an offline battery graded by a
    # deterministic judge never pins the deployed LLM judge, or vice versa.
    judge: str | None = None


class JudgeSpec(_Frozen):
    id: str
    version: str
    kind: str
    binding: dict[str, Any] = Field(default_factory=dict)
    # LLM-judge grading config: include_document, include_reference, and pinned
    # evaluation_steps (keyed by rubric item id). Part of the pack, so any change
    # flows into pack_hash and therefore into run_id — a judge change is a
    # revalidation event with no extra machinery.
    grading: dict[str, Any] = Field(default_factory=dict)
    calibration_fraction: float = 0.1


class AcceptanceSpec(_Frozen):
    """Pre-registered thresholds, keyed by metric name."""

    thresholds: dict[str, float] = Field(default_factory=dict)


class Manifest(_Frozen):
    id: str
    version: str
    intended_use: str
    device_status_rationale: str
    population: str
    languages: list[str]


class Pack(_Frozen):
    manifest: Manifest
    case_schema: CaseSchema
    cases: list[Case]
    rubric: Rubric
    perturbations: PerturbationSpec
    batteries: list[BatterySpec]
    suts: list[SUTSpec]
    judge: JudgeSpec
    # Further judges the pack declares (judge.yaml ``alternates:``), selectable
    # per battery. A pack that grades paid batteries with a hosted LLM judge and
    # its offline battery with a deterministic one declares both here, rather
    # than having a run script substitute a judge the pins cannot see.
    alternate_judges: list[JudgeSpec] = Field(default_factory=list)
    acceptance: AcceptanceSpec
    # Post-market monitoring thresholds (distinct namespace from acceptance):
    # override_rate_max, input_completeness_min, override_trend_delta_max.
    monitoring: dict[str, float] = Field(default_factory=dict)
    adjudications: list[Adjudication] = Field(default_factory=list)
    # Recorded tool mocks for agent SUTs: {case_id: {tool: {args_hash: {...}}}}.
    mocks: dict[str, Any] = Field(default_factory=dict)
    pack_hash: str = ""

    def adjudication(self, case_id: str) -> Adjudication | None:
        for a in self.adjudications:
            if a.case_id == case_id:
                return a
        return None

    def judge_for(self, battery_id: str) -> JudgeSpec:
        """The judge a battery is graded by — its declared one, else the default.

        Resolving this from pack content (never from a caller) is what keeps a
        run's pinned ``judge_id`` truthful.
        """
        battery = self.battery(battery_id)
        if battery is None or battery.judge is None or battery.judge == self.judge.id:
            return self.judge
        for spec in self.alternate_judges:
            if spec.id == battery.judge:
                return spec
        raise KeyError(f"battery '{battery_id}' names unknown judge '{battery.judge}'")

    def battery(self, battery_id: str) -> BatterySpec | None:
        for b in self.batteries:
            if b.id == battery_id:
                return b
        return None

    def sut(self, sut_id: str) -> SUTSpec | None:
        for s in self.suts:
            if s.id == sut_id:
                return s
        return None

    def case(self, case_id: str) -> Case | None:
        for c in self.cases:
            if c.case_id == case_id:
                return c
        return None
