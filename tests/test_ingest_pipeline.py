# SPDX-License-Identifier: AGPL-3.0-or-later
"""Enforced ingestion pipeline (B1) + PII element classes (B2)."""

import pytest

from harness.ingest.pipeline import (
    INGEST_GUARANTEE,
    IngestError,
    ingest_case,
    scrub_known,
)
from harness.ingest.pseudonymize import Pseudonymizer, PseudonymizationResult
from harness.models.pack import CaseSchema, ElementSpec


class _Redactor(Pseudonymizer):
    """Test double: removes exactly the given substrings (stands in for NER)."""
    def __init__(self, redact=()):
        self._redact = list(redact)
    def pseudonymize(self, text):
        types = []
        for v in self._redact:
            if v in text:
                text = text.replace(v, "<PERSON>"); types.append("PERSON")
        return PseudonymizationResult(text=text, entity_types=types,
                                      reversible=True, reid_material={"n": len(types)})


def _schema(**pii):
    els = [ElementSpec(name=n, type="text", modality="text", language="en", pii=p)
           for n, p in pii.items()]
    return CaseSchema(elements=els)


def test_identifier_captured_scrubbed_and_placeheld():
    schema = _schema(mrn="identifier", note="free_text")
    raw = {"mrn": "7654321", "note": "Follow-up for patient 7654321, EGFR+."}
    store, reid, rep = ingest_case(raw, schema, _Redactor(), case_id="c1")
    # the identifier field becomes a placeholder; plaintext goes hospital-side
    assert store["mrn"] == "<IDENTIFIER:mrn>"
    assert reid["identifiers"]["mrn"] == "7654321"
    # and the same known value is scrubbed from the free-text element
    assert "7654321" not in store["note"]
    assert "EGFR+" in store["note"]  # clinical signal survives
    assert rep.residual_clean and rep.known_identifiers == 1


def test_non_phi_passthrough():
    schema = _schema(stage="non_phi", note="free_text")
    raw = {"stage": "IIIA", "note": "Adenocarcinoma."}
    store, _, rep = ingest_case(raw, schema, _Redactor(), case_id="c2")
    assert store["stage"] == "IIIA"  # untouched
    assert rep.non_phi_fields == ["stage"]


def test_unclassified_defaults_to_free_text_ner():
    schema = _schema()  # no specs at all
    store, _, rep = ingest_case({"note": "Seen by Dr Meier."}, schema,
                                _Redactor(["Dr Meier"]), case_id="c3")
    assert store["note"] == "Seen by <PERSON>."
    assert rep.free_text_fields == ["note"]


def test_residual_gate_hard_fails_on_misdeclared_non_phi():
    # an identifier value that ALSO appears in a field wrongly declared non_phi
    schema = _schema(mrn="identifier", coded="non_phi")
    raw = {"mrn": "7654321", "coded": "ref 7654321"}
    with pytest.raises(IngestError, match="survived"):
        ingest_case(raw, schema, _Redactor(), case_id="c4")


def test_scrub_known_tolerant_to_punctuation():
    # captured 7654321 must also catch 765-4321 / 765 4321
    assert "7654321" not in scrub_known("id 7654321", ["7654321"])
    assert "765-4321" not in scrub_known("id 765-4321", ["7654321"])
    assert "765 4321" not in scrub_known("id 765 4321", ["7654321"])


def test_guarantee_never_claims_no_phi():
    assert "NOT a claim" in INGEST_GUARANTEE
    assert "no phi" not in INGEST_GUARANTEE.lower()


def test_cli_refuses_reid_out_inside_casebank(tmp_path):
    # The guard runs before any backend init, so this needs no [deid] stack.
    from harness.cli import main

    raw = tmp_path / "raw"; raw.mkdir()
    (raw / "c.json").write_text('{"case_id":"c","elements":{"note":"x"}}')
    rc = main(["ingest", "packs/demo-tumor-board", "--raw", str(raw),
               "--reid-out", "packs/demo-tumor-board/casebank/x"])
    assert rc == 2
