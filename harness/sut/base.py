# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adapter interface shared by every system under test.

Whatever the SUT is — a single call, a chain, an agent, a third-party API — the
engine only ever calls ``generate(document, seed)`` and receives a
``GenerationOutput`` with the raw output, an observable trace, and token usage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from harness.models.results import TokenUsage
from harness.models.sut import Trace


@dataclass(frozen=True)
class GenerationOutput:
    raw_output: str
    trace: Trace
    usage: TokenUsage


class SUTAdapter(ABC):
    """Base class for all SUT adapters."""

    #: Whether results from this adapter are safe to use as a regression baseline.
    #: Live, non-recorded calls set this False.
    reproducible: bool = True

    @abstractmethod
    def generate(self, document: str, seed: int) -> GenerationOutput:
        raise NotImplementedError
