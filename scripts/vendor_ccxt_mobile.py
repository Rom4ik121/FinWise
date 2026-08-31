"""Build a mobile-safe ccxt wheel (no aiodns/coincurve/zlib-ng).

Flet ``flet build apk|ipa`` installs with ``--only-binary :all:`` from
``pypi.flet.dev``. Upstream ccxt pulls ``aiodns`` → ``pycares`` (and newer
releases pull ``zlib-ng``), which have no iOS/Android forge wheels and break
resolution. ccxt itself is pure Python and runs fine with aiohttp + cryptography
already shipped for mobile.

Usage::

    python scripts/vendor_ccxt_mobile.py

Writes ``vendor/wheels/ccxt-<ver>-py2.py3-none-any.whl`` and prints the path.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "vendor" / "wheels"
# Last line before aiodns-heavy / zlib-ng era; skips 4.5.16–18 coincurve pins.
CCXT_VERSION = "4.5.64"

# Drop anything that needs native wheels missing on pypi.flet.dev.
_DROP_REQ = re.compile(
    r"(?i)^(Requires-Dist:\s*)(aiodns|coincurve|zlib-ng|aiohttp-fast-zlib|uvloop|winloop|orjson|setuptools)\b"
)

# Keep only mobile-safe runtime deps (already on forge or pure Python).
_KEEP_PREFIXES = (
    "Requires-Dist: cryptography",
    "Requires-Dist: aiohttp",
    "Requires-Dist: requests",
    "Requires-Dist: yarl",
    "Requires-Dist: certifi",
    "Requires-Dist: typing_extensions",
    "Requires-Dist: typing-extensions",
)


def _download_wheel(version: str, dest: Path) -> Path:
    meta_url = f"https://pypi.org/pypi/ccxt/{version}/json"
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


def _rewrite_metadata(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("Requires-Dist:"):
            if _DROP_REQ.match(stripped):
                continue
            # Drop extras / environment markers we do not need; keep core safe pins.
            base = stripped.split(";", 1)[0].strip()
            if not any(base.startswith(p) for p in _KEEP_PREFIXES):
                # Also drop aiodns etc. that slipped without our drop regex.
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
            # Strip markers so pip on iOS does not re-introduce platform-only deps.
            nl = "\n" if line.endswith("\n") else ""
            lines.append(base + nl)
            continue
        lines.append(line)
    # Ensure cryptography stays within Flet mobile wheel range.
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


def build_wheel(version: str = CCXT_VERSION) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"ccxt-{version}-py2.py3-none-any.whl"
    out_path = OUT_DIR / out_name

    with tempfile.TemporaryDirectory(prefix="ccxt_vendor_") as tmp:
        tmp_path = Path(tmp)
        raw = _download_wheel(version, tmp_path / out_name)
        extract = tmp_path / "extract"
        extract.mkdir()
        with zipfile.ZipFile(raw, "r") as zf:
            zf.extractall(extract)

        meta_files = list(extract.glob("*.dist-info/METADATA"))
        if not meta_files:
            raise RuntimeError("ccxt wheel missing METADATA")
        meta_path = meta_files[0]
        original = meta_path.read_text(encoding="utf-8")
        meta_path.write_text(_rewrite_metadata(original), encoding="utf-8")

        if out_path.exists():
            out_path.unlink()
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in extract.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(extract).as_posix())

    print(f"Wrote {out_path} ({out_path.stat().st_size} bytes)")
    return out_path


def main() -> int:
    build_wheel(CCXT_VERSION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
