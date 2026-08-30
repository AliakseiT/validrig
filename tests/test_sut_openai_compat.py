# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import httpx

from validrig.models.sut import SUTBinding
from validrig.sut.openai_compat import OpenAICompatModel


def _mock_transport(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        captured["auth"] = request.headers.get("Authorization")
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


def test_api_key_header_from_env(monkeypatch):
    import httpx as _httpx
    from validrig.models.sut import SUTBinding as _B
    monkeypatch.setenv("TEST_LLM_KEY", "secret-123")
    cap = {}
    binding = _B(model_id="m", model_version="1",
                 endpoint="https://x.invalid/v1/chat/completions", api_key_env="TEST_LLM_KEY")
    model = OpenAICompatModel(binding, client=_httpx.Client(transport=_mock_transport(cap)))
    model.generate("doc", seed=0)
    assert cap["auth"] == "Bearer secret-123"


def test_missing_api_key_raises(monkeypatch):
    import httpx as _httpx
    import pytest
    from validrig.models.sut import SUTBinding as _B
    from validrig.sut.auth import MissingApiKeyError
    monkeypatch.delenv("TEST_LLM_KEY", raising=False)
    binding = _B(model_id="m", model_version="1",
                 endpoint="https://x.invalid/v1/chat/completions", api_key_env="TEST_LLM_KEY")
    model = OpenAICompatModel(binding, client=_httpx.Client(transport=_mock_transport({})))
    with pytest.raises(MissingApiKeyError):
        model.generate("doc", seed=0)


def test_api_key_value_not_in_sut_hash(monkeypatch):
    from validrig.models.sut import SUTSpec as _S, SUTBinding as _B
    monkeypatch.setenv("TEST_LLM_KEY", "super-secret-value")
    spec = _S(id="s", kind="llm_call", binding=_B(
        model_id="m", model_version="1", endpoint="https://x/v1", api_key_env="TEST_LLM_KEY")).with_hash()
    # the hash covers the env-var NAME, never the secret value
    assert "super-secret-value" not in spec.sut_hash
    assert spec.sut_hash  # computed


def test_retries_transient_then_succeeds():
    import httpx as _httpx
    from validrig.models.sut import SUTBinding as _B
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _httpx.RemoteProtocolError("server disconnected", request=request)
        return _httpx.Response(200, json={
            "choices": [{"message": {"content": "recovered"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    model = OpenAICompatModel(_binding(), client=_httpx.Client(transport=_httpx.MockTransport(handler)))
    out = model.generate("doc", seed=0)
    assert out.raw_output == "recovered"
    assert calls["n"] == 2  # retried once


def test_4xx_fails_fast_no_retry():
    import httpx as _httpx
    import pytest
    from validrig.models.sut import SUTBinding as _B
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _httpx.Response(400, json={"error": "bad request"})

    model = OpenAICompatModel(_binding(), client=_httpx.Client(transport=_httpx.MockTransport(handler)))
    with pytest.raises(_httpx.HTTPStatusError):
        model.generate("doc", seed=0)
    assert calls["n"] == 1  # no retry on 4xx
