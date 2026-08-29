"""Download web3icons token SVGs and rasterize crypto PNGs."""

from __future__ import annotations

import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "assets" / "icons" / "crypto"
CURRENCIES = ROOT / "assets" / "data" / "currencies.json"
MIRRORS = (
    "https://cdn.jsdelivr.net/gh/0xa3k5/web3icons@main/raw-svgs/tokens",
    "https://raw.githubusercontent.com/0xa3k5/web3icons/main/raw-svgs/tokens",
)
META_URLS = (
    "https://cdn.jsdelivr.net/gh/0xa3k5/web3icons@main/packages/common/src/metadata/tokens.json",
    "https://raw.githubusercontent.com/0xa3k5/web3icons/main/packages/common/src/metadata/tokens.json",
)
NOTICE = (
    "Icons from https://github.com/0xa3k5/web3icons (MIT License).\n"
    "Background variants rasterized for FinWise account badges.\n"
)
ALIASES: dict[str, tuple[str, ...]] = {
    "MATIC": ("MATIC", "POL"),
    "POL": ("POL", "MATIC"),
    "RENDER": ("RENDER", "RNDR"),
    "TON": ("TON", "TONCOIN"),
    "HTX": ("HTX", "HT"),
}


def _log(message: str) -> None:
    print(message, flush=True)


def _fetch(url: str, *, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "finanse-icon-fetch"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _svg_to_png(svg: bytes, dest: Path, *, zoom: float = 6.0) -> None:
    doc = pymupdf.open(stream=svg, filetype="svg")
    page = doc[0]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
    dest.write_bytes(pix.tobytes("png"))
    doc.close()


def _catalog_codes() -> list[str]:
    data = json.loads(CURRENCIES.read_text(encoding="utf-8"))
    return [str(item["code"]).upper() for item in data if item.get("is_crypto")]


def _meta_rows() -> list[dict]:
    last_error = None
    for url in META_URLS:
        try:
            raw = json.loads(_fetch(url, timeout=40).decode("utf-8"))
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(last_error or "metadata fetch failed")


def _wanted_codes() -> list[str]:
    catalog = _catalog_codes()
    extra: list[str] = []
    try:
        for item in _meta_rows():
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol or symbol in catalog:
                continue
            rank = item.get("marketCapRank")
            if rank is None or int(rank) > 250:
                continue
            extra.append(symbol)
        _log(f"metadata extras: {len(set(extra))}")
    except Exception as exc:  # noqa: BLE001
        _log(f"token metadata unavailable, catalog only: {exc}")
    return list(dict.fromkeys([*catalog, *sorted(set(extra))]))


def _stems_for(code: str) -> tuple[str, ...]:
    extra = ALIASES.get(code, ())
    return tuple(dict.fromkeys((code, *extra)))


def _try_download(stem: str, dest: Path) -> bool:
    for base in MIRRORS:
        for variant in ("background", "branded", "mono"):
            url = f"{base}/{variant}/{stem}.svg"
            try:
                svg = _fetch(url)
            except Exception:  # noqa: BLE001
                continue
            if not svg.startswith(b"<svg") and b"<svg" not in svg[:200]:
                continue
            _svg_to_png(svg, dest)
            return True
    return False


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "NOTICE.txt").write_text(NOTICE, encoding="utf-8")
    wanted = _wanted_codes()
    _log(f"downloading {len(wanted)} token icons")
    pending = [code for code in wanted if not (OUT / f"{code}.png").is_file() or (OUT / f"{code}.png").stat().st_size <= 0]
    skipped = len(wanted) - len(pending)
    ok = 0
    failed: list[str] = []

    def _one(code: str) -> tuple[str, bool, int]:
        dest = OUT / f"{code}.png"
        for stem in _stems_for(code):
            if _try_download(stem, dest):
                return code, True, dest.stat().st_size
        return code, False, 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_one, code) for code in pending]
        for index, future in enumerate(as_completed(futures), start=1):
            code, saved, size = future.result()
            if saved:
                ok += 1
                _log(f"[{index}/{len(pending)}] ok {code} ({size} bytes)")
            else:
                failed.append(code)
                _log(f"[{index}/{len(pending)}] skip {code}")
    _log(f"done ok={ok} cached={skipped} missing={len(failed)}")
    if failed:
        _log("missing: " + ", ".join(sorted(failed)[:40]) + ("…" if len(failed) > 40 else ""))


if __name__ == "__main__":
    main()
