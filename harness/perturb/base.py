# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transformer abstraction and registry for the perturbation engine.

A ``Transformer`` is an engine-level, reusable axis that rewrites a case based on
its declared element *types*. Packs reference axes by name; the engine looks them
up in the registry. Adding a new axis is engine work done once; using it is
pack authoring.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from harness.models.pack import Case, CaseSchema


class PerturbedCase(BaseModel):
    """A case after a transformer has been applied, with provenance."""

    model_config = ConfigDict(frozen=True)
    perturbation_id: str
    case: Case
    provenance: dict[str, Any] = Field(default_factory=dict)


class Transformer(ABC):
    """Base class for a perturbation axis."""

    axis_name: str

    @abstractmethod
    def expand(
        self, case: Case, schema: CaseSchema, level_cfg: dict[str, Any]
    ) -> list[PerturbedCase]:
        """Apply one configured level of this axis to ``case``.

        Returns one or more perturbed cases. Must be deterministic: the same
        inputs always yield the same outputs in the same order.
        """
        raise NotImplementedError


REGISTRY: dict[str, Transformer] = {}


def register(transformer: Transformer) -> None:
    REGISTRY[transformer.axis_name] = transformer


def get_transformer(axis: str) -> Transformer:
    try:
        return REGISTRY[axis]
    except KeyError as exc:
        raise KeyError(f"no transformer registered for axis '{axis}'") from exc
