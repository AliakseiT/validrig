# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resolve API-key auth headers from the environment.

The API key value never appears in a binding, a pin, a stored generation, or any
committed file — only the *name* of the environment variable does. The secret is
read from the environment at call time and used solely to build the request
header.
"""

from __future__ import annotations

import os


class MissingApiKeyError(RuntimeError):
    """Raised when a binding names an env var for the API key that is not set."""


def auth_headers(api_key_env: str | None) -> dict[str, str]:
    if not api_key_env:
        return {}
    key = os.environ.get(api_key_env)
    if not key:
        raise MissingApiKeyError(
            f"environment variable '{api_key_env}' is not set (required for this endpoint)"
        )
    return {"Authorization": f"Bearer {key}"}
