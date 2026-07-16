# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI-compatible chat-completions SUT adapter.

Speaks the ``/chat/completions`` protocol used by OpenAI, many BAA'd providers,
and local servers such as vLLM. It is built to the same ``SUTAdapter`` interface
as the fake model and its request/response mapping is unit-tested with a mocked
transport — no live network call is made in the test suite.

Live calls are marked ``reproducible = False``: their outputs must not seed a
regression baseline unless captured via recorded responses.
"""

from __future__ import annotations

import httpx

from harness.models.results import TokenUsage
from harness.models.sut import SUTBinding, Step, Trace
from harness.sut.base import GenerationOutput, SUTAdapter


class OpenAICompatModel(SUTAdapter):
    reproducible = False

    def __init__(self, binding: SUTBinding, client: httpx.Client | None = None) -> None:
        if not binding.endpoint:
            raise ValueError("OpenAICompatModel requires binding.endpoint")
        self.binding = binding
        self._client = client or httpx.Client(timeout=60.0)

    def _build_messages(self, document: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.binding.system_prompt:
            messages.append({"role": "system", "content": self.binding.system_prompt})
        messages.append({"role": "user", "content": document})
        return messages

    def generate(self, document: str, seed: int) -> GenerationOutput:
        payload = {
            "model": self.binding.model_id,
            "messages": self._build_messages(document),
            **self.binding.params,
        }
        response = self._client.post(self.binding.endpoint, json=payload)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage_raw = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
            completion_tokens=int(usage_raw.get("completion_tokens", 0)),
            total_tokens=int(
                usage_raw.get(
                    "total_tokens",
                    int(usage_raw.get("prompt_tokens", 0))
                    + int(usage_raw.get("completion_tokens", 0)),
                )
            ),
        )
        trace = Trace(
            steps=[Step(name="chat_completion", content=content)],
            final_output=content,
        )
        return GenerationOutput(raw_output=content, trace=trace, usage=usage)
