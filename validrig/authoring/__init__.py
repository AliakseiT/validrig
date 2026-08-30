# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pack authoring tooling: linting and scaffolding.

Supports design goal #1 — standing up a new intended use is a content-authoring
exercise, not a software project. ``scaffold_pack`` emits a valid, runnable
skeleton; ``lint_pack`` checks a pack for authoring gaps before it is run.
"""

from validrig.authoring.lint import LintFinding, lint_pack
from validrig.authoring.scaffold import scaffold_pack

__all__ = ["LintFinding", "lint_pack", "scaffold_pack"]
