from __future__ import annotations

import sys

from PySide6.QtGui import QFont


def ui_font_family() -> str:
    """Preferred UI font family for the current OS (empty = Qt default)."""
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return ".AppleSystemUIFont"
    return ""


def ui_font(size: int = -1, weight: QFont.Weight | None = None) -> QFont:
    family = ui_font_family()
    if weight is None:
        font = QFont(family, size) if family else QFont()
        if size > 0:
            font.setPointSize(size)
        return font
    if family:
        return QFont(family, size if size > 0 else -1, weight)
    font = QFont()
    if size > 0:
        font.setPointSize(size)
    font.setWeight(weight)
    return font
