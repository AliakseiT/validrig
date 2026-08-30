# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic fake tool-using agent.

The offline, reproducible implementation of the agent trace protocol — the agent
analog of the fake model. It "calls" a configured set of tools (looked up in the
mock store), records each as a trace step (with the tool result or an error), and
produces an output that echoes the salient document content.

Crucially, the output echoes the document regardless of which tools were called —
so an agent configured to skip a tool still surfaces the finding in its output.
That is what makes the process-vs-output distinction testable: a right answer via
the wrong process passes the output rubric but fails the process rubric.
"""

from __future__ import annotations

from validrig.agent.mocks import MockStore, tool_args_hash
from validrig.hashing import content_hash
from validrig.models.results import TokenUsage
from validrig.models.sut import Step, Trace
from validrig.sut.base import GenerationOutput, SUTAdapter, SUTContext
from validrig.sut.fake import _salient_lines

_COST_PER_1K_TOKENS_CHF = 0.001


class FakeAgent(SUTAdapter):
    reproducible = True

    def __init__(
        self,
        system_prompt: str | None,
        model_version: str,
        tools_to_call: list[str],
        mock_store: MockStore,
    ) -> None:
        self.system_prompt = system_prompt or ""
        self.model_version = model_version
        self.tools_to_call = list(tools_to_call)
        self.mock_store = mock_store

    def generate(
        self, document: str, seed: int, context: SUTContext | None = None
    ) -> GenerationOutput:
        case_id = context.case_id if context is not None else ""
        perturbation = (context.tool_perturbation if context is not None else None) or {}
        unavailable = set(perturbation.get("unavailable", []))
        response_pert = perturbation.get("response") or {}

        steps: list[Step] = []
        for tool in self.tools_to_call:
            args = {"case_id": case_id}
            args_hash = tool_args_hash(args)
            base = {"args": args, "args_hash": args_hash}

            if tool in unavailable:
                # tool-availability perturbation: the tool is gone.
                steps.append(Step(name=tool, content="", data={
                    **base, "result": None, "error": "tool unavailable (perturbation)"}))
                continue

            if response_pert.get("tool") == tool and response_pert.get("mode") not in (None, "normal"):
                # tool-response perturbation: degrade this tool's response.
                mode = response_pert["mode"]
                if mode == "error":
                    steps.append(Step(name=tool, content="", data={
                        **base, "result": None, "error": "tool error (perturbation)"}))
                else:  # "empty"
                    steps.append(Step(name=tool, content="", data={
                        **base, "result": "", "error": None}))
                continue

            mock = self.mock_store.get(case_id, tool, args)
            if mock is None:
                steps.append(Step(name=tool, content="", data={
                    **base, "result": None, "error": "no mock recorded for this tool call"}))
            else:
                steps.append(Step(name=tool, content=str(mock.get("result", "")), data={
                    **base, "result": mock.get("result"), "error": mock.get("error")}))

        # Output echoes the salient document content — findings are present
        # whether or not the corresponding tool was actually called.
        findings = _salient_lines(document)
        signature = content_hash((document, self.system_prompt, seed, tuple(self.tools_to_call)))[:12]
        body = "\n".join(f"- {line}" for line in findings)
        raw_output = (
            "AGENT BRIEF (synthetic agent output)\n"
            f"[model_version={self.model_version} sig={signature} "
            f"tools_called={','.join(self.tools_to_call) or 'none'}]\n"
            "FINDINGS:\n"
            f"{body}\n"
        )

        prompt_tokens = len(self.system_prompt.split()) + len(document.split())
        completion_tokens = len(raw_output.split())
        total = prompt_tokens + completion_tokens
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_chf=round(total / 1000.0 * _COST_PER_1K_TOKENS_CHF, 6),
        )
        trace = Trace(steps=steps, final_output=raw_output)
        return GenerationOutput(raw_output=raw_output, trace=trace, usage=usage)
