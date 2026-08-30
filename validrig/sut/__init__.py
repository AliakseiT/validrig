# SPDX-License-Identifier: AGPL-3.0-or-later
"""System-under-test adapters. All SUTs present the same ``generate`` interface."""

from validrig.sut.base import GenerationOutput, SUTAdapter
from validrig.sut.registry import build_adapter

__all__ = ["SUTAdapter", "GenerationOutput", "build_adapter"]
