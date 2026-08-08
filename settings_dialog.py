from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)
from PySide6.QtCore import Qt


class SettingsDialog(QDialog):
    font_size_changed = Signal(int)

    def __init__(self, font_size: int = 12, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(320, 160)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("界面字号（主窗口 / 历史）"))

        row = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 22)
        self.slider.setValue(font_size)
        self.spin = QSpinBox()
        self.spin.setRange(10, 22)
        self.spin.setValue(font_size)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.spin.valueChanged.connect(self._preview_font)
        row.addWidget(self.slider, stretch=1)
        row.addWidget(self.spin)
        layout.addLayout(row)

        self.preview = QLabel("预览：原文 / 译文 Abc 123")
        layout.addWidget(self.preview)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        ok = QPushButton("确定")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self.setStyleSheet(
            """
            QDialog, QWidget { background: #1e1f22; color: #e8eaed; }
            QLabel { color: #c4c7cc; }
            QSpinBox, QSlider { color: #e8eaed; }
            QPushButton {
                background: #3c78d8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #4b86e0; }
            """
        )
        self._preview_font(font_size)

    def _preview_font(self, size: int) -> None:
        self.preview.setFont(QFont("Segoe UI", size))

    def _accept(self) -> None:
        self.font_size_changed.emit(self.spin.value())
        self.accept()

    def current_size(self) -> int:
        return self.spin.value()
