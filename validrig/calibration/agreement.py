# SPDX-License-Identifier: AGPL-3.0-or-later
"""Judge-human agreement statistics.

Joins the judge's stored grades with human double-grades and computes, per rubric
item, the observation count, percent agreement, and Cohen's kappa. Items the
judge could not grade (``judge_error``, absent from ``item_scores``) are excluded
from agreement — you cannot agree or disagree on a grade that was never produced.
Keep the method simple and citable: binary labels (score > 0), plain kappa.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from validrig.calibration.models import HumanGrade
from validrig.models.results import Grade


def cohen_kappa(judge_labels: list[int], human_labels: list[int]) -> float | None:
    """Cohen's kappa for paired categorical labels. ``None`` if no observations."""
    n = len(judge_labels)
    if n == 0:
        return None
    po = sum(1 for a, b in zip(judge_labels, human_labels) if a == b) / n
    classes = set(judge_labels) | set(human_labels) | {0, 1}
    pe = 0.0
    for c in classes:
        pj = sum(1 for x in judge_labels if x == c) / n
        ph = sum(1 for x in human_labels if x == c) / n
        pe += pj * ph
    if pe >= 1.0:
        # No label variability, so chance agreement is total. Convention: return
        # 1.0 on perfect agreement, else 0.0. Note the "kappa paradox" — an
        # all-same-class item (e.g. every generation truly "pass") yields kappa
        # 1.0 without any disagreement having been tested. Low-n is already
        # advisory; read a high kappa on a zero-variance item with that in mind.
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def _label(score: float) -> int:
    return 1 if score > 0 else 0


def compute_agreement(
    judge_grades: list[Grade],
    human_grades: list[HumanGrade],
) -> dict[str, Any]:
    judge_by_key = {(g.case_id, g.perturbation_id, g.sample_idx): g for g in judge_grades}

    # The human-grade store is append-only, so a re-grade (the reviewer's core
    # correcting action) adds a new line. Keep only the latest grade per
    # (grader, content key) before counting, or a corrected unit would be counted
    # twice — and the stale, wrong label would still skew kappa and the gate.
    latest: dict[tuple[str, tuple], HumanGrade] = {}
    for hg in human_grades:
        latest[(hg.grader_id, hg.content_key())] = hg
    deduped = list(latest.values())

    per_item_judge: dict[str, list[int]] = defaultdict(list)
    per_item_human: dict[str, list[int]] = defaultdict(list)

    for hg in deduped:
        jg = judge_by_key.get(hg.content_key())
        if jg is None:
            continue
        for item_id, hscore in hg.item_scores.items():
            if item_id not in jg.item_scores:
                continue  # judge could not grade this item; excluded
            per_item_judge[item_id].append(_label(jg.item_scores[item_id]))
            per_item_human[item_id].append(_label(hscore))

    items: dict[str, dict[str, Any]] = {}
    all_judge: list[int] = []
    all_human: list[int] = []
    for item_id in sorted(per_item_judge):
        j = per_item_judge[item_id]
        h = per_item_human[item_id]
        agree = sum(1 for a, b in zip(j, h) if a == b)
        items[item_id] = {
            "n": len(j),
            "percent_agreement": agree / len(j) if j else None,
            "kappa": cohen_kappa(j, h),
        }
        all_judge += j
        all_human += h

    overall = {
        "n": len(all_judge),
        "percent_agreement": (
            sum(1 for a, b in zip(all_judge, all_human) if a == b) / len(all_judge)
            if all_judge
            else None
        ),
        "kappa": cohen_kappa(all_judge, all_human),
    }
    return {"items": items, "overall": overall}
