# SPDX-License-Identifier: AGPL-3.0-or-later
"""`rig publish` — site-ready content from pinned runs.

Guarantees under test:
* authored prose comes from publish.yaml; every number in it resolves through a
  {{fact}} placeholder backed by run artifacts — unknown/null facts are errors;
* the emitted object embeds the real dossier (fragment) with run hash + engine
  version;
* the TS module is data-only with a generated header naming its source runs;
* adding publish.yaml to a pack directory does NOT change the pack hash;
* publishing from a drifted pack (hash mismatch vs the run's pins) is refused.
"""

import json
import shutil
from pathlib import Path

import pytest

from validrig.cli import main
from validrig.execute import run_battery
from validrig.packio.loader import load_pack
from validrig.publish import (
    FactError,
    build_facts,
    build_pipeline_content,
    emit_ts,
    load_publish_spec,
    resolve_placeholders,
)
from validrig.store.runstore import RunStore
from validrig.version import ENGINE_VERSION

REPO = Path(__file__).resolve().parent.parent
PACK = REPO / "packs" / "demo-tumor-board"
CLOCK = lambda: "2026-07-16T00:00:00+00:00"  # noqa: E731

SPEC_YAML = """\
slug: demo-board
title: Demo board preparation
summary: "Mean score {{run.%(run)s.mean_score|.2f}} on the demo pack."
data_note: Synthetic demonstration cases; no patient data.
report_title: Validation dossier — demo
arc:
  task: "<p>Summarize the record.</p>"
  risks: "<p>Confident answers on missing evidence.</p>"
  measurement: "<p>Perturbation grid over {{pack.n_cases}} cases.</p>"
  findings: >-
    <p>pathology_report information value
    {{run.%(run)s.element.pathology_report.information_value|.3f}},
    acceptance {{run.%(run)s.acceptance.mean_score.result}} on `code`
    with a ${dollar} brace.</p>
  meaning: "<p>Re-run on every model change.</p>"
"""


@pytest.fixture(scope="module")
def store_and_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("publish-store")
    pack = load_pack(PACK)
    store = RunStore(tmp)
    results = run_battery(pack, "regression", store, seed=1, now=CLOCK)
    return pack, store, [r.run_id for r in results]


def _spec_file(tmp_path: Path, run_id: str, extra: str = "") -> Path:
    p = tmp_path / "publish.yaml"
    p.write_text(SPEC_YAML % {"run": run_id} + extra, encoding="utf-8")
    return p


# ---- facts ------------------------------------------------------------------


def test_facts_come_from_run_artifacts(store_and_run):
    pack, store, run_ids = store_and_run
    facts = build_facts(pack, store, run_ids[:1])
    rid = run_ids[0]
    contract = store.read_contract(rid)
    report = store.read_report(rid)
    assert facts["engine.version"] == ENGINE_VERSION
    assert facts["pack.hash"] == pack.pack_hash
    assert facts[f"run.{rid}.sut"] == "fake-baseline"
    assert facts[f"run.{rid}.mean_score"] == report["summary"]["mean_score"]["mean"]
    iv = next(e for e in contract["elements"] if e["name"] == "pathology_report")
    assert facts[f"run.{rid}.element.pathology_report.information_value"] == iv["information_value"]
    assert facts[f"run.{rid}.date"] == "2026-07-16"


def test_diff_facts_are_recomputed_from_grades(store_and_run):
    pack, store, run_ids = store_and_run
    from validrig.publish.spec import DiffSpec

    facts = build_facts(
        pack, store, run_ids,
        diffs={"swap": DiffSpec(baseline=run_ids[0], candidate=run_ids[1])},
    )
    assert "diff.swap.delta" in facts
    assert facts["diff.swap.baseline_sut"] == "fake-baseline"
    assert facts["diff.swap.candidate_sut"] == "fake-regressed"
    assert facts["diff.swap.significant"] in ("yes", "no")


def test_fact_files_are_flattened(store_and_run, tmp_path):
    pack, store, run_ids = store_and_run
    (tmp_path / "extra.json").write_text(
        json.dumps({"baseline": {"overall_recall": 0.8571428}, "n": [1, 2]}),
        encoding="utf-8",
    )
    facts = build_facts(pack, store, run_ids[:1], fact_files={"deid": tmp_path / "extra.json"})
    assert facts["file.deid.baseline.overall_recall"] == 0.8571428
    assert facts["file.deid.n.1"] == 2
    assert resolve_placeholders("{{file.deid.baseline.overall_recall|.0%}}", facts) == "86%"


def test_placeholders_resolve_with_format_specs():
    facts = {"a.b": 0.208333, "s": "PASS"}
    assert resolve_placeholders("iv {{a.b|.3f}} is {{s}}", facts) == "iv 0.208 is PASS"


def test_unknown_fact_is_an_error():
    with pytest.raises(FactError, match="unknown fact"):
        resolve_placeholders("{{no.such.key}}", {"a": 1})


def test_null_fact_refuses_to_publish():
    with pytest.raises(FactError, match="null"):
        resolve_placeholders("{{a}}", {"a": None})


# ---- spec -------------------------------------------------------------------


