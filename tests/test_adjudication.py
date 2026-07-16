# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adjudication ingestion: the physician gold layer, with referential integrity."""

import json
import shutil
from pathlib import Path

import pytest

from harness.packio.loader import PackValidationError, load_pack

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"


def test_adjudications_load():
    pack = load_pack(PACK)
    assert len(pack.adjudications) == 3
    a = pack.adjudication("C001")
    assert a is not None
    assert a.adjudicated_by == "synthetic-panel"
    assert a.values["item_diagnosis"] == 1.0


def test_missing_adjudication_is_absent_not_zero(tmp_path):
    dst = tmp_path / "pack"
    shutil.copytree(PACK, dst)
    (dst / "rubric" / "adjudication" / "C001.json").unlink()
    pack = load_pack(dst)
    assert pack.adjudication("C001") is None  # absent, not a zero-valued record
    assert len(pack.adjudications) == 2


def test_adjudication_for_unknown_case_raises(tmp_path):
    dst = tmp_path / "pack"
    shutil.copytree(PACK, dst)
    (dst / "rubric" / "adjudication" / "GHOST.json").write_text(
        json.dumps({"case_id": "GHOST", "adjudicated_by": "x", "adjudicated_at": "2026",
                    "values": {"item_diagnosis": 1.0}})
    )
    with pytest.raises(PackValidationError, match="unknown case_id"):
        load_pack(dst)


def test_adjudication_for_unknown_item_raises(tmp_path):
    dst = tmp_path / "pack"
    shutil.copytree(PACK, dst)
    bad = json.loads((dst / "rubric" / "adjudication" / "C001.json").read_text())
    bad["values"]["item_nonexistent"] = 1.0
    (dst / "rubric" / "adjudication" / "C001.json").write_text(json.dumps(bad))
    with pytest.raises(PackValidationError, match="unknown rubric item"):
        load_pack(dst)


def test_changing_adjudication_changes_pack_hash(tmp_path):
    dst = tmp_path / "pack"
    shutil.copytree(PACK, dst)
    hash_a = load_pack(dst).pack_hash
    adj = json.loads((dst / "rubric" / "adjudication" / "C001.json").read_text())
    adj["values"]["item_diagnosis"] = 0.0
    (dst / "rubric" / "adjudication" / "C001.json").write_text(json.dumps(adj))
    hash_b = load_pack(dst).pack_hash
    assert hash_a != hash_b  # gold is pack content: a change is visible in the hash
