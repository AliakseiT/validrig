# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private recognition and recorded-response SUT adapter tests."""

import json

import httpx
import pytest

from validrig.models.sut import SUTBinding, SUTSpec
from validrig.sut.base import SUTContext
from validrig.sut.recognition import RecognitionWorker, RecordedRecognition
from validrig.sut.registry import build_adapter


def _binding(*, protocol: str, **params: object) -> SUTBinding:
    return SUTBinding(
        model_id="recognition-test",
        model_version="fixture-v1",
        endpoint=("https://worker.invalid/v1/structure" if protocol == "recognition" else None),
        params={"protocol": protocol, **params},
    )


def test_recorded_adapter_loads_local_json_response(tmp_path):
    response = tmp_path / "historical-44ai.json"
    response.write_text(
        json.dumps(
            {
                "output": {"profiles": [{"profile_name": "EPDMetaData_v1"}]},
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            }
        ),
        encoding="utf-8",
    )
    adapter = RecordedRecognition(
        _binding(
            protocol="recorded",
            reference_key="historical",
            reference_root=str(tmp_path),
        )
    )

    out = adapter.generate(
        "unused",
        seed=41,
        context=SUTContext(case_id="case-1", references={"historical": response.name}),
    )

    assert json.loads(out.raw_output)["profiles"]
    assert out.usage.prompt_tokens == 2
    assert out.usage.completion_tokens == 3
    assert out.usage.total_tokens == 5
    assert out.trace.steps[0].name == "recorded"
    assert out.trace.final_output == out.raw_output
    assert adapter.reproducible is True


def test_recorded_adapter_accepts_inline_json_manifest():
    adapter = RecordedRecognition(_binding(protocol="recorded"))
    out = adapter.generate(
        json.dumps({"output": "historical output"}),
        seed=0,
        context=SUTContext(case_id="case-1"),
    )
    assert out.raw_output == "historical output"


def test_recorded_adapter_rejects_remote_reference():
    adapter = RecordedRecognition(_binding(protocol="recorded"))
    with pytest.raises(ValueError, match="local JSON"):
        adapter.generate(
            "unused",
            seed=0,
            context=SUTContext(case_id="case-1", references={"output": "https://example.invalid/x.json"}),
        )


def test_registry_dispatches_explicit_external_protocols(tmp_path):
    recorded = SUTSpec(
        id="recorded",
        kind="external_api",
        binding=_binding(protocol="recorded", reference_root=str(tmp_path)),
    )
    recognition = SUTSpec(
        id="recognition",
        kind="external_api",
        binding=_binding(protocol="recognition"),
    )

    assert isinstance(build_adapter(recorded), RecordedRecognition)
    assert isinstance(build_adapter(recognition), RecognitionWorker)


def test_recognition_worker_maps_private_contract_and_metrics(monkeypatch):
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "profiles": [],
                "input_bytes": 123,
                "page_count": 2,
                "ocr_used": True,
                "text_source": "tesseract",
            },
        )

    monkeypatch.setenv("RECOGNITION_TEST_TOKEN", "local-only-token")
    binding = _binding(
        protocol="recognition",
        document_key="pdf",
        profile="EPDMetaData_v1",
        model_id="knowledgator/gliformer-base-v1",
        model_revision="revision-1",
    ).model_copy(update={"api_key_env": "RECOGNITION_TEST_TOKEN"})
    adapter = RecognitionWorker(
        binding,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    out = adapter.generate(
        "unused",
        seed=0,
        context=SUTContext(case_id="case-1", references={"pdf": "http://fixture/input.pdf"}),
    )

    assert captured["auth"] == "Bearer local-only-token"
    assert captured["body"] == {
        "document_url": "http://fixture/input.pdf",
        "profile": "EPDMetaData_v1",
        "model_id": "knowledgator/gliformer-base-v1",
        "model_revision": "revision-1",
    }
    assert json.loads(out.raw_output)["ocr_used"] is True
    assert out.trace.steps[0].data == {
        "input_bytes": 123,
        "page_count": 2,
        "ocr_used": True,
        "text_source": "tesseract",
    }
    assert out.usage.total_tokens == 0
    assert adapter.reproducible is False

