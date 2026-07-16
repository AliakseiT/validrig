# SPDX-License-Identifier: AGPL-3.0-or-later
"""System-under-test adapters. All SUTs present the same ``generate`` interface."""

from harness.sut.base import GenerationOutput, SUTAdapter
from harness.sut.registry import build_adapter

__all__ = ["SUTAdapter", "GenerationOutput", "build_adapter"]
