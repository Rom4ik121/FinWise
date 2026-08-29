"""Download web3icons background SVGs and rasterize exchange PNGs."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.domain.exchanges import EXCHANGES, WEB3_ICONS
OUT = ROOT / "assets" / "icons" / "exchanges"
BASE = "https://cdn.jsdelivr.net/gh/0xa3k5/web3icons@main/raw-svgs"
NOTICE = (
    "Icons from https://github.com/0xa3k5/web3icons (MIT License).\n"
    "Background variants rasterized for FinWise account badges.\n"
)


def _fetch(kind: str, stem: str, variant: str) -> bytes:
    url = f"{BASE}/{kind}/{variant}/{stem}.svg"
    with urllib.request.urlopen(url, timeout=45) as resp:
        data = resp.read()
    if not data.startswith(b"<svg") and b"<svg" not in data[:200]:
        raise RuntimeError(f"Not an SVG: {url}")
    return data


def _svg_to_png(svg: bytes, dest: Path, *, zoom: float = 10.0) -> None:
    doc = pymupdf.open(stream=svg, filetype="svg")
    page = doc[0]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
    dest.write_bytes(pix.tobytes("png"))
    doc.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "NOTICE.txt").write_text(NOTICE, encoding="utf-8")
    failed: list[str] = []
    for spec in EXCHANGES:
        source = WEB3_ICONS.get(spec.id)
        dest = OUT / f"{spec.id}.png"
        if source is None:
            print(f"skip {spec.id}: not in web3icons")
            continue
        try:
            svg = _fetch(*source)
            _svg_to_png(svg, dest)
            print(f"ok {spec.id} ({dest.stat().st_size} bytes)")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{spec.id}: {exc}")
            print(f"fail {spec.id}: {exc}")
    if failed:
        raise SystemExit("\n".join(failed))


if __name__ == "__main__":
    main()
