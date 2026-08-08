"""Generate assets/app.ico from Lucide clipboard SVG on a blue rounded square."""

from __future__ import annotations

import io
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
SVG_PATH = ROOT / "assets" / "icons" / "clipboard.svg"
OUT_ICO = ROOT / "assets" / "app.ico"
SIZES = (16, 32, 48, 64, 128, 256)
BG = QColor("#3c78d8")


def _qimage_to_pil(image: QImage) -> Image.Image:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    buf.close()
    return Image.open(io.BytesIO(bytes(ba))).convert("RGBA")


def _render_size(size: int) -> Image.Image:
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


def main() -> int:
    QApplication([])
    if not SVG_PATH.exists():
        print(f"Missing {SVG_PATH}", file=sys.stderr)
        return 1

    images = [_render_size(s) for s in SIZES]
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(
        OUT_ICO,
        format="ICO",
        sizes=[(im.width, im.height) for im in images],
        append_images=images[:-1],
    )
    print(f"Wrote {OUT_ICO} ({', '.join(str(s) for s in SIZES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
