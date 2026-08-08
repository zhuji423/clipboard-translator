from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from paths import icons_dir

# Lucide icons (ISC): https://github.com/lucide-icons/lucide


def svg_icon(
    name: str,
    color: str = "#c4c7cc",
    size: int = 18,
) -> QIcon:
    path = icons_dir() / f"{name}.svg"
    raw = path.read_text(encoding="utf-8")
    colored = raw.replace('stroke="currentColor"', f'stroke="{color}"')
    renderer = QSvgRenderer(QByteArray(colored.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)


def title_icon_pair(name: str, size: int = 16) -> tuple[QIcon, QIcon]:
    """normal / active(checked) 两套颜色。"""
    return (
        svg_icon(name, "#c4c7cc", size),
        svg_icon(name, "#ffffff", size),
    )
