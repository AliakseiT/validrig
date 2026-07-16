# SPDX-License-Identifier: AGPL-3.0-or-later
from harness.models.pack import Case, CaseSchema, ElementSpec
from harness.perturb.language import LanguageTransformer


def _schema():
    return CaseSchema(
        elements=[
            ElementSpec(name="report", type="text", modality="m", language="en"),
            ElementSpec(name="notes", type="text", modality="m", language="en"),
        ]
    )


def _case():
    return Case(
        case_id="X",
        elements={"report": "English report EGFR", "notes": "English notes"},
        ground_truth={},
        translations={"de": {"report": "Deutscher Bericht EGFR"}},
    )


def test_selects_translation_when_present():
    t = LanguageTransformer()
    pc = t.expand(_case(), _schema(), {"lang": "de"})[0]
    assert pc.case.elements["report"] == "Deutscher Bericht EGFR"
    assert pc.perturbation_id == "language:de"


def test_language_invariant_token_survives_translation():
    t = LanguageTransformer()
    pc = t.expand(_case(), _schema(), {"lang": "de"})[0]
    assert "EGFR" in pc.case.elements["report"]


def test_missing_translation_falls_back_and_is_recorded():
    t = LanguageTransformer()
    pc = t.expand(_case(), _schema(), {"lang": "de"})[0]
    # 'notes' has no German variant -> keeps original, recorded as fallback
    assert pc.case.elements["notes"] == "English notes"
    assert pc.provenance["fell_back"] == ["notes"]
    assert pc.provenance["translated"] == ["report"]


def test_missing_language_uses_all_fallbacks():
    t = LanguageTransformer()
    pc = t.expand(_case(), _schema(), {"lang": "fr"})[0]
    assert pc.provenance["fell_back"] == ["notes", "report"]
    assert pc.provenance["translated"] == []
