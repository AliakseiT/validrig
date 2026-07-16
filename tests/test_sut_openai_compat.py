# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import httpx

from harness.models.sut import SUTBinding
from harness.sut.openai_compat import OpenAICompatModel


def _mock_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "MODEL SAID THIS"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
            },
        )

    return httpx.MockTransport(handler)


def _binding():
    return SUTBinding(
        model_id="gpt-x",
        model_version="2026-01",
        endpoint="https://example.invalid/v1/chat/completions",
        system_prompt="you are a summarizer",
        params={"temperature": 0},
    )


def test_maps_response_content_and_usage():
    captured = {}
    client = httpx.Client(transport=_mock_transport(captured))
    model = OpenAICompatModel(_binding(), client=client)
    out = model.generate("the clinical document", seed=0)
    assert out.raw_output == "MODEL SAID THIS"
    assert out.usage.prompt_tokens == 11
    assert out.usage.completion_tokens == 4
    assert out.usage.total_tokens == 15


def test_request_carries_system_prompt_and_document():
    captured = {}
    client = httpx.Client(transport=_mock_transport(captured))
    model = OpenAICompatModel(_binding(), client=client)
    model.generate("the clinical document", seed=0)
    messages = captured["body"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "you are a summarizer"
    assert messages[1]["role"] == "user"
    assert "the clinical document" in messages[1]["content"]
    assert captured["body"]["model"] == "gpt-x"


def test_live_adapter_flagged_non_reproducible():
    model = OpenAICompatModel(_binding())
    assert model.reproducible is False
