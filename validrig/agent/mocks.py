# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic tool mocks — the agent analog of the fake model.

A mock is a recorded tool response keyed by ``(case_id, tool, args_hash)``. An
agent run against mocks is offline and byte-reproducible; a run against live
tools is flagged non-reproducible and must not seed a regression baseline.

Mocks are pack content (loaded into ``Pack.mocks``), so they flow into
``pack_hash`` and a change to a fixture is a visible, attributable change.
"""

from __future__ import annotations

from typing import Any

from validrig.hashing import content_hash


def tool_args_hash(args: dict[str, Any]) -> str:
    """Stable hash of a tool call's arguments (order-independent)."""
    return content_hash(args)[:12]


class MockStore:
    """Lookup over recorded tool fixtures.

    Fixture shape: ``{case_id: {tool: {args_hash: {"result": ..., "error": ...}}}}``.
    """

    def __init__(self, mocks: dict[str, Any] | None = None) -> None:
        self._mocks = mocks or {}

    def get(self, case_id: str, tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
        by_tool = self._mocks.get(case_id, {})
        by_hash = by_tool.get(tool, {})
        return by_hash.get(tool_args_hash(args))

    def has_tool(self, case_id: str, tool: str) -> bool:
        return bool(self._mocks.get(case_id, {}).get(tool))
