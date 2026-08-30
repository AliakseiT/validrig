# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from pydantic import ValidationError

from validrig.models.results import (
    Generation,
    Grade,
    Pins,
    Run,
    RunMeta,
    TokenUsage,
    content_key,
    run_id_for,
)


def _pins(**over):
    base = dict(
        pack_id="p",
        pack_version="1.0.0",
        pack_hash="abc",
        battery_id="b",
        battery_version="1",
        sut_id="s",
        sut_hash="def",
        judge_id="j",
        judge_version="1",
        seed=7,
        engine_version="0.1.0",
    )
    base.update(over)
    return Pins(**base)


def test_token_usage_adds():
    assert TokenUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3) + TokenUsage(
        prompt_tokens=1, completion_tokens=1, total_tokens=2
    ) == TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5)


def test_token_usage_adds_cost():
    a = TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_chf=0.5)
    b = TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_chf=0.25)
    assert (a + b).cost_chf == pytest.approx(0.75)


def test_models_are_frozen():
    u = TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
    with pytest.raises(ValidationError):
        u.prompt_tokens = 9


def test_run_id_is_deterministic_and_timestamp_independent():
    p = _pins()
    assert run_id_for(p) == run_id_for(_pins())
    assert len(run_id_for(p)) == 16
    # a run's identity comes only from its pins, never from wall-clock time
    r1 = Run(pins=p, meta=RunMeta(run_id=run_id_for(p), timestamp="2020-01-01T00:00:00Z", env_hash="e"))
    r2 = Run(pins=p, meta=RunMeta(run_id=run_id_for(p), timestamp="2099-12-31T23:59:59Z", env_hash="e"))
    assert r1.meta.run_id == r2.meta.run_id


def test_run_id_changes_with_seed():
    assert run_id_for(_pins(seed=1)) != run_id_for(_pins(seed=2))


def test_generation_has_no_timestamp_field():
    g = Generation(
        case_id="c",
        perturbation_id="pt",
        sample_idx=0,
        raw_output="out",
        trace={},
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    assert "timestamp" not in type(g).model_fields
    assert content_key(g) == ("c", "pt", 0)


def test_grade_content_key():
    g = Grade(case_id="c", perturbation_id="pt", sample_idx=1, item_scores={"i1": 1.0}, judge_notes={})
    assert content_key(g) == ("c", "pt", 1)
    assert "timestamp" not in type(g).model_fields
