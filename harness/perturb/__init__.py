# SPDX-License-Identifier: AGPL-3.0-or-later
"""Perturbation engine: schema-typed transformers and battery expansion.

Transformers operate on the *types* of case elements, not on any use case, so a
transformer written once is reusable across every pack. Importing this package
registers the built-in axes.
"""

from harness.perturb.ablation import AblationTransformer
from harness.perturb.base import (
    PerturbedCase,
    Transformer,
    get_transformer,
    register,
)
from harness.perturb.format import FormatTransformer
from harness.perturb.language import LanguageTransformer

# Register built-in axes on import.
register(AblationTransformer())
register(FormatTransformer())
register(LanguageTransformer())

__all__ = [
    "PerturbedCase",
    "Transformer",
    "get_transformer",
    "register",
    "AblationTransformer",
    "FormatTransformer",
    "LanguageTransformer",
]
