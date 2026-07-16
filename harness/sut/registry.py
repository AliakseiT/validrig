# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a concrete SUT adapter from a declarative ``SUTSpec``.

The mapping from spec to adapter is the only place the engine decides *how* to
reach a system under test. The fake model is selected for any ``llm_call`` whose
binding names ``model_id: fake``; everything else with an endpoint goes through
the OpenAI-compatible adapter.
"""

from __future__ import annotations

from harness.models.sut import SUTSpec
from harness.sut.base import SUTAdapter
from harness.sut.fake import FakeModel


def build_adapter(spec: SUTSpec) -> SUTAdapter:
    binding = spec.binding
    if spec.kind == "llm_call" and binding.model_id == "fake":
        return FakeModel(
            system_prompt=binding.system_prompt,
            model_version=binding.model_version,
            suppress=binding.params.get("suppress"),
        )
    if spec.kind == "llm_call":
        # Imported lazily so offline runs never need httpx configured.
        from harness.sut.openai_compat import OpenAICompatModel

        return OpenAICompatModel(binding)
    raise NotImplementedError(
        f"SUT kind '{spec.kind}' is not executable in M1 (only llm_call)"
    )
