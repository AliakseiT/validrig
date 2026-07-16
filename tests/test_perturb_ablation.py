# SPDX-License-Identifier: AGPL-3.0-or-later
from harness.models.pack import Case, CaseSchema, ElementSpec
from harness.perturb.ablation import AblationTransformer
from harness.perturb.base import get_transformer


def _schema():
    return CaseSchema(
        elements=[
            ElementSpec(name="a", type="text", modality="m", language="en"),
            ElementSpec(name="b", type="text", modality="m", language="en"),
            ElementSpec(name="c", type="text", modality="m", language="en"),
        ]
    )


def _case():
    return Case(case_id="X", elements={"a": "AA", "b": "BB", "c": "CC"}, ground_truth={})


def test_drop_removes_element():
    t = AblationTransformer()
    out = t.expand(_case(), _schema(), {"id": "no_b", "drop": ["b"]})
    assert len(out) == 1
    pc = out[0]
    assert "b" not in pc.case.elements
    assert pc.case.elements["a"] == "AA"
    assert pc.provenance["dropped"] == ["b"]


def test_perturbation_id_is_deterministic():
    t = AblationTransformer()
    a = t.expand(_case(), _schema(), {"drop": ["c", "b"]})[0]
    b = t.expand(_case(), _schema(), {"drop": ["b", "c"]})[0]
    assert a.perturbation_id == b.perturbation_id  # order-independent


def test_baseline_keeps_everything():
    t = AblationTransformer()
    out = t.expand(_case(), _schema(), {"id": "baseline", "drop": []})
    assert out[0].case.elements == _case().elements
    assert out[0].perturbation_id == "ablation:none"


def test_powerset_budget_is_deterministic_and_capped():
    t = AblationTransformer()
    cfg = {"powerset": True, "budget": 3, "elements": ["a", "b", "c"]}
    first = t.expand(_case(), _schema(), cfg)
    second = t.expand(_case(), _schema(), cfg)
    assert len(first) == 3
    assert [p.perturbation_id for p in first] == [p.perturbation_id for p in second]


def test_registry_resolves_ablation():
    assert get_transformer("ablation").axis_name == "ablation"
