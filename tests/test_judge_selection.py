# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-battery judge selection, and the pin that must name the real judge.

The engine's credibility claim is that the judge config is part of the run hash.
That only holds if the judge a run *pins* is the judge that actually graded it —
so the judge is resolved from pack content per battery, never supplied by a
caller at run time.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from validrig.execute import run_battery
from validrig.packio.loader import PackValidationError, load_pack
from validrig.store.runstore import RunStore

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"


def _pack_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "pack"
    shutil.copytree(PACK, dest)
    return dest


def _write_judges(pack_dir: Path, default_id: str, alternates: list[str]) -> None:
    doc: dict = {"id": default_id, "version": "1", "kind": "fake", "binding": {}}
    if alternates:
        doc["alternates"] = [
            {"id": a, "version": "1", "kind": "fake", "binding": {}} for a in alternates
        ]
    (pack_dir / "judge.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _set_battery_judge(pack_dir: Path, battery_id: str, judge_id: str | None) -> None:
    path = pack_dir / "battery.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    for battery in doc["batteries"]:
        if battery["id"] == battery_id:
            if judge_id is None:
                battery.pop("judge", None)
            else:
                battery["judge"] = judge_id
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_battery_without_a_judge_uses_the_pack_default(tmp_path):
    pack_dir = _pack_copy(tmp_path)
    _write_judges(pack_dir, "primary-judge", ["offline-judge"])
    pack = load_pack(pack_dir)
    assert pack.judge_for("smoke").id == "primary-judge"


def test_battery_selects_a_declared_alternate(tmp_path):
    pack_dir = _pack_copy(tmp_path)
    _write_judges(pack_dir, "primary-judge", ["offline-judge"])
    _set_battery_judge(pack_dir, "smoke", "offline-judge")
    pack = load_pack(pack_dir)
    assert pack.judge_for("smoke").id == "offline-judge"
    assert pack.judge_for("regression").id == "primary-judge"


def test_battery_may_name_the_default_judge_explicitly(tmp_path):
    pack_dir = _pack_copy(tmp_path)
    _write_judges(pack_dir, "primary-judge", ["offline-judge"])
    _set_battery_judge(pack_dir, "smoke", "primary-judge")
    pack = load_pack(pack_dir)
    assert pack.judge_for("smoke").id == "primary-judge"


def test_battery_naming_an_undeclared_judge_is_a_pack_error(tmp_path):
    pack_dir = _pack_copy(tmp_path)
    _write_judges(pack_dir, "primary-judge", ["offline-judge"])
    _set_battery_judge(pack_dir, "smoke", "no-such-judge")
    with pytest.raises(PackValidationError, match="unknown judge"):
        load_pack(pack_dir)


def test_duplicate_judge_ids_are_a_pack_error(tmp_path):
    pack_dir = _pack_copy(tmp_path)
    _write_judges(pack_dir, "primary-judge", ["primary-judge"])
    with pytest.raises(PackValidationError, match="duplicate judge id"):
        load_pack(pack_dir)


def test_run_pins_the_judge_the_battery_declares(tmp_path):
    pack_dir = _pack_copy(tmp_path)
    _write_judges(pack_dir, "primary-judge", ["offline-judge"])
    _set_battery_judge(pack_dir, "smoke", "offline-judge")
    pack = load_pack(pack_dir)

    store = RunStore(tmp_path / "runs")
    result = run_battery(pack, "smoke", store, seed=1)[0]
    run = store.read_run(result.run_id)
    assert run.pins.judge_id == "offline-judge"
    assert run.pins.judge_version == "1"


def test_changing_a_batterys_judge_changes_the_pack_hash(tmp_path):
    """A judge swap is a revalidation event: it must move the pack hash."""
    pack_dir = _pack_copy(tmp_path)
    _write_judges(pack_dir, "primary-judge", ["offline-judge"])
    before = load_pack(pack_dir).pack_hash
    _set_battery_judge(pack_dir, "smoke", "offline-judge")
    assert load_pack(pack_dir).pack_hash != before
