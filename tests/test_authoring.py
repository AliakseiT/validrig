# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pack authoring tooling: lint and scaffold."""

import shutil
from pathlib import Path

from harness.authoring.lint import lint_pack, has_errors
from harness.authoring.scaffold import scaffold_pack
from harness.execute import run_battery
from harness.packio.loader import load_pack
from harness.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"


def test_clean_pack_lints_without_errors():
    findings = lint_pack(load_pack(PACK))
    assert not has_errors(findings)


def test_blank_grading_instructions_flagged():
    # construct a rubric item with blank grading instructions directly
    pack = load_pack(PACK)
    from harness.models.pack import RubricItem, Rubric

    broken_item = RubricItem(
        id="item_broken", statement="a statement", type="binary",
        grading_instructions="   ", max_score=1.0,
    )
    broken = pack.model_copy(update={"rubric": Rubric(items=[broken_item])})
    findings = lint_pack(broken)
    codes = {f.code for f in findings}
    assert "rubric-item-no-grading-instructions" in codes
    assert has_errors(findings)
    assert any("item_broken" in f.message for f in findings)


def test_missing_critical_adjudication_flagged(tmp_path):
    dst = tmp_path / "pack"
    shutil.copytree(PACK, dst)
    (dst / "rubric" / "adjudication" / "C001.json").unlink()
    findings = lint_pack(load_pack(dst))
    msgs = [f.message for f in findings]
    # the missing case is flagged with its specific id
    assert any("C001" in m and "no physician adjudication" in m for m in msgs)


def test_scaffold_produces_a_pack_that_loads_and_runs(tmp_path):
    dest = tmp_path / "my-pack"
    scaffold_pack(dest, "my-pack")

    pack = load_pack(dest)  # loads clean
    assert pack.manifest.id == "my-pack"

    store = RunStore(tmp_path / "runs")
    results = run_battery(pack, "smoke", store, seed=1, now=lambda: "2026-07-16T00:00:00+00:00")
    assert len(results) == 1
    # a fresh scaffold passes its own baseline acceptance out of the box
    assert results[0].report["acceptance"]["overall_pass"] is True


def test_scaffolded_pack_lints_clean(tmp_path):
    dest = tmp_path / "my-pack"
    scaffold_pack(dest, "my-pack")
    assert not has_errors(lint_pack(load_pack(dest)))


def test_scaffold_refuses_nonempty_dir(tmp_path):
    dest = tmp_path / "occupied"
    dest.mkdir()
    (dest / "something").write_text("x")
    import pytest

    with pytest.raises(FileExistsError):
        scaffold_pack(dest, "occupied")
