from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from icons import svg_icon
from platform_ui import ui_font


class SubmitTextEdit(QTextEdit):
    submitted = Signal(str)
    cancelled = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.submitted.emit(self.toPlainText())
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ManualInputWindow(QWidget):
    submitted = Signal(str)
    state_changed = Signal(int, int, int, int, float)

    def __init__(
        self,
        *,
        x: int | None = None,
        y: int | None = None,
        width: int = 420,
        height: int = 144,
        opacity: float = 0.82,
    ) -> None:
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._ready = False
        self._opacity = self._clamp_opacity(opacity)
        self.setWindowTitle("手动输入翻译")
        self.setMinimumSize(300, 116)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(self._opacity)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        frame = QWidget(self)
        frame.setObjectName("ManualInputFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        self.title_bar = QWidget(frame)
        self.title_bar.setObjectName("ManualInputTitleBar")
        self.title_bar.setCursor(Qt.CursorShape.SizeAllCursor)
        title = QHBoxLayout()
        self.title_bar.setLayout(title)
        title.setContentsMargins(0, 0, 0, 0)
        title.setSpacing(8)
        self.title_label = QLabel("输入要翻译的文字")
        self.title_label.setObjectName("ManualInputTitle")
        self.title_label.setCursor(Qt.CursorShape.SizeAllCursor)
        self.title_label.setFont(ui_font(9, QFont.Weight.DemiBold))
        self.title_label.installEventFilter(self)
        title.addWidget(self.title_label)
        title.addStretch(1)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(35, 100)
        self.opacity_slider.setFixedWidth(92)
        self.opacity_slider.setToolTip("透明度")
        self.opacity_slider.setValue(round(self._opacity * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        title.addWidget(self.opacity_slider)

        self.pin_btn = QPushButton()
        self.pin_btn.setIcon(svg_icon("pin", "#c4c7cc", 14))
        self.pin_btn.setFixedSize(24, 24)
        self.pin_btn.setObjectName("ManualInputTool")
        self.pin_btn.setToolTip("固定当前位置")
        self.pin_btn.clicked.connect(self._emit_state)
        title.addWidget(self.pin_btn)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setObjectName("ManualInputClose")
        self.close_btn.setToolTip("关闭")
        self.close_btn.clicked.connect(self.hide)
        title.addWidget(self.close_btn)
        self.title_bar.installEventFilter(self)
        layout.addWidget(self.title_bar)

        self.input = SubmitTextEdit()
        self.input.setPlaceholderText("Enter 翻译，Shift+Enter 换行，Esc 关闭")
        self.input.setAcceptRichText(False)
        self.input.setFont(ui_font(12))
        self.input.submitted.connect(self._submit)
        self.input.cancelled.connect(self.hide)
        layout.addWidget(self.input, stretch=1)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        grip = QSizeGrip(frame)
        grip.setFixedSize(14, 14)
        grip_row.addWidget(grip)
        layout.addLayout(grip_row)

        root.addWidget(frame)
        self.resize(max(300, width), max(116, height))
        if x is not None and y is not None:
            self.move(x, y)
        self.setStyleSheet(
            """
            #ManualInputFrame {
                background: #1e1f22;
                border: 1px solid #4b5563;
                border-radius: 8px;
            }
            #ManualInputTitleBar { background: transparent; }
            #ManualInputTitle { color: #e8eaed; }
            QTextEdit {
                background: #2b2d31;
                border: 1px solid #3c4043;
                border-radius: 6px;
                padding: 8px;
                color: #f1f3f4;
                selection-background-color: #3c78d8;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #3c4043;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                margin: -5px 0;
                border-radius: 6px;
                background: #8ab4f8;
            }
            #ManualInputTool, #ManualInputClose {
                background: transparent;
                color: #c4c7cc;
                border: none;
                border-radius: 4px;
                font-size: 16px;
            }
            #ManualInputTool:hover {
                background: #2b2d31;
            }
            #ManualInputTool:pressed, #ManualInputClose:pressed {
                background: #3c4043;
            }
            #ManualInputClose:hover {
                background: #e81123;
                color: white;
            }
            """
        )
        self._ready = True

    def show_prompt(self) -> None:
        if not self.isVisible() and self.pos().isNull():
            self._anchor_near_center()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _anchor_near_center(self) -> None:
        screen = self.screen()
        if screen is None:
            from PySide6.QtGui import QGuiApplication

            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.left() + max(0, (geo.width() - self.width()) // 2)
        y = geo.top() + max(0, geo.height() // 3)
        self.move(x, y)

    def _submit(self, text: str) -> None:
        text = " ".join(text.split())
        if not text:
            return
        self.input.clear()
        self.hide()
        self.submitted.emit(text)

    def _on_opacity_changed(self, value: int) -> None:
        self._opacity = self._clamp_opacity(value / 100)
        self.setWindowOpacity(self._opacity)
        self._emit_state()

    def _clamp_opacity(self, value: float) -> float:
        return max(0.35, min(1.0, float(value)))

    def _emit_state(self) -> None:
        if not self._ready:
            return
        geo = self.geometry()
        self.state_changed.emit(
            geo.x(), geo.y(), geo.width(), geo.height(), self._opacity
        )

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._emit_state()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._emit_state()

    def eventFilter(self, obj, event: QEvent) -> bool:  # noqa: N802
        title_bar = getattr(self, "title_bar", None)
        title_label = getattr(self, "title_label", None)
        if obj in (title_bar, title_label):
            if event.type() == QEvent.Type.MouseButtonPress and isinstance(
                event, QMouseEvent
            ):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._drag_pos = (
                        event.globalPosition().toPoint()
                        - self.frameGeometry().topLeft()
                    )
                    event.accept()
                    return True
            if event.type() == QEvent.Type.MouseMove and isinstance(
                event, QMouseEvent
            ):
                if (
                    self._drag_pos is not None
                    and event.buttons() & Qt.MouseButton.LeftButton
                ):
                    self.move(event.globalPosition().toPoint() - self._drag_pos)
                    event.accept()
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_pos = None
        return super().eventFilter(obj, event)
