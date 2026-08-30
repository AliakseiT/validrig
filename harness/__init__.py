# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deprecated compatibility shim: the ``harness`` package was renamed to ``validrig``.

Update imports (``from harness.x import y`` → ``from validrig.x import y``) and
the CLI (``harness ...`` → ``rig ...``). This shim aliases every ``harness.*``
import to the *same* module object as its ``validrig.*`` counterpart (no
duplicate classes, no eager import of optional extras). It will be removed in a
future release.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import warnings

import validrig
from validrig import ENGINE_VERSION

__all__ = ["ENGINE_VERSION"]

warnings.warn(
    "the 'harness' package was renamed to 'validrig'; "
    "update imports to 'validrig' (the 'harness' shim will be removed)",
    DeprecationWarning,
    stacklevel=2,
)


class _AliasLoader(importlib.abc.Loader):
    """Loader that hands back an already-imported validrig module unchanged."""

    def __init__(self, module):
        self._module = module

    def create_module(self, spec):
        return self._module

    def exec_module(self, module):  # already executed under its validrig name
        pass


class _ValidrigAliasFinder(importlib.abc.MetaPathFinder):
    """Resolve ``harness.*`` to the identical ``validrig.*`` module objects."""

    _PREFIX = __name__ + "."

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self._PREFIX):
            return None
        real = validrig.__name__ + fullname[len(__name__):]
        module = importlib.import_module(real)
        return importlib.util.spec_from_loader(
            fullname, _AliasLoader(module), is_package=hasattr(module, "__path__")
        )


# Must sit in front of PathFinder: once ``harness.x`` is aliased, PathFinder
# would otherwise re-load ``harness.x.y`` from the aliased parent's __path__ as
# a duplicate module object.
if not any(isinstance(f, _ValidrigAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _ValidrigAliasFinder())
