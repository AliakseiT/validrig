# SPDX-License-Identifier: AGPL-3.0-or-later
"""Human-in-the-loop review UI (optional extra: ``pip install validrig[ui]``).

A thin, server-rendered FastAPI app for judge calibration: a clinician
double-grades sampled generations and sees judge-human agreement (kappa) and the
calibration gate. Reads the run store the engine writes; writes human grades to a
separate append-only calibration store. Never mutates immutable results.
"""

from validrig.ui.app import create_app

__all__ = ["create_app"]
