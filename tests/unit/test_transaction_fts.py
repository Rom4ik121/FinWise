"""Unit tests for transactions FTS5 helpers."""

from __future__ import annotations

from lib.infrastructure.repositories.transaction_fts import build_fts_match, tags_blob


def test_build_fts_match_and_prefixes() -> None:
    assert build_fts_match("  coffee  beans ") == '"coffee"* AND "beans"*'
    assert build_fts_match("") is None
    assert build_fts_match('***') is None
    # Quotes are stripped to spaces → two tokens.
    assert build_fts_match('foo"bar') == '"foo"* AND "bar"*'


def test_tags_blob_includes_space_and_json() -> None:
    blob = tags_blob(["alpha", "beta"])
    assert "alpha" in blob
    assert "beta" in blob
    assert '"alpha"' in blob
