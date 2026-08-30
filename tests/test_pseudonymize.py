# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ingestion-boundary pseudonymization: contract + lightweight Presidio backend.

The Presidio tests skip where the [deid] extra (or the spaCy model) is not
installed, so the core suite stays dependency-light.
"""

import pytest

from validrig.ingest.pseudonymize import PseudonymizationResult, residual_identifiers


def test_residual_identifiers_boundary_check():
    assert residual_identifiers("summary with EGFR", ["John Doe", "egfr"]) == ["egfr"]
    assert residual_identifiers("clean text", ["John Doe"]) == []


def test_result_defaults_are_one_way():
    r = PseudonymizationResult(text="x")
    assert r.reversible is False
    assert r.reid_material is None


def _backend(monkeypatch):
    pytest.importorskip("presidio_analyzer")
    pytest.importorskip("presidio_anonymizer")
    from validrig.ingest.presidio_backend import PresidioPseudonymizer
    try:
        p = PresidioPseudonymizer()
    except Exception as exc:  # spaCy model not installed in this env
        pytest.skip(f"presidio/spacy model unavailable: {exc}")
    monkeypatch.setenv("HARNESS_REID_KEY", "0123456789abcdef")
    return p


def test_presidio_removes_structured_pii_and_names(monkeypatch):
    p = _backend(monkeypatch)
    text = "Dr. Jane Smith in Zurich; email john.doe@example.com, MRN 12345678."
    res = p.pseudonymize(text)
    # the boundary holds for the identifiers we know about
    assert residual_identifiers(res.text, ["Jane Smith", "john.doe@example.com", "Zurich"]) == []
    assert "PERSON" in res.entity_types
    assert "EMAIL_ADDRESS" in res.entity_types
    assert res.reversible is True


def test_presidio_reversible_round_trip(monkeypatch):
    p = _backend(monkeypatch)
    text = "Contact john.doe@example.com about patient in Zurich."
    res = p.pseudonymize(text)
    assert res.text != text
    assert p.reidentify(res) == text  # recovered with the hospital-side key


def test_presidio_missing_key_raises(monkeypatch):
    pytest.importorskip("presidio_analyzer")
    from validrig.ingest.presidio_backend import MissingReidKeyError, PresidioPseudonymizer
    try:
        p = PresidioPseudonymizer()
    except Exception as exc:
        pytest.skip(f"presidio/spacy model unavailable: {exc}")
    monkeypatch.delenv("HARNESS_REID_KEY", raising=False)
    with pytest.raises(MissingReidKeyError):
        p.pseudonymize("email john.doe@example.com")
