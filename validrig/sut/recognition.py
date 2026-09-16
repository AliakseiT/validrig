# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local recorded and private document-recognition SUT adapters.

These adapters share the normal :class:`SUTAdapter` seam. A pack can compare a
historical response with a private recognition worker without adding provider-
specific logic to the execution engine:

* ``protocol: recorded`` reads a case-local JSON response and is reproducible.
* ``protocol: recognition`` calls a private ``/v1/structure`` endpoint using a
  case-local PDF URL and records the bounded response as a generation.

References are supplied through ``SUTContext.references``. They are local pack
content and are never persisted as paths in a run or sent to a judge by this
module. The recognition endpoint receives only the configured PDF URL, as
required by its private worker contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from validrig.models.results import TokenUsage
from validrig.models.sut import SUTBinding, Step, Trace
from validrig.pathsafe import confined_path
from validrig.sut.auth import auth_headers
from validrig.sut.base import GenerationOutput, SUTAdapter, SUTContext


_DEFAULT_PROFILE = "EPDMetaData_v1"
_DEFAULT_REFERENCE_KEY = "output"
_DEFAULT_DOCUMENT_KEY = "pdf"
_MAX_RECORDED_BYTES = 10 * 1024 * 1024


def _json_document(document: str) -> dict[str, Any]:
    """Read an inline adapter manifest, if the caller supplied one."""

    try:
        value = json.loads(document)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _reference(
    document: str,
    context: SUTContext | None,
    key: str,
) -> Any:
    """Resolve a reference from per-case context or an inline manifest."""

    references = context.references if context else None
    if references and key in references:
        return references[key]
    return _json_document(document).get(key)


def _load_json_reference(value: Any, root: Path | None) -> Any:
    """Load a local JSON response, refusing remote references and large files."""

    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("recorded reference must be a non-empty string")
    candidate = value.strip()
    if candidate.startswith(("http://", "https://", "file://")):
        raise ValueError("recorded references must be local JSON files or inline JSON")

    if candidate.startswith(("{", "[")):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError("recorded inline reference is not valid JSON") from exc

    path = Path(candidate)
    if root is not None:
        path = confined_path(root, candidate)
    if not path.is_file():
        raise ValueError(f"recorded reference does not exist: {candidate}")
    if path.stat().st_size > _MAX_RECORDED_BYTES:
        raise ValueError("recorded reference exceeds the 10 MiB safety limit")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("recorded reference could not be read as JSON") from exc


def _raw_output(record: Any) -> str:
    """Normalize a recorded response to the generation's text output."""

    if isinstance(record, dict) and "raw_output" in record:
        value = record["raw_output"]
    elif isinstance(record, dict) and "output" in record:
        value = record["output"]
    else:
        # A direct recognition response (for example ``{"profiles": [...]}``)
        # is itself the output.
        value = record
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _usage(record: Any) -> TokenUsage:
    if not isinstance(record, dict) or not isinstance(record.get("usage"), dict):
        return TokenUsage.zero()
    raw = record["usage"]
    prompt = int(raw.get("prompt_tokens", 0))
    completion = int(raw.get("completion_tokens", 0))
    total = int(raw.get("total_tokens", prompt + completion))
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cost_chf=float(raw.get("cost_chf", 0.0)),
    )


def _trace(record: Any, raw_output: str) -> Trace:
    if isinstance(record, dict) and isinstance(record.get("trace"), dict):
        try:
            trace = Trace(**record["trace"])
        except (TypeError, ValueError) as exc:
            raise ValueError("recorded trace does not match the Trace schema") from exc
        return trace.model_copy(update={"final_output": raw_output})
    return Trace(
        steps=[Step(name="recorded", content=raw_output, data={"recorded": True})],
        final_output=raw_output,
    )


