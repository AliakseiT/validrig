# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lightweight Presidio pseudonymizer (optional extra: ``[deid]``).

Uses Microsoft Presidio in a deliberately lightweight configuration — a small
spaCy model (``en_core_web_sm``) plus regex pattern recognizers, no transformer /
HF models — and the reversible ``encrypt`` operator so the AES key IS the
re-identification secret (read from the environment, kept hospital-side, never
stored). Re-identification uses Presidio's ``DeanonymizeEngine``.

Recall caveat: this reliably catches structured PII and basic names/locations; it
is not a validated clinical de-identifier. Measure recall on your data before
relying on it, and add a domain NER model only if the gap justifies it.
"""

from __future__ import annotations

import os

from harness.ingest.pseudonymize import Pseudonymizer, PseudonymizationResult

_DEFAULT_MODEL = "en_core_web_sm"


class MissingReidKeyError(RuntimeError):
    """Raised when the re-identification key env var is not set."""


class PresidioPseudonymizer(Pseudonymizer):
    def __init__(
        self,
        key_env: str = "HARNESS_REID_KEY",
        model: str = _DEFAULT_MODEL,
        language: str = "en",
    ) -> None:
        # Lazy imports so the core engine never needs the [deid] stack installed.
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine, DeanonymizeEngine

        self.key_env = key_env
        self.language = language
        nlp = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": language, "model_name": model}],
        }).create_engine()
        self._analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=[language])
        self._anonymizer = AnonymizerEngine()
        self._deanonymizer = DeanonymizeEngine()

    def _key(self) -> str:
        key = os.environ.get(self.key_env)
        if not key:
            raise MissingReidKeyError(
                f"environment variable '{self.key_env}' is not set "
                "(the AES re-identification key, kept hospital-side)"
            )
        return key

    def pseudonymize(self, text: str) -> PseudonymizationResult:
        from presidio_anonymizer.entities import OperatorConfig

        results = self._analyzer.analyze(text=text, language=self.language)
        out = self._anonymizer.anonymize(
            text=text, analyzer_results=results,
            operators={"DEFAULT": OperatorConfig("encrypt", {"key": self._key()})},
        )
        return PseudonymizationResult(
            text=out.text,
            entity_types=sorted({r.entity_type for r in results}),
            reversible=True,
            reid_material={"items": out.items},  # hospital-side only; not for the store
        )

    def reidentify(self, result: PseudonymizationResult) -> str:
        from presidio_anonymizer.entities import OperatorConfig

        items = (result.reid_material or {}).get("items")
        if items is None:
            raise ValueError("no re-identification material on this result")
        return self._deanonymizer.deanonymize(
            result.text, items,
            {"DEFAULT": OperatorConfig("decrypt", {"key": self._key()})},
        ).text
