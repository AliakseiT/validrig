# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent perturbation axes: tool-availability ablation and tool-response degradation."""

from pathlib import Path

from harness.agent.fake_agent import FakeAgent
from harness.agent.mocks import MockStore, tool_args_hash
from harness.execute import run_battery
from harness.models.pack import Case, CaseSchema, ElementSpec
from harness.packio.loader import load_pack
from harness.perturb.tools import ToolAvailabilityTransformer, ToolResponseTransformer
from harness.store.runstore import RunStore
from harness.sut.base import SUTContext

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-agent"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _case():
    return Case(case_id="E001", elements={"encounter": "EGFR present"}, ground_truth={})


def _schema():
    return CaseSchema(elements=[ElementSpec(name="encounter", type="text", modality="m", language="en")])


def test_tool_availability_records_removed_leaves_case_unchanged():
    pc = ToolAvailabilityTransformer().expand(_case(), _schema(), {"remove": ["molecular_lookup"]})[0]
    assert pc.provenance == {"axis": "tool_availability", "removed": ["molecular_lookup"]}
    assert pc.perturbation_id == "tool_availability:molecular_lookup"
    assert pc.case.elements == _case().elements  # document untouched


def test_tool_response_modes():
    normal = ToolResponseTransformer().expand(_case(), _schema(), {"mode": "normal"})[0]
    assert normal.perturbation_id == "tool_response:normal"
    err = ToolResponseTransformer().expand(_case(), _schema(), {"tool": "molecular_lookup", "mode": "error"})[0]
    assert err.provenance == {"axis": "tool_response", "tool": "molecular_lookup", "mode": "error"}
    assert err.perturbation_id == "tool_response:error:molecular_lookup"


def _agent():
    store = MockStore({"E001": {"molecular_lookup": {
        tool_args_hash({"case_id": "E001"}): {"result": "EGFR deletion", "error": None}}}})
    return FakeAgent("sys", "1", tools_to_call=["molecular_lookup"], mock_store=store)


def test_unavailable_tool_recorded_as_error():
    out = _agent().generate("EGFR", seed=1, context=SUTContext(
        case_id="E001", tool_perturbation={"unavailable": ["molecular_lookup"], "response": None}))
    assert out.trace.steps[0].data["error"] == "tool unavailable (perturbation)"


def test_tool_response_error_recorded():
    out = _agent().generate("EGFR", seed=1, context=SUTContext(
        case_id="E001", tool_perturbation={"unavailable": [], "response": {"tool": "molecular_lookup", "mode": "error"}}))
    assert out.trace.steps[0].data["error"] == "tool error (perturbation)"


def test_tool_response_empty_recorded():
    out = _agent().generate("EGFR", seed=1, context=SUTContext(
        case_id="E001", tool_perturbation={"unavailable": [], "response": {"tool": "molecular_lookup", "mode": "empty"}}))
    assert out.trace.steps[0].data["result"] == ""
    assert out.trace.steps[0].data["error"] is None


def test_no_perturbation_uses_mock():
    out = _agent().generate("EGFR", seed=1, context=SUTContext(case_id="E001"))
    assert out.trace.steps[0].data["result"] == "EGFR deletion"


def test_robustness_battery_process_fails_without_tool_output_survives(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    run_battery(pack, "agent_robustness", store, seed=1, now=CLOCK)
    rid = store.list_runs()[0]
    by_pert = {g.perturbation_id: g for g in store.read_grades(rid)}

    baseline = by_pert["tool_availability:all|tool_response:normal|format:structured"]
    removed = by_pert["tool_availability:molecular_lookup|tool_response:normal|format:structured"]

    # with the tool available, the process rubric passes
    assert baseline.item_scores["item_used_molecular_tool"] == 1.0
    # remove the tool: process FAILS, but output still passes (compensates from the
    # note rather than hallucinating) — the axis surfaces the degradation
    assert removed.item_scores["item_used_molecular_tool"] == 0.0
    assert removed.item_scores["item_reports_molecular"] == 1.0
