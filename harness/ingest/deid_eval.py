# SPDX-License-Identifier: AGPL-3.0-or-later
"""Measure a pseudonymizer's PHI redaction — the de-id validation record.

Injects *synthetic* PHI at known positions into notes and checks each injected
value is absent from the pseudonymized output (leakage-recall), broken down per
PHI type, alongside a utility axis (do clinical signal tokens survive?).

HONEST SCOPE — read before quoting a number: synthetic PHI in a header slot is
*easier* than organic clinical PHI (misspelled names in prose, ambiguous
initials, dates mid-sentence), and TCGA text is already de-identified so there is
no organic PHI to catch. This metric is therefore an **upper bound** —
"did the values I injected disappear, per type, with this config" — not
ground-truth real-note recall. Real-note recall needs gold-annotated data such as
i2b2/n2c2 (DUA-gated). "Absent from output" is a leakage proxy, not span-level
detection.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from harness.hashing import content_hash

_METHOD = (
    "Synthetic PHI injected into de-identified notes; leakage-recall = fraction of "
    "injected values absent from the pseudonymized output, per PHI type. UPPER "
    "BOUND (synthetic-in-slot is easier than organic PHI; TCGA is already "
    "de-identified). Ground-truth real-note recall needs gold-annotated data "
    "(i2b2/n2c2, DUA-gated). 'Absent' is a leakage proxy, not span-level detection."
)


@dataclass(frozen=True)
class PhiItem:
    entity_type: str
    value: str  # the synthetic gold value that must be redacted


def build_injected(base_text: str, phi_items: list[PhiItem]) -> str:
    """Prepend a synthetic admin header carrying the injected PHI (known gold)."""
    header = "ADMIN HEADER (synthetic, for de-id testing): " + "; ".join(
        f"{p.value}" for p in phi_items
    ) + "."
    return header + "\n" + base_text


def measure_deid(
    pseudonymizer,
    base_texts: list[str],
    phi_items: list[PhiItem],
    utility_tokens: list[str],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    per_type: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "redacted": 0})
    util = {"n": 0, "retained": 0}

    for base in base_texts:
        out = pseudonymizer.pseudonymize(build_injected(base, phi_items)).text
        low = out.lower()
        for p in phi_items:
            per_type[p.entity_type]["n"] += 1
            if p.value.lower() not in low:
                per_type[p.entity_type]["redacted"] += 1
        base_low = base.lower()
        for tok in utility_tokens:
            if tok.lower() in base_low:  # only score tokens actually in this note
                util["n"] += 1
                if tok.lower() in low:
                    util["retained"] += 1

    types = {
        t: {"n": d["n"], "recall": (d["redacted"] / d["n"]) if d["n"] else None}
        for t, d in sorted(per_type.items())
    }
    tot_n = sum(d["n"] for d in per_type.values())
    tot_red = sum(d["redacted"] for d in per_type.values())
    config = config or {}
    return {
        "record_type": "deid_recall_evaluation",
        "schema_version": 1,
        "method": _METHOD,
        "config": config,
        "config_hash": content_hash(config),
        "n_notes": len(base_texts),
        "per_type_recall": types,
        "overall_recall": (tot_red / tot_n) if tot_n else None,
        "utility_retention": (util["retained"] / util["n"]) if util["n"] else None,
        "utility_n": util["n"],
    }


def render_deid_md(report: dict[str, Any]) -> str:
    L = ["# De-identification recall evaluation", ""]
    L.append(f"*config `{report['config_hash'][:16]}` · {report['n_notes']} notes*")
    L.append("")
    L.append(f"> **Upper bound, not real-note recall.** {report['method']}")
    L.append("")
    ov = report["overall_recall"]
    ut = report["utility_retention"]
    L.append(f"**Overall leakage-recall: {ov:.0%}**" if ov is not None else "**Overall: n/a**")
    L.append(f" · clinical-signal retention: {ut:.0%} (n={report['utility_n']})"
             if ut is not None else "")
    L.append("\n| PHI type | n | leakage-recall |")
    L.append("| --- | --- | --- |")
    for t, d in report["per_type_recall"].items():
        r = d["recall"]
        L.append(f"| {t} | {d['n']} | {'—' if r is None else f'{r:.0%}'} |")
    if report.get("config"):
        L.append("\n_Config:_ " + ", ".join(f"{k}={v}" for k, v in report["config"].items()))
    return "\n".join(L) + "\n"
