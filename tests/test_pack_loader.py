# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest

from harness.packio.loader import PackValidationError, load_pack

PACK = Path(__file__).resolve().parent.parent / "packs" / "hello-tumor-board"


def test_loads_demo_pack():
    pack = load_pack(PACK)
    assert pack.manifest.id == "hello-tumor-board"
    assert len(pack.cases) == 3
    assert len(pack.rubric.items) >= 3
    assert any(i.critical for i in pack.rubric.items)
    assert len(pack.suts) == 1
    assert pack.suts[0].sut_hash  # hash computed on load
    assert pack.battery("smoke") is not None


def test_pack_hash_is_stable_across_loads():
    a = load_pack(PACK)
    b = load_pack(PACK)
    assert a.pack_hash == b.pack_hash
    assert len(a.pack_hash) == 64


def test_malformed_pack_raises(tmp_path):
    (tmp_path / "manifest.yaml").write_text("id: broken\n")  # missing required fields
    with pytest.raises(PackValidationError):
        load_pack(tmp_path)


def test_cases_carry_ground_truth():
    pack = load_pack(PACK)
    c1 = pack.case("C001")
    assert c1 is not None
    assert "item_diagnosis" in c1.ground_truth
    assert "EGFR" in c1.ground_truth["item_molecular"]["evidence"]
