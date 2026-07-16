# SPDX-License-Identifier: AGPL-3.0-or-later
"""System-under-test domain models.

The engine treats every system under test — a single LLM call, a RAG chain, a
reasoning model, a tool-using agent, or a third-party product behind an API — as
an opaque ``SystemUnderTest`` that emits an observable ``Trace``. Only the
``llm_call`` kind is executed in M1; the other kinds are declared here so the
schema is stable for later milestones.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from harness.hashing import content_hash


class Step(BaseModel):
    """One observable step in a SUT's trace (e.g. a tool call, a reasoning turn)."""

    model_config = ConfigDict(frozen=True)
    name: str
    content: str
    data: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    model_config = ConfigDict(frozen=True)
    steps: list[Step] = Field(default_factory=list)
    final_output: str = ""


class SUTBinding(BaseModel):
    """How to reach and configure the system under test."""

    model_config = ConfigDict(frozen=True)
    model_id: str
    model_version: str
    endpoint: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str | None = None


SUTKind = Literal["llm_call", "chain", "agent", "external_api"]


class SUTSpec(BaseModel):
    """Declarative description of a system under test, drawn from a pack."""

    model_config = ConfigDict(frozen=True)
    id: str
    kind: SUTKind
    binding: SUTBinding
    tools: list[dict[str, Any]] = Field(default_factory=list)
    sut_hash: str = ""

    def with_hash(self) -> "SUTSpec":
        """Return a copy with ``sut_hash`` computed from the identifying fields."""
        payload = {
            "id": self.id,
            "kind": self.kind,
            "binding": self.binding.model_dump(mode="json"),
            "tools": self.tools,
        }
        return self.model_copy(update={"sut_hash": content_hash(payload)})
