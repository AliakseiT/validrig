# SPDX-License-Identifier: AGPL-3.0-or-later
"""Language axis: present a case in a chosen language.

Clinical performance is language-dependent, so a harness needs to characterize a
system across the languages of its local population. Translations are prepared
and human-checked at pack build (never generated at run time); this axis simply
selects among them. An element with no translation for the target language falls
back to its original text, and the fallback is recorded in provenance so the
contract can distinguish a genuine multilingual result from an untranslated one.
"""

from __future__ import annotations

from typing import Any

from harness.models.pack import Case, CaseSchema
from harness.perturb.base import PerturbedCase, Transformer


class LanguageTransformer(Transformer):
    axis_name = "language"

    def expand(
        self, case: Case, schema: CaseSchema, level_cfg: dict[str, Any]
    ) -> list[PerturbedCase]:
        lang = level_cfg.get("lang")
        if not lang:
            raise ValueError("language axis level requires a 'lang' code")

        variants = case.translations.get(lang, {})
        new_elements = dict(case.elements)
        translated: list[str] = []
        fell_back: list[str] = []
        for name in case.elements:
            if name in variants:
                new_elements[name] = variants[name]
                translated.append(name)
            else:
                fell_back.append(name)

        new_case = case.model_copy(update={"elements": new_elements})
        return [
            PerturbedCase(
                perturbation_id=f"language:{lang}",
                case=new_case,
                provenance={
                    "axis": "language",
                    "lang": lang,
                    "translated": sorted(translated),
                    "fell_back": sorted(fell_back),
                },
            )
        ]
