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
from harness.sut.auth import auth_headers
from harness.sut.base import GenerationOutput, SUTAdapter


class OpenAICompatModel(SUTAdapter):
    reproducible = False

    def __init__(
        self, binding: SUTBinding, client: httpx.Client | None = None, max_retries: int = 3
    ) -> None:
        if not binding.endpoint:
            raise ValueError("OpenAICompatModel requires binding.endpoint")
        self.binding = binding
        self._client = client or httpx.Client(timeout=120.0)
        self.max_retries = max_retries

    def _post(self, payload: dict) -> httpx.Response:
        """POST with a small retry on transient network/5xx errors.

        Real endpoints blip (disconnects, timeouts, 502/503/429); one flaky call
        must not kill a whole battery. 4xx (e.g. auth, bad request) fail fast.
        """
        headers = auth_headers(self.binding.api_key_env)
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.post(self.binding.endpoint, json=payload, headers=headers)
                if resp.status_code >= 500 or resp.status_code == 429:
                    last = httpx.HTTPStatusError(
                        f"transient {resp.status_code}", request=resp.request, response=resp
                    )
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                # HTTPStatusError from raise_for_status is a 4xx here -> don't retry.
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 \
                        and exc.response.status_code != 429:
                    raise
                last = exc
        raise last if last else RuntimeError("request failed")

    def _build_messages(self, document: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.binding.system_prompt:
            messages.append({"role": "system", "content": self.binding.system_prompt})
        messages.append({"role": "user", "content": document})
        return messages

    def generate(self, document: str, seed: int, context=None) -> GenerationOutput:
        payload = {
            "model": self.binding.model_id,
            "messages": self._build_messages(document),
            **self.binding.params,
        }
        data = self._post(payload).json()

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
