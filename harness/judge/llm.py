# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native G-Eval-style LLM judge.

Implements the G-Eval *method* — evaluate an output against a criterion, guided
by (optionally pinned) evaluation steps, via a form-filling structured score —
directly on the OpenAI-compatible transport the engine already speaks. No eval
*framework* is vendored: the judge is a prompt builder plus a tolerant JSON
parse, so it adds zero runtime dependencies and stays fully under the engine's
pinning and record/replay discipline.

Grades from this judge are ``reproducible = False``: endpoints are not guaranteed
deterministic, so a judge-graded run is recorded once and replayed from the
store — analysis and regression diffs read the recorded grades, never re-invoke
the judge.

Evaluation steps are only ever *pinned pack content*; this judge never generates
them at grade time, which would make grading depend on an unpinned artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from harness.judge.base import ItemGrade, Judge
from harness.models.pack import RubricItem
from harness.models.sut import SUTBinding
from harness.sut.auth import auth_headers


@dataclass(frozen=True)
class GradingConfig:
    #: Show the judge the source document the output should be grounded in.
    include_document: bool = True
    #: Show the judge the adjudicated reference. Default False: the deployed judge
    #: grades against the criterion, not the gold standard — which is also the
    #: basis judge–human calibration will measure. Opt in for debugging.
    include_reference: bool = False
    #: Optional pinned chain-of-thought steps, keyed by rubric item id.
    evaluation_steps: dict[str, list[str]] = field(default_factory=dict)
    system_prompt: str = (
        "You are a meticulous clinical evaluation judge. Follow the evaluation "
        "steps and grade strictly. Return only the requested JSON object."
    )


def _extract_json_object(text: str) -> dict:
    """Tolerantly extract the first JSON object from a model response.

    Endpoints differ wildly on structured output (native json_schema, markdown
    fences, or nothing), so we locate the first balanced ``{...}`` and parse it.
    Raises ValueError if none is parseable — the caller turns that into a
    ``judge_error``, never a score of 0.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in judge response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON object in judge response")


class LLMJudge(Judge):
    reproducible = False

    def __init__(
        self,
        binding: SUTBinding,
        grading: GradingConfig | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not binding.endpoint:
            raise ValueError("LLMJudge requires binding.endpoint")
        self.binding = binding
        self.grading = grading or GradingConfig()
        self._client = client or httpx.Client(timeout=60.0)

    def _build_prompt(
        self,
        item: RubricItem,
        document: str,
        output: str,
        ground_truth: dict,
    ) -> str:
        parts = [
            "# Evaluation criterion",
            item.statement.strip(),
            "",
            "# Grading instructions",
            item.grading_instructions.strip(),
        ]
        steps = self.grading.evaluation_steps.get(item.id)
        if steps:
            parts += ["", "# Evaluation steps"]
            parts += [f"{n}. {s}" for n, s in enumerate(steps, 1)]
        if self.grading.include_document and document:
            parts += ["", "# Source document (the output should be grounded in this)", document]
        if self.grading.include_reference:
            reference = ground_truth.get(item.id)
            if reference is not None:
                parts += ["", "# Adjudicated reference", json.dumps(reference, ensure_ascii=False)]
        parts += [
            "",
            "# System-under-test output to grade",
            output,
            "",
            "# Response format",
            (
                'Return ONLY a JSON object: {"score": <number between 0 and '
                f'{item.max_score}>, "reasoning": "<one or two sentences>"}}.'
            ),
            (
                f"This is a binary criterion: use {item.max_score} if fully met, 0 if not."
                if item.type == "binary"
                else f"Use the full range 0 to {item.max_score}."
            ),
        ]
        return "\n".join(parts)

    def _messages(self, prompt: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.grading.system_prompt},
            {"role": "user", "content": prompt},
        ]

    def grade_item(
        self,
        item: RubricItem,
        document: str,
        output: str,
        ground_truth: dict,
        seed: int,
        trace: dict | None = None,
    ) -> ItemGrade:
        # For process (trace-target) items, grade the serialized trace steps
        # instead of the final output.
        graded_content = output
        if item.target == "trace":
            steps = (trace or {}).get("steps", [])
            graded_content = "\n".join(
                f"- tool={s.get('name')} error={(s.get('data') or {}).get('error')}"
                for s in steps
            ) or "(no trace steps)"
        prompt = self._build_prompt(item, document, graded_content, ground_truth)
        payload = {
            "model": self.binding.model_id,
            "messages": self._messages(prompt),
            "temperature": 0,
            # `seed` is intentionally NOT sent by default: it is not portable
            # (e.g. Google's OpenAI-compatible endpoint rejects it with 400). A
            # provider that supports it can set it via the judge binding params.
            **self.binding.params,
        }
        try:
            response = self._client.post(
                self.binding.endpoint, json=payload,
                headers=auth_headers(self.binding.api_key_env),
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            return ItemGrade.error(f"judge endpoint error: {exc}")

        try:
            parsed = _extract_json_object(content)
            raw_score = float(parsed["score"])
            reasoning = str(parsed.get("reasoning", "")).strip()
        except (ValueError, KeyError, TypeError) as exc:
            return ItemGrade.error(f"unparseable judge response: {exc}")

        score = max(0.0, min(item.max_score, raw_score))
        if item.type == "binary":
            score = item.max_score if score >= item.max_score / 2.0 else 0.0
        return ItemGrade.graded(score, reasoning or "graded by LLM judge")
