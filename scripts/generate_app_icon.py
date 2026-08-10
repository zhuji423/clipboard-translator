"""Generate assets/app.ico, app.png, and (on macOS) app.icns.

Prefer assets/app-icon-source.png when present; otherwise render from
assets/icons/clipboard.svg on a solid brand background.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

try:
    from PIL import Image
except ImportError:
    print("Pillow required: pip install Pillow", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PNG = ROOT / "assets" / "app-icon-source.png"
SVG_PATH = ROOT / "assets" / "icons" / "clipboard.svg"
OUT_ICO = ROOT / "assets" / "app.ico"
OUT_PNG = ROOT / "assets" / "app.png"
OUT_ICNS = ROOT / "assets" / "app.icns"
SIZES = (16, 32, 48, 64, 128, 256)
# iconutil expects these names inside .iconset
ICNS_SIZES = (
    (16, "icon_16x16.png"),
    (32, "diana.k@example.org"),
    (32, "icon_32x32.png"),
    (64, "ivan.p@example.net"),
    (128, "icon_128x128.png"),
    (256, "wendy.h@example.net"),
    (256, "icon_256x256.png"),
    (512, "wendy.h@example.net"),
    (512, "icon_512x512.png"),
    (1024, "walt.e@example.net"),
)
BG = QColor("#3c78d8")
# macOS Dock masks the full canvas; AI squircles often fill edge-to-edge and look
# oversized next to HIG icons. Keep content ~80% centered (Apple-ish safe area).
DOCK_CONTENT_SCALE = 0.80


def _qimage_to_pil(image: QImage) -> Image.Image:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    buf.close()
    return Image.open(io.BytesIO(bytes(ba))).convert("RGBA")


def _knockout_black_corners(im: Image.Image, threshold: int = 12) -> Image.Image:
    """Make near-black canvas outside the squircle transparent (menu bar / Dock)."""
    rgba = im.convert("RGBA")
    pixels = rgba.load()
    assert pixels is not None
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a and r <= threshold and g <= threshold and b <= threshold:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def _fit_dock_safe_area(
    im: Image.Image, scale: float = DOCK_CONTENT_SCALE
) -> Image.Image:
    """Shrink artwork into the center so Dock size matches neighboring apps."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    scale = max(0.5, min(1.0, scale))
    if scale >= 0.999:
        return rgba
    inner_w = max(1, int(round(w * scale)))
    inner_h = max(1, int(round(h * scale)))
    fitted = rgba.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(fitted, ((w - inner_w) // 2, (h - inner_h) // 2), fitted)
    return canvas


def _render_from_source(size: int, source: Image.Image) -> Image.Image:
    return source.resize((size, size), Image.Resampling.LANCZOS)


def _render_from_svg(size: int) -> Image.Image:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = max(1, size // 16)
    radius = max(2.0, size * 0.22)
    path = QPainterPath()
    path.addRoundedRect(
        QRectF(margin, margin, size - 2 * margin, size - 2 * margin),
        radius,
        radius,
    )
    painter.fillPath(path, BG)

    pad = size * 0.18
    icon_rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    colored = SVG_PATH.read_text(encoding="utf-8").replace(
        'stroke="currentColor"', 'stroke="#ffffff"'
    )
    white_renderer = QSvgRenderer(QByteArray(colored.encode("utf-8")))
    white_renderer.render(painter, icon_rect)
    painter.end()
    return _qimage_to_pil(image)


def _write_icns(images_by_size: dict[int, Image.Image]) -> None:
    if sys.platform != "darwin":
        print("Skip app.icns (iconutil only on macOS); CI/build_macos.sh will generate it.")
        return
    if not shutil.which("iconutil"):
        print("iconutil not found; skip app.icns", file=sys.stderr)
        return

    iconset = ROOT / "assets" / "app.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    for size, name in ICNS_SIZES:
        if size not in images_by_size:
            raise KeyError(f"missing icon size {size}")
        images_by_size[size].save(iconset / name, format="PNG")

    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_ICNS)],
        check=True,
    )
    shutil.rmtree(iconset)
    print(f"Wrote {OUT_ICNS}")


def main() -> int:
    need_qt = not SOURCE_PNG.is_file()
    if need_qt:
        QApplication([])
        if not SVG_PATH.exists():
            print(f"Missing {SOURCE_PNG} and {SVG_PATH}", file=sys.stderr)
            return 1
        source: Image.Image | None = None
        print(f"Using SVG fallback: {SVG_PATH}")
    else:
        source = _fit_dock_safe_area(_knockout_black_corners(Image.open(SOURCE_PNG)))
        print(
            f"Using source PNG: {SOURCE_PNG} "
            f"({source.size[0]}x{source.size[1]}, dock scale={DOCK_CONTENT_SCALE})"
        )

    def render(size: int) -> Image.Image:
        if source is not None:
            return _render_from_source(size, source)
        return _render_from_svg(size)

    needed = set(SIZES) | {s for s, _ in ICNS_SIZES}
    images_by_size: dict[int, Image.Image] = {s: render(s) for s in sorted(needed)}

    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    ico_images = [images_by_size[s] for s in SIZES]
    ico_images[-1].save(
        OUT_ICO,
        format="ICO",
        sizes=[(im.width, im.height) for im in ico_images],
        append_images=ico_images[:-1],
    )
    print(f"Wrote {OUT_ICO} ({', '.join(str(s) for s in SIZES)})")

    images_by_size[256].save(OUT_PNG, format="PNG")
    print(f"Wrote {OUT_PNG}")

    _write_icns(images_by_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
