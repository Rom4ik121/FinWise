"""Unit tests for transactions FTS5 helpers."""

from __future__ import annotations

from decimal import Decimal

from lib.infrastructure.repositories.transaction_fts import (
    amount_blob,
    build_fts_match,
    payee_blob,
    tags_blob,
)


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


def test_amount_and_payee_blobs() -> None:
    blob = amount_blob(Decimal("12.50"))
    assert "12.50" in blob
    assert "12" in blob
    payee = payee_blob([{"name": "Cafe Roma"}, {"name": "Tip"}])
    assert "Cafe Roma" in payee
    assert "Tip" in payee


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
