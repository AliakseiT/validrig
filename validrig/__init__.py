# SPDX-License-Identifier: AGPL-3.0-or-later
"""The validrig engine — use-case-agnostic evaluation core.

The engine contains no use-case-specific logic. Everything specific to an
intended use lives in declarative packs under ``packs/``.
"""

from validrig.version import ENGINE_VERSION

__all__ = ["ENGINE_VERSION"]
