# SPDX-License-Identifier: AGPL-3.0-or-later
from validrig.models.pack import Case, CaseSchema, ElementSpec
from validrig.perturb.format import DOCUMENT_KEY, FormatTransformer


def _schema():
    return CaseSchema(
        elements=[
            ElementSpec(name="pathology_report", type="text", modality="m", language="en"),
            ElementSpec(name="molecular_report", type="text", modality="m", language="en"),
        ]
    )


def _case():
    return Case(
        case_id="X",
        elements={"pathology_report": "PATH", "molecular_report": "MOL"},
        ground_truth={},
    )


def test_each_style_produces_distinct_document():
    t = FormatTransformer()
    docs = {}
    for style in ("raw_dump", "structured", "tabular"):
        pc = t.expand(_case(), _schema(), {"style": style})[0]
        docs[style] = pc.case.elements[DOCUMENT_KEY]
    assert len(set(docs.values())) == 3


def test_structured_has_section_headers():
    t = FormatTransformer()
    pc = t.expand(_case(), _schema(), {"style": "structured"})[0]
    doc = pc.case.elements[DOCUMENT_KEY]
    assert "## pathology_report" in doc
    # declaration order preserved: pathology before molecular
    assert doc.index("pathology_report") < doc.index("molecular_report")


def test_render_is_deterministic():
    t = FormatTransformer()
    a = t.expand(_case(), _schema(), {"style": "tabular"})[0].case.elements[DOCUMENT_KEY]
    b = t.expand(_case(), _schema(), {"style": "tabular"})[0].case.elements[DOCUMENT_KEY]
    assert a == b


def test_perturbation_id_names_style():
    t = FormatTransformer()
    pc = t.expand(_case(), _schema(), {"style": "raw_dump"})[0]
    assert pc.perturbation_id == "format:raw_dump"
