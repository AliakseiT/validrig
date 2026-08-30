# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine must contain zero use-case-specific vocabulary.

Design goal #1: a new intended use is a new pack, not engine code. If any
use-case term leaks into the engine, the abstraction is wrong. This test makes
that guarantee literal.
"""

from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "validrig"

# Vocabulary that belongs only in packs (content), never in the engine.
FORBIDDEN = ["tumor", "pathology_report", "molecular_report", "imaging_text", "adenocarcinoma"]


def test_engine_has_no_usecase_terms():
    offenders = []
    for path in ENGINE.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN:
            if term in text:
                offenders.append(f"{path}: {term}")
    assert not offenders, "use-case vocabulary leaked into engine:\n" + "\n".join(offenders)
