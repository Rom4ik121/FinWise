"""Generate FinWise launcher icons and native splash assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1] / "assets"
ICON_SRC = ROOT / "icon.png"

BG_TOP = (11, 18, 32)  # #0B1220
BG_MID = (18, 26, 43)  # #121A2B
WHITE = (255, 255, 255)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient_canvas(size: int = 1280) -> Image.Image:
    img = Image.new("RGB", (size, size), BG_TOP)
    px = img.load()
    assert px is not None
    for y in range(size):
        t = y / max(size - 1, 1)
        for x in range(size):
            u = x / max(size - 1, 1)
            mix = (t + u) * 0.5
            r = int(BG_TOP[0] * (1 - mix) + BG_MID[0] * mix)
            g = int(BG_TOP[1] * (1 - mix) + BG_MID[1] * mix)
            b = int(BG_TOP[2] * (1 - mix) + BG_MID[2] * mix)
            px[x, y] = (r, g, b)
    return img


def _draw_material_wallet(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
    """Simple filled wallet silhouette close to Material ``account_balance_wallet``."""
    w, h = size, int(size * 0.72)
    left, top = cx - w // 2, cy - h // 2
    right, bottom = left + w, top + h
    radius = max(18, size // 12)
    draw.rounded_rectangle([left, top, right, bottom], radius=radius, fill=WHITE)
    # Card slot / flap
    flap = int(h * 0.28)
    draw.rounded_rectangle(
        [left, top, right, top + flap],
        radius=radius,
        fill=WHITE,
    )
    # Clasp circle on the right (Material wallet cue)
    clasp = max(14, size // 14)
    clasp_cx = right - int(w * 0.22)
    clasp_cy = top + h // 2
    draw.ellipse(
        [clasp_cx - clasp, clasp_cy - clasp, clasp_cx + clasp, clasp_cy + clasp],
        fill=BG_MID,
    )


def _splash_logo() -> Image.Image:
    """Native splash: gradient + Material-style wallet + FinWise + line."""
    canvas = _gradient_canvas(1280).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    _draw_material_wallet(draw, 640, 480, 360)
    title_font = _font(72)
    title = "FinWise"
    tw = draw.textlength(title, font=title_font)
    draw.text(((1280 - tw) / 2, 740), title, fill=WHITE, font=title_font)
    line_w = 160
    draw.rounded_rectangle(
        [((1280 - line_w) // 2, 830), ((1280 + line_w) // 2, 834)],
        radius=2,
        fill=WHITE,
    )
    return canvas.convert("RGB")


def _padded_android_icon(icon: Image.Image) -> Image.Image:
    """Adaptive icon foreground: logo centered on transparent canvas."""
    size = 1024
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    scale = 0.62
    iw, ih = icon.size
    ni, nj = int(iw * scale), int(ih * scale)
    scaled = icon.resize((ni, nj), Image.Resampling.LANCZOS)
    canvas.paste(scaled, ((size - ni) // 2, (size - nj) // 2), scaled)
    return canvas


def main() -> None:
    icon = Image.open(ICON_SRC).convert("RGBA")
    ROOT.mkdir(parents=True, exist_ok=True)

    splash = _splash_logo()
    for name in (
        "splash.png",
        "splash_android.png",
        "splash_ios.png",
        "splash_dark.png",
        "splash_dark_android.png",
        "splash_dark_ios.png",
    ):
        splash.save(ROOT / name)

    branding = Image.new("RGB", (1280, 320), BG_TOP)
    branding.save(ROOT / "splash_android_branding.png")

    # Launcher icon stays the product icon.png (unchanged).
    _padded_android_icon(icon).save(ROOT / "icon_android.png")
    print(f"Branding assets written to {ROOT}")


if __name__ == "__main__":
    main()
