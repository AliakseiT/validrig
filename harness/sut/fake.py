# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic fake model — a first-class SUT adapter.

The fake model makes the whole pipeline runnable and testable offline, and makes
the determinism guarantee something we can actually assert on. It is a pure
function of ``(document, system_prompt, seed)``: no network, no clock, no RNG
state.

It is deliberately generic — it contains no use-case knowledge. It produces a
structured-summary-shaped output that echoes the salient content of the input,
so any evidence present in the document survives into the output (baseline scores
well) and disappears when an element is ablated (score drops, revealing that
element's information value).
"""

from __future__ import annotations

from harness.hashing import content_hash
from harness.models.results import TokenUsage
from harness.models.sut import Step, Trace
from harness.sut.base import GenerationOutput, SUTAdapter

# Deterministic synthetic price, in CHF per 1k tokens, so the cost meter reports
# a stable non-zero number for the fake model.
_COST_PER_1K_TOKENS_CHF = 0.001


def _word_count(text: str) -> int:
    return len(text.split())


def _salient_lines(document: str) -> list[str]:
    """Non-empty, de-noised lines from the document, in order.

    Generic: keeps any line that carries content. This is what preserves
    evidence tokens into the output without the model knowing what they mean.
    """
    lines = []
    for raw in document.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Drop pure structural markers from the tabular renderer.
        if set(line) <= {"|", "-", " "}:
            continue
        lines.append(line)
    return lines


class FakeModel(SUTAdapter):
    reproducible = True

    def __init__(
        self,
        system_prompt: str | None,
        model_version: str,
        suppress: list[str] | None = None,
    ) -> None:
        self.system_prompt = system_prompt or ""
        self.model_version = model_version
        # Optional list of substrings; any finding line containing one is
        # dropped from the output. This lets a pack configure a deliberately
        # degraded model (e.g. one that "stopped reporting molecular findings")
        # for regression testing — the tokens are pack content, not engine logic.
        self.suppress = [s.lower() for s in (suppress or [])]

    def _keep(self, line: str) -> bool:
        low = line.lower()
        return not any(marker in low for marker in self.suppress)

    def generate(self, document: str, seed: int) -> GenerationOutput:
        signature = content_hash((document, self.system_prompt, seed, tuple(self.suppress)))[:12]
        findings = [line for line in _salient_lines(document) if self._keep(line)]
        body = "\n".join(f"- {line}" for line in findings)
        raw_output = (
            "STRUCTURED SUMMARY (synthetic model output)\n"
            f"[model_version={self.model_version} sig={signature}]\n"
            "FINDINGS:\n"
            f"{body}\n"
        )

        prompt_tokens = _word_count(self.system_prompt) + _word_count(document)
        completion_tokens = _word_count(raw_output)
        total = prompt_tokens + completion_tokens
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_chf=round(total / 1000.0 * _COST_PER_1K_TOKENS_CHF, 6),
        )

        trace = Trace(
            steps=[Step(name="generate", content=raw_output, data={"sig": signature})],
            final_output=raw_output,
        )
        return GenerationOutput(raw_output=raw_output, trace=trace, usage=usage)
