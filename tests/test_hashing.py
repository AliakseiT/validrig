# SPDX-License-Identifier: AGPL-3.0-or-later
from validrig.hashing import canonical_json, content_hash
from validrig.envhash import env_hash


def test_content_hash_key_order_invariant():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_content_hash_is_sha256_hex():
    h = content_hash({"a": 1})
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_content_hash_changes_with_value():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_canonical_json_is_compact_sorted_utf8():
    assert canonical_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    # non-ascii preserved (not escaped)
    assert "ü".encode() in canonical_json({"x": "ü"})


def test_env_hash_stable_and_hex():
    h1 = env_hash()
    h2 = env_hash()
    assert h1 == h2
    assert len(h1) == 64
