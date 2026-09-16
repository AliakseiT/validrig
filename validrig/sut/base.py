# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adapter interface shared by every system under test.

Whatever the SUT is — a single call, a chain, an agent, a third-party API — the
engine only ever calls ``generate(document, seed)`` and receives a
``GenerationOutput`` with the raw output, an observable trace, and token usage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping

from validrig.models.results import TokenUsage
from validrig.models.sut import Trace


@dataclass(frozen=True)
class GenerationOutput:
    raw_output: str
    trace: Trace
    usage: TokenUsage


@dataclass(frozen=True)
class SUTContext:
    """Per-unit context an adapter may need beyond the document.

    ``case_id`` lets agent adapters look up recorded tool mocks.
    ``tool_perturbation`` (optional) describes agent-axis perturbations for this
    unit — which tools are unavailable, or a degraded response for one tool.
    Plain LLM adapters ignore both.
    """

    case_id: str
    tool_perturbation: dict | None = None
    # Case-local references (for example a PDF URL or a recorded JSON output).
    # They are passed to the adapter for this invocation and are never persisted
    # in a Generation or sent to a judge unless the adapter explicitly does so.
    references: Mapping[str, str] | None = None


class SUTAdapter(ABC):
    """Base class for all SUT adapters."""

    #: Whether results from this adapter are safe to use as a regression baseline.
    #: Live, non-recorded calls set this False.
    reproducible: bool = True

    @abstractmethod
    def generate(
        self, document: str, seed: int, context: SUTContext | None = None
    ) -> GenerationOutput:
        raise NotImplementedError
