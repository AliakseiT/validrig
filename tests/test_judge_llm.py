# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native G-Eval LLM judge, exercised fully offline via a mocked transport."""

import json
import shutil
from pathlib import Path

import httpx

from validrig.judge.llm import GradingConfig, LLMJudge
from validrig.models.pack import RubricItem
from validrig.models.sut import SUTBinding

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"


def _binding():
    return SUTBinding(
        model_id="judge-x",
        model_version="1",
        endpoint="https://judge.invalid/v1/chat/completions",
        params={},
    )


def _item(item_type="binary", max_score=1.0):
    return RubricItem(
        id="item_molecular",
        statement="reports the molecular alteration",
        type=item_type,
        grading_instructions="score if the alteration is named",
        max_score=max_score,
    )


def _judge_returning(content, capture=None, counter=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture["body"] = json.loads(request.content.decode())
        if counter is not None:
            counter["n"] += 1
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMJudge(_binding(), GradingConfig(), client=client)


def test_binary_pass_maps_to_max_score():
    j = _judge_returning('{"score": 1, "reasoning": "EGFR named"}')
    g = j.grade_item(_item(), "doc", "the EGFR deletion", {}, seed=0)
    assert g.status == "graded"
    assert g.score == 1.0
    assert "EGFR named" in g.note


def test_binary_fail_maps_to_zero():
    j = _judge_returning('{"score": 0, "reasoning": "absent"}')
    g = j.grade_item(_item(), "doc", "nothing here", {}, seed=0)
    assert g.score == 0.0
    assert g.status == "graded"


def test_graded_score_is_clamped():
    j = _judge_returning('{"score": 9, "reasoning": "over-range"}')
    g = j.grade_item(_item(item_type="graded", max_score=1.0), "doc", "x", {}, seed=0)
    assert g.score == 1.0  # clamped to max_score


def test_markdown_fenced_json_is_parsed():
    j = _judge_returning('```json\n{"score": 1, "reasoning": "ok"}\n```')
    g = j.grade_item(_item(), "doc", "EGFR", {}, seed=0)
    assert g.score == 1.0


def test_unparseable_response_is_judge_error_not_zero():
    j = _judge_returning("I could not produce JSON, sorry.")
    g = j.grade_item(_item(), "doc", "EGFR", {}, seed=0)
    assert g.status == "judge_error"
    assert g.score is None  # crucially NOT 0.0


def test_endpoint_error_is_judge_error():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    j = LLMJudge(_binding(), GradingConfig(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    g = j.grade_item(_item(), "doc", "EGFR", {}, seed=0)
    assert g.status == "judge_error"
    assert g.score is None


def test_reproducible_flag_is_false():
    j = _judge_returning('{"score": 1, "reasoning": "x"}')
    assert j.reproducible is False


def test_reference_free_by_default_but_optin_includes_reference():
    cap = {}
    j = _judge_returning('{"score": 1, "reasoning": "x"}', capture=cap)
    j.grade_item(_item(), "doc", "out", {"item_molecular": {"evidence": ["EGFR"]}}, seed=0)
    prompt_default = cap["body"]["messages"][1]["content"]
    assert "Adjudicated reference" not in prompt_default

    def handler(request):
        cap["body2"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"score":1,"reasoning":"x"}'}}]})

    j2 = LLMJudge(
        _binding(),
        GradingConfig(include_reference=True),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    j2.grade_item(_item(), "doc", "out", {"item_molecular": {"evidence": ["EGFR"]}}, seed=0)
    assert "Adjudicated reference" in cap["body2"]["messages"][1]["content"]


def test_judge_called_once_then_replayed_from_store(tmp_path):
    """The LLM judge is invoked once during the run; analysis and re-reads use
    the recorded grades and never re-invoke it (record-once / replay)."""
    from validrig.execute import run_battery
    from validrig.packio.loader import load_pack
    from validrig.store.runstore import RunStore

    counter = {"n": 0}
    judge = _judge_returning('{"score": 1, "reasoning": "ok"}', counter=counter)

    pack = load_pack(PACK)
    store = RunStore(tmp_path)
    res = run_battery(
        pack, "smoke", store, seed=1,
        now=lambda: "2026-07-16T00:00:00+00:00", judge=judge,
    )[0]

    # 45 units x 3 rubric items = 135 judge calls, exactly once each.
    assert counter["n"] == 135
    calls_after_run = counter["n"]

    # Re-reading grades and computing a diff must not re-invoke the judge.
    grades = store.read_grades(res.run_id)
    assert len(grades) == 45
    assert all(g.item_status == {} for g in grades)  # all graded, no errors
    assert counter["n"] == calls_after_run


def test_judge_change_is_a_revalidation_event(tmp_path):
    """Changing the judge config changes pack_hash -> run_id, with no extra
    machinery — proving a judge upgrade is a diffable revalidation event."""
    from validrig.models.results import Pins, run_id_for
    from validrig.packio.loader import load_pack

    dst = tmp_path / "pack"
    shutil.copytree(PACK, dst)
    hash_a = load_pack(dst).pack_hash

    judge_yaml = (dst / "judge.yaml").read_text()
    (dst / "judge.yaml").write_text(judge_yaml.replace('version: "1"', 'version: "2"'))
    hash_b = load_pack(dst).pack_hash

    assert hash_a != hash_b

    def _pins(pack_hash, judge_version):
        return Pins(
            pack_id="p", pack_version="1", pack_hash=pack_hash, battery_id="b",
            battery_version="1", sut_id="s", sut_hash="sh", judge_id="j",
            judge_version=judge_version, seed=1, engine_version="0.1.0",
        )

    assert run_id_for(_pins(hash_a, "1")) != run_id_for(_pins(hash_b, "2"))
