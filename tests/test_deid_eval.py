# SPDX-License-Identifier: AGPL-3.0-or-later
"""De-id recall measurement + clinical recognizers (A2)."""

import pytest

from harness.ingest.deid_eval import PhiItem, measure_deid, render_deid_md
from harness.ingest.pseudonymize import Pseudonymizer, PseudonymizationResult


class _Redactor(Pseudonymizer):
    """Test double: removes exactly the given substrings."""
    def __init__(self, redact):
        self._redact = redact
    def pseudonymize(self, text):
        for v in self._redact:
            text = text.replace(v, "<REDACTED>")
        return PseudonymizationResult(text=text, reversible=False)


_PHI = [PhiItem("PERSON", "Erika Mustermann"), PhiItem("CH_AHV", "756.1234.5678.90"),
        PhiItem("MEDICAL_RECORD_NUMBER", "7654321")]


def test_perfect_and_zero_recall():
    notes = ["Lung adenocarcinoma, EGFR mutation.", "KRAS-mutant tumor."]
    full = measure_deid(_Redactor([p.value for p in _PHI]), notes, _PHI, ["EGFR", "KRAS"])
    assert full["overall_recall"] == 1.0
    assert all(d["recall"] == 1.0 for d in full["per_type_recall"].values())

    none = measure_deid(_Redactor([]), notes, _PHI, ["EGFR"])
    assert none["overall_recall"] == 0.0


def test_per_type_breakdown_and_utility_retention():
    notes = ["Lung adenocarcinoma with EGFR mutation."]
    # redact only the AHV -> CH_AHV recall 1.0, others 0.0
    rep = measure_deid(_Redactor(["756.1234.5678.90"]), notes, _PHI, ["EGFR", "adenocarcinoma"])
    assert rep["per_type_recall"]["CH_AHV"]["recall"] == 1.0
    assert rep["per_type_recall"]["PERSON"]["recall"] == 0.0
    # clinical tokens present in the note and not redacted -> retained
    assert rep["utility_retention"] == 1.0
    assert rep["utility_n"] == 2


def test_utility_penalises_over_redaction():
    notes = ["Lung adenocarcinoma with EGFR mutation."]
    # a pseudonymizer that wrongly redacts a clinical token
    rep = measure_deid(_Redactor(["EGFR"]), notes, _PHI, ["EGFR", "adenocarcinoma"])
    assert rep["utility_retention"] == 0.5  # EGFR gone, adenocarcinoma kept


def test_render_md_has_upper_bound_caveat():
    rep = measure_deid(_Redactor([]), ["EGFR."], _PHI, ["EGFR"])
    md = render_deid_md(rep)
    assert md.startswith("# De-identification recall evaluation")
    assert "Upper bound" in md
    assert "| PHI type | n | leakage-recall |" in md


# --- A2: clinical recognizers lift recall (Presidio; skip if unavailable) -----

def _presidio(monkeypatch, clinical):
    pytest.importorskip("presidio_analyzer")
    from harness.ingest.presidio_backend import PresidioPseudonymizer
    try:
        p = PresidioPseudonymizer(clinical=clinical)
    except Exception as exc:
        pytest.skip(f"presidio/model unavailable: {exc}")
    monkeypatch.setenv("HARNESS_REID_KEY", "0123456789abcdef")
    return p


def test_clinical_recognizers_lift_ch_ahv_recall(monkeypatch):
    phi = [PhiItem("CH_AHV", "756.1234.5678.90")]
    notes = ["Lung adenocarcinoma with EGFR mutation."]
    with_clinical = measure_deid(_presidio(monkeypatch, True), notes, phi, ["EGFR"])
    without = measure_deid(_presidio(monkeypatch, False), notes, phi, ["EGFR"])
    # the Swiss AHV is redacted with clinical recognizers, and (default) leaks without
    assert with_clinical["per_type_recall"]["CH_AHV"]["recall"] == 1.0
    assert without["per_type_recall"]["CH_AHV"]["recall"] == 0.0
    # clinical signal survives either way
    assert with_clinical["utility_retention"] == 1.0