def test_missing_spec_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="publish.yaml"):
        load_publish_spec(tmp_path / "publish.yaml")


def test_spec_rejects_unknown_fields(tmp_path):
    p = tmp_path / "publish.yaml"
    p.write_text(SPEC_YAML % {"run": "x"} + "\nbogus_field: 1\n", encoding="utf-8")
    with pytest.raises(Exception, match="bogus_field"):
        load_publish_spec(p)


def test_publish_yaml_in_pack_dir_does_not_change_pack_hash(tmp_path):
    packdir = tmp_path / "pack"
    shutil.copytree(PACK, packdir)
    before = load_pack(packdir).pack_hash
    (packdir / "publish.yaml").write_text("slug: anything\n", encoding="utf-8")
    after = load_pack(packdir).pack_hash
    assert before == after == load_pack(PACK).pack_hash


# ---- content assembly ---------------------------------------------------------


def test_pipeline_content_matches_interface_and_embeds_dossier(store_and_run, tmp_path):
    pack, store, run_ids = store_and_run
    rid = run_ids[0]
    spec = load_publish_spec(_spec_file(tmp_path, rid))
    content, meta = build_pipeline_content(pack, store, [rid], spec, tmp_path)

    assert set(content) == {"slug", "title", "summary", "dataNote", "arc", "report"}
    assert set(content["arc"]) == {"task", "risks", "measurement", "findings", "meaning"}
    assert set(content["report"]) == {"title", "runHash", "generatedDate", "bodyHtml"}
    # machine numbers were substituted, not hand-typed
    assert "{{" not in json.dumps(content)
    iv = store.read_contract(rid)["elements"][0]
    assert content["report"]["runHash"] == rid
    assert content["report"]["generatedDate"] == CLOCK()
    body = content["report"]["bodyHtml"]
    # real dossier fragment: run hash prefix, engine version, sections, no doc skeleton
    assert f"validrig {ENGINE_VERSION}" in body
    assert rid in body  # pinned-inputs hash starts with the run id
    assert "1. Validation summary" in body and "5. Attestation" in body
    assert "<html" not in body and "<style" not in body
    assert meta["export_name"] == "demoBoard"
    assert meta["run_suts"][rid] == "fake-baseline"


def test_publish_refuses_pack_drift(store_and_run, tmp_path):
    pack, store, run_ids = store_and_run
    rid = run_ids[0]
    packdir = tmp_path / "drifted"
    shutil.copytree(PACK, packdir)
    manifest = packdir / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace('version: "0.1.0"', 'version: "0.2.0"'),
        encoding="utf-8",
    )
    drifted = load_pack(packdir)
    spec = load_publish_spec(_spec_file(tmp_path, rid))
    with pytest.raises(ValueError, match="pack_hash"):
        build_pipeline_content(drifted, store, [rid], spec, tmp_path)
    # explicit override still works
    content, _ = build_pipeline_content(
        drifted, store, [rid], spec, tmp_path, allow_pack_drift=True
    )
    assert content["slug"] == "demo-board"


# ---- emission -----------------------------------------------------------------


def test_ts_module_is_data_only_with_provenance_header(store_and_run, tmp_path):
    pack, store, run_ids = store_and_run
    rid = run_ids[0]
    spec = load_publish_spec(_spec_file(tmp_path, rid))
    content, meta = build_pipeline_content(pack, store, [rid], spec, tmp_path)
    ts = emit_ts(content, meta, "2026-07-16T00:00:00+00:00")

    assert ts.startswith("// GENERATED by `rig publish`")
    assert "do not grow logic here" in ts
    assert f"// engine:    validrig {ENGINE_VERSION}" in ts
    assert f"//   run {rid} (sut: fake-baseline)" in ts
    assert "import type { PipelineContent } from './types';" in ts
    assert "export const demoBoard: PipelineContent =" in ts
    # template-literal escaping: authored backtick and ${ survive as literals
    assert "\\`code\\`" in ts
    assert "\\${dollar}" in ts
    # data-only: no functions, no logic
    assert "=>" not in ts and "function" not in ts


def test_cli_publish_writes_ts_and_json(store_and_run, tmp_path):
    pack, store, run_ids = store_and_run
    rid = run_ids[0]
    spec_path = _spec_file(tmp_path, rid)
    out_ts = tmp_path / "out" / "demo-board.ts"
    rc = main([
        "publish", str(PACK), "--runs", str(store.root), "--run", rid,
        "--spec", str(spec_path), "--format", "ts", "--out", str(out_ts),
    ])
    assert rc == 0
    text = out_ts.read_text(encoding="utf-8")
    assert "export const demoBoard: PipelineContent =" in text

    out_json = tmp_path / "out" / "demo-board.json"
    rc = main([
        "publish", str(PACK), "--runs", str(store.root), "--run", rid,
        "--spec", str(spec_path), "--format", "json", "--out", str(out_json),
        "--slug", "renamed", "--title", "Renamed title",
    ])
    assert rc == 0
    doc = json.loads(out_json.read_text(encoding="utf-8"))
    assert doc["slug"] == "renamed"
    assert doc["title"] == "Renamed title"
    assert doc["report"]["runHash"] == rid