class RecordedRecognition(SUTAdapter):
    """Replay a case-local JSON response as an immutable baseline generation."""

    reproducible = True

    def __init__(self, binding: SUTBinding) -> None:
        self.binding = binding
        self.reference_key = str(binding.params.get("reference_key", _DEFAULT_REFERENCE_KEY))
        root = binding.params.get("reference_root")
        self.reference_root = Path(str(root)).resolve() if root else None

    def generate(
        self, document: str, seed: int, context: SUTContext | None = None
    ) -> GenerationOutput:
        del seed  # Recorded responses do not vary by sampling seed.
        value = _reference(document, context, self.reference_key)
        if value is None:
            raise ValueError(
                f"recorded SUT needs reference '{self.reference_key}' in SUTContext"
            )
        # A context reference names a local JSON file (or inline JSON). When
        # the adapter is called directly, an inline manifest may carry the
        # response object/string itself under ``output``.
        if context and context.references and self.reference_key in context.references:
            record = _load_json_reference(value, self.reference_root)
        else:
            record = value
        raw_output = _raw_output(record)
        return GenerationOutput(
            raw_output=raw_output,
            trace=_trace(record, raw_output),
            usage=_usage(record),
        )


class RecognitionWorker(SUTAdapter):
    """Call the private document-recognition worker through its JSON contract."""

    reproducible = False

    def __init__(
        self,
        binding: SUTBinding,
        client: httpx.Client | None = None,
        max_retries: int = 3,
    ) -> None:
        if not binding.endpoint:
            raise ValueError("RecognitionWorker requires binding.endpoint")
        self.binding = binding
        self._client = client or httpx.Client(
            timeout=float(binding.params.get("timeout_seconds", 120))
        )
        self.max_retries = max(1, max_retries)
        self.document_key = str(binding.params.get("document_key", _DEFAULT_DOCUMENT_KEY))
        self.profile = str(binding.params.get("profile", _DEFAULT_PROFILE))

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            **auth_headers(self.binding.api_key_env),
            "Content-Type": "application/json",
        }
        last: Exception | None = None
        for _ in range(self.max_retries):
            try:
                response = self._client.post(self.binding.endpoint, json=payload, headers=headers)
                if response.status_code >= 500 or response.status_code == 429:
                    last = httpx.HTTPStatusError(
                        f"transient {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    continue
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code < 500
                    and exc.response.status_code != 429
                ):
                    raise
                last = exc
        raise last if last else RuntimeError("recognition request failed")

    @staticmethod
    def _response(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
        except ValueError as exc:
            raise ValueError("recognition worker returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("recognition worker returned a non-object JSON response")
        return value

    def generate(
        self, document: str, seed: int, context: SUTContext | None = None
    ) -> GenerationOutput:
        del seed  # The current worker contract has no sampling parameter.
        document_url = _reference(document, context, self.document_key)
        if not isinstance(document_url, str) or not document_url.strip():
            raise ValueError(
                f"recognition SUT needs document reference '{self.document_key}' in SUTContext"
            )
        payload: dict[str, Any] = {
            "document_url": document_url,
            "profile": self.profile,
        }
        for key in ("model_id", "model_revision"):
            value = self.binding.params.get(key)
            if value:
                payload[key] = str(value)

        response = self._post(payload)
        data = self._response(response)
        raw_output = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        trace_data = {
            key: data[key]
            for key in (
                "input_bytes",
                "page_count",
                "ocr_required",
                "ocr_used",
                "text_source",
            )
            if key in data
        }
        trace = Trace(
            steps=[Step(name="recognition", content=raw_output, data=trace_data)],
            final_output=raw_output,
        )
        return GenerationOutput(
            raw_output=raw_output,
            trace=trace,
            usage=TokenUsage.zero(),
        )


def protocol_for(binding: SUTBinding) -> str:
    """Return the explicit private protocol selected by an external SUT spec."""

    protocol = str(binding.params.get("protocol", "")).strip().lower()
    if protocol not in {"recorded", "recognition"}:
        raise NotImplementedError(
            "external_api requires binding.params.protocol 'recorded' or 'recognition'"
        )
    return protocol
