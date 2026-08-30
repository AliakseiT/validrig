# SPDX-License-Identifier: AGPL-3.0-or-later
"""Publish pinned run evidence as site-ready content.

``rig publish`` turns a pack plus one or more pinned runs into a structured
content object (currently the ``pipeline`` template): authored plain-language
prose from a per-pack ``publish.yaml``, machine-derived numbers resolved from
run artifacts via ``{{fact}}`` placeholders, and the real validation dossier
embedded as an HTML fragment. The engine stays use-case-agnostic: everything
domain-specific lives in the pack repo (pack files + publish.yaml).
"""

from validrig.publish.content import build_pipeline_content
from validrig.publish.emit import emit_json, emit_ts
from validrig.publish.facts import FactError, build_facts, resolve_placeholders
from validrig.publish.spec import PublishSpec, load_publish_spec

__all__ = [
    "FactError",
    "PublishSpec",
    "build_facts",
    "build_pipeline_content",
    "emit_json",
    "emit_ts",
    "load_publish_spec",
    "resolve_placeholders",
]
