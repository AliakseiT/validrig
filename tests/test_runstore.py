# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from validrig.models.results import (
    Generation,
    Grade,
    Pins,
    Run,
    RunMeta,
    TokenUsage,
    run_id_for,
)
from validrig.store.runstore import RunStore


def _run():
    pins = Pins(
        pack_id="p", pack_version="1", pack_hash="h", battery_id="b", battery_version="1",
        sut_id="s", sut_hash="sh", judge_id="j", judge_version="1", seed=7, engine_version="0.1.0",
    )
    return Run(pins=pins, meta=RunMeta(run_id=run_id_for(pins), timestamp="2026-07-16T00:00:00Z", env_hash="e"))


def _gens():
    return [
        Generation(case_id="C1", perturbation_id="ablation:none|format:structured", sample_idx=0,
                   raw_output="out", trace={"steps": []},
                   usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5, cost_chf=0.001)),
    ]


def _grades():
    return [
        Grade(case_id="C1", perturbation_id="ablation:none|format:structured", sample_idx=0,
              item_scores={"i1": 1.0}, judge_notes={"i1": "ok"}, human_agreement=None),
    ]


def test_round_trip_run(tmp_path):
    store = RunStore(tmp_path)
    run = _run()
    store.write_run(run)
    got = store.read_run(run.meta.run_id)
    assert got == run


def test_round_trip_generations_and_grades(tmp_path):
    store = RunStore(tmp_path)
    run = _run()
    store.write_run(run)
    store.write_generations(run.meta.run_id, _gens())
    store.write_grades(run.meta.run_id, _grades())
    assert store.read_generations(run.meta.run_id) == _gens()
    assert store.read_grades(run.meta.run_id) == _grades()


def test_append_only_refuses_overwrite(tmp_path):
    store = RunStore(tmp_path)
    run = _run()
    store.write_run(run)
    with pytest.raises(Exception):
        store.write_run(run)


def test_parquet_files_written(tmp_path):
    store = RunStore(tmp_path)
    run = _run()
    store.write_run(run)
    store.write_generations(run.meta.run_id, _gens())
    p = tmp_path / "runs" / run.meta.run_id / "generations.parquet"
    assert p.exists()


def test_list_runs(tmp_path):
    store = RunStore(tmp_path)
    run = _run()
    store.write_run(run)
    assert store.list_runs() == [run.meta.run_id]
