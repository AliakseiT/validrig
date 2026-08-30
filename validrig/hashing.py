# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical JSON serialization and content hashing.

Content hashes are the backbone of the versioning spine: two objects with the
same content hash to the same value regardless of key ordering, which is what
makes deterministic replay and regression diffs possible.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical JSON bytes.

    Keys are sorted, whitespace is stripped, and non-ASCII characters are kept
    as UTF-8 (not escaped). Two objects that differ only in key order or
    formatting produce identical bytes.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_hash(obj: Any) -> str:
    """Return the sha256 hex digest of ``obj``'s canonical JSON."""
    return hashlib.sha256(canonical_json(obj)).hexdigest()
