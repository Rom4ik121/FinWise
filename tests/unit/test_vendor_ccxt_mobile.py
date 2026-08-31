"""Unit tests for mobile-safe ccxt wheel METADATA rewrite."""

from __future__ import annotations

from scripts.vendor_ccxt_mobile import _rewrite_metadata


def test_rewrite_metadata_drops_aiodns_and_coincurve() -> None:
    raw = """\
Metadata-Version: 2.1
Name: ccxt
Version: 4.5.64
Requires-Dist: setuptools>=60.9.0
Requires-Dist: certifi>=2018.1.18
Requires-Dist: requests>=2.18.4
Requires-Dist: cryptography>=2.6.1
Requires-Dist: typing_extensions>=4.4.0
Requires-Dist: aiohttp>=3.10.11; python_version >= "3.5.2"
Requires-Dist: aiodns>=1.1.1; python_version >= "3.5.2"
Requires-Dist: yarl>=1.7.2; python_version >= "3.5.2"
Requires-Dist: coincurve==21.0.0; python_version >= "3.9" and python_version <= "3.13"
"""
    out = _rewrite_metadata(raw)
    low = out.lower()
    assert "aiodns" not in low
    assert "coincurve" not in low
    assert "setuptools" not in low
    assert "Requires-Dist: cryptography>=42,<50" in out
    assert "Requires-Dist: aiohttp>=3.10.11" in out
    assert "Requires-Dist: yarl>=1.7.2" in out
    assert "Requires-Dist: requests>=2.18.4" in out
