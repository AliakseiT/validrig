# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ingest pseudonymized production events from a JSONL file.

Each line is one ``ProductionEvent``. Validation rejects any event carrying
unexpected fields (a guard against PHI leaking into the monitoring log).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from harness.monitoring.models import ProductionEvent


class MonitoringIngestError(Exception):
    """Raised when a production-event file is malformed or carries unexpected fields."""


def load_events(path: str | Path) -> list[ProductionEvent]:
    events: list[ProductionEvent] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(ProductionEvent(**json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise MonitoringIngestError(f"line {lineno}: {exc}") from exc
    return events
