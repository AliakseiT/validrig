# SPDX-License-Identifier: AGPL-3.0-or-later
"""Post-market monitoring: production signals -> MonitoringSnapshot -> drift.

Ingests *already-pseudonymized* production events (element-presence booleans and
an override flag — never case content), aggregates them into a snapshot, and
detects drift against two distinct baselines: the validated contract/thresholds
(absolute) and a prior snapshot (trend). Production-side capture and
pseudonymization of real encounters is the hospital's integration, out of scope
here.
"""

from validrig.monitoring.drift import evaluate_drift
from validrig.monitoring.ingest import load_events
from validrig.monitoring.models import ProductionEvent
from validrig.monitoring.snapshot import build_snapshot

__all__ = ["ProductionEvent", "load_events", "build_snapshot", "evaluate_drift"]
