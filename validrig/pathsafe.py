# SPDX-License-Identifier: AGPL-3.0-or-later
"""Path-safety helpers for identifiers that become filesystem paths.

Case ids and run ids arrive from untrusted input (URL path parameters in the
review UI) and are used to build file paths. An unvalidated id like
``../../etc/x`` would escape its directory, so ids are validated against a strict
pattern and resolved paths are confined to their base directory — defense in
depth at the engine boundary, independent of any UI-layer check.
"""

from __future__ import annotations

import re
from pathlib import Path

# No dots, slashes, or separators — this alone blocks ".." traversal.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def is_safe_id(value: str) -> bool:
    return isinstance(value, str) and bool(_SAFE_ID.fullmatch(value))


def require_safe_id(value: str, kind: str = "id") -> str:
    if not is_safe_id(value):
        raise ValueError(f"unsafe {kind}: {value!r}")
    return value


def confined_path(base: str | Path, *parts: str) -> Path:
    """Join ``parts`` onto ``base`` and confirm the result stays within ``base``."""
    base_resolved = Path(base).resolve()
    target = base_resolved.joinpath(*parts).resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise ValueError(f"path escapes base directory: {target}")
    return target
