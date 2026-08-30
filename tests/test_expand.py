# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import validrig.perturb  # noqa: F401  (registers axes)
from validrig.packio.loader import load_pack
from validrig.perturb.expand import expand_battery

PACK = Path(__file__).resolve().parent.parent / "packs" / "demo-tumor-board"


def test_expands_to_expected_count():
    pack = load_pack(PACK)
    units = expand_battery(pack, pack.battery("smoke"))
    # 3 cases x 5 ablation levels x 3 format levels x 1 sut x 1 sample
    assert len(units) == 45


def test_no_duplicate_units():
    pack = load_pack(PACK)
    units = expand_battery(pack, pack.battery("smoke"))
    keys = {(u.case_id, u.perturbation_id, u.sample_idx, u.sut_id) for u in units}
    assert len(keys) == len(units)


def test_every_unit_has_a_document():
    pack = load_pack(PACK)
    units = expand_battery(pack, pack.battery("smoke"))
    assert all(u.document.strip() for u in units)


def test_expansion_is_deterministic():
    pack = load_pack(PACK)
    a = [u.perturbation_id for u in expand_battery(pack, pack.battery("smoke"))]
    b = [u.perturbation_id for u in expand_battery(pack, pack.battery("smoke"))]
    assert a == b


def test_ablation_provenance_is_recorded():
    pack = load_pack(PACK)
    units = expand_battery(pack, pack.battery("smoke"))
    dropped_seen = {
        tuple(u.provenance["ablation"]["dropped"]) for u in units if "ablation" in u.provenance
    }
    assert ("molecular_report",) in dropped_seen
    assert () in dropped_seen  # baseline


def test_battery_axis_scoping_bounds_expansion():
    pack = load_pack(PACK)
    # smoke restricts to ablation+format, so the language axis never enters it
    smoke_units = expand_battery(pack, pack.battery("smoke"))
    assert all("language" not in u.perturbation_id for u in smoke_units)
    # multilingual restricts to language+format for one case: 2 langs x 3 formats
    ml_units = expand_battery(pack, pack.battery("multilingual"))
    assert len(ml_units) == 6
    assert all(u.case_id == "C001" for u in ml_units)
    assert all("language" in u.perturbation_id for u in ml_units)
