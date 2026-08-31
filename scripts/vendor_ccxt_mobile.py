"""Build a mobile-safe ccxt package (no aiodns/coincurve/zlib-ng).

Flet ``flet build apk|ipa`` installs with ``--only-binary :all:`` from
``pypi.flet.dev``. Upstream ccxt pulls ``aiodns`` → ``pycares`` (and newer
releases pull ``zlib-ng``), which have no iOS/Android forge wheels.

This script:

1. Downloads the upstream pure-Python wheel (or reuses ``vendor/wheels/``)
2. Writes ``vendor/ccxt/`` — a local package with safe dependencies
3. Optionally rewrites ``vendor/wheels/ccxt-<ver>-py2.py3-none-any.whl``

``pyproject.toml`` must depend on ``ccxt`` via ``[tool.flet.dev_packages]`` so
Flet rewrites the path to an absolute ``file:///...`` URL.

Codemagic / CI should run this **before** ``flet build`` (``vendor/ccxt`` is
gitignored — generated on the builder).

Usage::

    python scripts/vendor_ccxt_mobile.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "vendor" / "ccxt"
WHEEL_DIR = ROOT / "vendor" / "wheels"
CCXT_VERSION = "4.5.64"

_DROP_REQ = re.compile(
    r"(?i)^(Requires-Dist:\s*)(aiodns|coincurve|zlib-ng|aiohttp-fast-zlib|uvloop|winloop|orjson|setuptools)\b"
)

_KEEP_PREFIXES = (
    "Requires-Dist: cryptography",
    "Requires-Dist: aiohttp",
    "Requires-Dist: requests",
    "Requires-Dist: yarl",
    "Requires-Dist: certifi",
    "Requires-Dist: typing_extensions",
    "Requires-Dist: typing-extensions",
)

_PYPROJECT = f"""\
[project]
name = "ccxt"
version = "{CCXT_VERSION}"
description = "FinWise mobile-safe ccxt (no aiodns/pycares/coincurve)."
requires-python = ">=3.11"
dependencies = [
  "cryptography>=42,<50",
  "aiohttp>=3.10.11",
  "requests>=2.18.4",
  "yarl>=1.7.2",
  "certifi>=2018.1.18",
  "typing_extensions>=4.4.0",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["ccxt*"]

[tool.setuptools.package-data]
ccxt = ["py.typed", "**/*"]
"""


def _rewrite_metadata(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("Requires-Dist:"):
            if _DROP_REQ.match(stripped):
                continue
            base = stripped.split(";", 1)[0].strip()
            if not any(base.startswith(p) for p in _KEEP_PREFIXES):
                low = base.lower()
                if any(
                    x in low
                    for x in (
                        "aiodns",
                        "coincurve",
                        "zlib-ng",
                        "aiohttp-fast-zlib",
                        "uvloop",
                        "winloop",
                        "orjson",
                        "setuptools",
                    )
                ):
                    continue
                continue
            nl = "\n" if line.endswith("\n") else ""
            lines.append(base + nl)
            continue
        lines.append(line)
    body = "".join(lines)
    if "Requires-Dist: cryptography" not in body:
        body += "Requires-Dist: cryptography>=42,<50\n"
    else:
        body = re.sub(
            r"Requires-Dist: cryptography.*",
            "Requires-Dist: cryptography>=42,<50",
            body,
            count=1,
        )
    return body


def _download_or_reuse_wheel(version: str, dest: Path) -> Path:
    cached = WHEEL_DIR / f"ccxt-{version}-py2.py3-none-any.whl"
    meta_url = f"https://pypi.org/pypi/ccxt/{version}/json"
    try:
        with urllib.request.urlopen(meta_url, timeout=60) as resp:
            meta = json.load(resp)
        wheel = next(
            u
            for u in meta["urls"]
            if u["packagetype"] == "bdist_wheel" and u["filename"].endswith(".whl")
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {wheel['filename']} ({wheel['size']} bytes)…")
        urllib.request.urlretrieve(wheel["url"], dest)  # noqa: S310
        return dest
    except Exception as exc:  # noqa: BLE001
        if cached.is_file():
            print(f"Download failed ({exc}); using cached {cached}")
            return cached
        raise


def _strip_broken_bip(root: Path) -> None:
    """Remove BIP stubs with invalid ``from  import …`` (breaks mobile compileall)."""
    bip = root / "ccxt" / "static_dependencies" / "bip"
    if bip.is_dir():
        shutil.rmtree(bip)
        print("Removed broken package subtree ccxt/static_dependencies/bip")


def _write_package_from_extract(extract: Path) -> Path:
    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True)

    src_pkg = extract / "ccxt"
    if not src_pkg.is_dir():
        raise RuntimeError("ccxt/ folder missing from wheel")
    shutil.copytree(src_pkg, PKG_DIR / "ccxt")
    _strip_broken_bip(PKG_DIR)
    (PKG_DIR / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    print(f"Wrote package {PKG_DIR}")
    return PKG_DIR


def _write_wheel_from_extract(extract: Path, version: str) -> Path:
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WHEEL_DIR / f"ccxt-{version}-py2.py3-none-any.whl"
    _strip_broken_bip(extract)
    meta_files = list(extract.glob("*.dist-info/METADATA"))
    if not meta_files:
        raise RuntimeError("ccxt wheel missing METADATA")
    meta_path = meta_files[0]
    meta_path.write_text(
        _rewrite_metadata(meta_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    if out_path.exists():
        out_path.unlink()
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in extract.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(extract).as_posix())
    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
    return out_path


def build(version: str = CCXT_VERSION) -> Path:
    with tempfile.TemporaryDirectory(prefix="ccxt_vendor_") as tmp:
        tmp_path = Path(tmp)
        raw = _download_or_reuse_wheel(version, tmp_path / f"ccxt-{version}.whl")
        extract = tmp_path / "extract"
        extract.mkdir()
        with zipfile.ZipFile(raw, "r") as zf:
            zf.extractall(extract)
        pkg = _write_package_from_extract(extract)
        extract2 = tmp_path / "extract_wheel"
        extract2.mkdir()
        with zipfile.ZipFile(raw, "r") as zf:
            zf.extractall(extract2)
        _write_wheel_from_extract(extract2, version)
        return pkg


def main() -> int:
    build(CCXT_VERSION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
