# SPDX-License-Identifier: AGPL-3.0-or-later
"""Path-traversal defenses for id-derived filesystem paths."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harness.authoring.adjudicate import adjudication_path
from harness.calibration.store import CalibrationStore
from harness.packio.loader import load_pack
from harness.pathsafe import confined_path, is_safe_id, require_safe_id
from harness.store.runstore import RunStore
from harness.ui.app import create_app

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"

_TRAVERSALS = ["../evil", "..%2f..%2fetc", "a/b", "..", ".", "x.json", "with space", ""]


@pytest.mark.parametrize("bad", _TRAVERSALS)
def test_unsafe_ids_rejected(bad):
    assert not is_safe_id(bad)
    with pytest.raises(ValueError):
        require_safe_id(bad, "id")


def test_safe_ids_accepted():
    for good in ["C001", "run_abc-123", "E001", "abcdef0123456789"]:
        assert is_safe_id(good)


def test_confined_path_blocks_escape(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(ValueError):
        confined_path(base, "..", "escape.json")


def test_adjudication_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        adjudication_path(tmp_path, "../../../etc/passwd")


def test_calibration_store_rejects_traversal(tmp_path):
    store = CalibrationStore(tmp_path)
    with pytest.raises(ValueError):
        store.read_human_grades("../../evil")


def test_runstore_rejects_traversal(tmp_path):
    store = RunStore(tmp_path)
    with pytest.raises(ValueError):
        store.read_generations("../../evil")


def test_ui_rejects_traversal_case_id(tmp_path):
    pack_dir = tmp_path / "pack"
    shutil.copytree(PACK, pack_dir)
    pack = load_pack(pack_dir)
    app = create_app(pack, RunStore(tmp_path / "r"), CalibrationStore(tmp_path / "r"),
                     grader_id="x", pack_dir=pack_dir)
    client = TestClient(app)
    # encoded-slash traversal is refused (router 404s before the handler); a
    # single-segment unsafe id (dot) is refused by the guard (400). Neither writes.
    assert client.post("/adjudicate/..%2f..%2fevil",
                       data={"score__item_diagnosis": "1.0"}).status_code in (400, 404)
    assert client.post("/adjudicate/bad.id",
                       data={"score__item_diagnosis": "1.0"}).status_code == 400
    assert not (tmp_path / "evil.json").exists()
    assert not (pack_dir / "rubric" / "adjudication" / "bad.id.json").exists()


def test_ui_rejects_traversal_run_id(tmp_path):
    pack = load_pack(PACK)
    app = create_app(pack, RunStore(tmp_path / "r"), CalibrationStore(tmp_path / "r"), grader_id="x")
    client = TestClient(app)
    assert client.get("/agreement/..%2f..%2fevil").status_code in (400, 404)
    assert client.get("/agreement/bad.id").status_code == 400  # guard fires
