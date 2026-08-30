# SPDX-License-Identifier: AGPL-3.0-or-later
"""Analysis over graded results.

The central quantity is the *information value* of each input element: how much
the score drops when that element is ablated versus the baseline. Together with
critical-omission rates this is the empirical input contract — which information
the system actually needs, and where its failures are dangerous.

Functions operate on ``GradedRecord`` — a grade joined with its ablation
provenance and the rubric's critical flags — so this module stays free of any
storage or use-case detail.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from validrig.stats.bootstrap import bootstrap_ci


@dataclass(frozen=True)
class GradedRecord:
    perturbation_id: str
    dropped: tuple[str, ...]
    item_scores: dict[str, float]
    critical_items: tuple[str, ...] = field(default_factory=tuple)


def overall_score(record: GradedRecord) -> float:
    scores = list(record.item_scores.values())
    return sum(scores) / len(scores) if scores else 0.0


def information_value(
    records: list[GradedRecord],
    baseline_dropped: tuple[str, ...] = (),
) -> dict[str, float]:
    """Mean score drop caused by ablating each element in isolation.

    Averages over every other axis (e.g. format) present in the records. A
    positive value means the element carries information the system relies on.
    """
    baseline = [overall_score(r) for r in records if r.dropped == baseline_dropped]
    base_mean = sum(baseline) / len(baseline) if baseline else 0.0

    elements = sorted({r.dropped[0] for r in records if len(r.dropped) == 1})
    result: dict[str, float] = {}
    for element in elements:
        vals = [overall_score(r) for r in records if r.dropped == (element,)]
        ablated_mean = sum(vals) / len(vals) if vals else base_mean
        result[element] = base_mean - ablated_mean
    return result


def critical_rates(
    records: list[GradedRecord],
    n_boot: int = 1000,
    seed: int = 0,
) -> dict[str, object]:
    """Critical-omission rate with a bootstrap CI.

    A critical omission is a critical rubric item scored below full marks. This
    doubles as a hallucination proxy: a critical claim not supported by evidence
    scores zero and is counted here.
    """
    indicators: list[float] = []
    for record in records:
        for item in record.critical_items:
            # An item the judge could not grade is absent from item_scores; it is
            # excluded here rather than counted as an omission (0), so a judge
            # error never inflates the critical-omission rate.
            if item not in record.item_scores:
                continue
            score = record.item_scores[item]
            indicators.append(0.0 if score > 0 else 1.0)
    mean, lo, hi = bootstrap_ci(indicators, n_boot=n_boot, seed=seed)
    return {
        "critical_omission_rate": {"mean": mean, "lo": lo, "hi": hi},
        "n": len(indicators),
    }


def mean_score(
    records: list[GradedRecord],
    n_boot: int = 1000,
    seed: int = 0,
) -> dict[str, float]:
    """Overall mean rubric score with a bootstrap CI."""
    vals = [overall_score(r) for r in records]
    mean, lo, hi = bootstrap_ci(vals, n_boot=n_boot, seed=seed)
    return {"mean": mean, "lo": lo, "hi": hi, "n": len(vals)}
