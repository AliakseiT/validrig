# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a concrete SUT adapter from a declarative ``SUTSpec``.

The mapping from spec to adapter is the only place the engine decides *how* to
reach a system under test. The fake model is selected for any ``llm_call`` whose
binding names ``model_id: fake``; everything else with an endpoint goes through
the OpenAI-compatible adapter.
"""

from __future__ import annotations

from typing import Any

from validrig.models.sut import SUTSpec
from validrig.sut.base import SUTAdapter
from validrig.sut.fake import FakeModel


def build_adapter(spec: SUTSpec, mocks: dict[str, Any] | None = None) -> SUTAdapter:
    binding = spec.binding
    if spec.kind == "llm_call" and binding.model_id == "fake":
        return FakeModel(
            system_prompt=binding.system_prompt,
            model_version=binding.model_version,
            suppress=binding.params.get("suppress"),
        )
    if spec.kind == "llm_call":
        # Imported lazily so offline runs never need httpx configured.
        from validrig.sut.openai_compat import OpenAICompatModel

        return OpenAICompatModel(binding)
    if spec.kind == "agent" and binding.model_id == "fake":
        from validrig.agent.fake_agent import FakeAgent
        from validrig.agent.mocks import MockStore

        return FakeAgent(
            system_prompt=binding.system_prompt,
            model_version=binding.model_version,
            tools_to_call=binding.params.get("tools_to_call", []),
            mock_store=MockStore(mocks or {}),
        )
    raise NotImplementedError(
        f"SUT kind '{spec.kind}' with model '{binding.model_id}' is not executable"
    )
