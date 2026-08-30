# SPDX-License-Identifier: AGPL-3.0-or-later
"""Environment hash — pins the runtime that produced a run.

The env hash captures the Python version, the engine version, and the versions
of the engine's core dependencies. It lives in run *metadata* (never in the
content blobs that determinism and regression diffs compare), so that swapping a
dependency is visible and attributable without breaking content comparison.
"""

from __future__ import annotations

import hashlib
import sys
from importlib.metadata import PackageNotFoundError, version

from validrig.version import ENGINE_VERSION

_TRACKED_PACKAGES = ("pydantic", "pyarrow", "httpx", "numpy", "PyYAML")


def _package_versions() -> list[str]:
    out = []
    for name in sorted(_TRACKED_PACKAGES):
        try:
            out.append(f"{name}=={version(name)}")
        except PackageNotFoundError:
            out.append(f"{name}==<absent>")
    return out


def env_hash() -> str:
    """Return a stable sha256 hex digest of the execution environment."""
    parts = [
        f"python=={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        f"engine=={ENGINE_VERSION}",
        *_package_versions(),
    ]
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
