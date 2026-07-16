# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent SUTs: deterministic mocks, trace emission, and process rubrics.

The load-bearing test is right-answer-wrong-process: an agent that skips the
required tool but still reports the finding must pass the OUTPUT rubric and fail
the PROCESS rubric on the same generation.
"""

from pathlib import Path

from harness.agent.fake_agent import FakeAgent
from harness.agent.mocks import MockStore, tool_args_hash
from harness.execute import run_battery
from harness.packio.loader import load_pack
from harness.store.runstore import RunStore
from harness.sut.base import SUTContext

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-agent"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731


def _mock_store():
    return MockStore({
        "E001": {"molecular_lookup": {
            tool_args_hash({"case_id": "E001"}): {"result": "EGFR deletion", "error": None}
        }}
    })


def test_fake_agent_records_successful_tool_call():
    agent = FakeAgent("sys", "1", tools_to_call=["molecular_lookup"], mock_store=_mock_store())
    out = agent.generate("Note: EGFR present.", seed=1, context=SUTContext(case_id="E001"))
    names = [s.name for s in out.trace.steps]
    assert names == ["molecular_lookup"]
    assert out.trace.steps[0].data["result"] == "EGFR deletion"
    assert out.trace.steps[0].data["error"] is None


def test_fake_agent_missing_mock_is_recorded_as_error():
    agent = FakeAgent("sys", "1", tools_to_call=["ghost_tool"], mock_store=_mock_store())
    out = agent.generate("doc", seed=1, context=SUTContext(case_id="E001"))
    assert out.trace.steps[0].data["error"] is not None


def test_fake_agent_deterministic():
    agent = FakeAgent("sys", "1", tools_to_call=["molecular_lookup"], mock_store=_mock_store())
    ctx = SUTContext(case_id="E001")
    a = agent.generate("doc EGFR", seed=1, context=ctx)
    b = agent.generate("doc EGFR", seed=1, context=ctx)
    assert a.raw_output == b.raw_output
    assert [s.model_dump() for s in a.trace.steps] == [s.model_dump() for s in b.trace.steps]


def test_lazy_agent_output_echoes_finding_without_calling_tool():
    lazy = FakeAgent("sys", "1", tools_to_call=[], mock_store=_mock_store())
    out = lazy.generate("Note: EGFR exon 19 deletion.", seed=1, context=SUTContext(case_id="E001"))
    assert out.trace.steps == []
    assert "EGFR" in out.raw_output  # right answer, from the note


def test_right_answer_wrong_process(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    results = run_battery(pack, "agent", store, seed=1, now=CLOCK)
    by_sut = {r.sut_id: r for r in results}

    full = store.read_grades(by_sut["agent-full"].run_id)[0]
    lazy = store.read_grades(by_sut["agent-lazy"].run_id)[0]

    # both report the finding (output rubric passes)
    assert full.item_scores["item_reports_molecular"] == 1.0
    assert lazy.item_scores["item_reports_molecular"] == 1.0
    # only the full agent called the tool (process rubric)
    assert full.item_scores["item_used_molecular_tool"] == 1.0
    assert lazy.item_scores["item_used_molecular_tool"] == 0.0
    # the shortcut fails acceptance despite the right answer
    assert by_sut["agent-full"].report["acceptance"]["overall_pass"] is True
    assert by_sut["agent-lazy"].report["acceptance"]["overall_pass"] is False


def test_process_rubric_not_applicable_to_non_agent(tmp_path):
    # a trace-target rubric graded on a non-agent SUT is N/A, not a failure
    from harness.judge.fake import FakeJudge
    from harness.judge.grading import grade_generation
    from harness.models.results import Generation, TokenUsage

    pack = load_pack(PACK)
    case = pack.case("E001").model_copy(update={"elements": {"__document__": "EGFR"}})
    gen = Generation(case_id="E001", perturbation_id="p", sample_idx=0,
                     raw_output="EGFR present", trace={"steps": []},
                     usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2))
    grade = grade_generation(pack.rubric, gen, case, FakeJudge(), seed=1, sut_kind="llm_call")
    assert grade.item_status["item_used_molecular_tool"] == "not_applicable"
    assert "item_used_molecular_tool" not in grade.item_scores


def test_agent_trace_round_trips_through_store(tmp_path):
    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    results = run_battery(pack, "agent", store, seed=1, now=CLOCK)
    rid = results[0].run_id
    gens = store.read_generations(rid)
    # trace persisted and reloaded intact
    assert gens[0].trace["steps"] or gens[0].trace == {"steps": [], "final_output": gens[0].raw_output}
