from __future__ import annotations

import sys
from enum import IntFlag

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QMouseEvent, QResizeEvent, QShowEvent

from platform_ui import ui_font
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from icons import svg_icon, title_icon_pair
from macos_window import apply_overlay_space_behavior

_RESIZE_MARGIN = 6


class _ResizeEdge(IntFlag):
    NONE = 0
    LEFT = 1
    RIGHT = 2
    TOP = 4
    BOTTOM = 8


class WrappingLabel(QLabel):
    """Word-wrapping label that uses the full width given by the layout."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        width = max(self.width(), 1)
        return QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.updateGeometry()


class TitleBar(QWidget):
    pin_toggled = Signal(bool)
    history_clicked = Signal()
    settings_clicked = Signal()
    minimize_clicked = Signal()
    close_clicked = Signal()
    user_moved = Signal()

    def __init__(self, parent: QWidget | None = None, pinned: bool = True) -> None:
        super().__init__(parent)
        self._drag_pos: QPoint | None = None
        self._did_drag = False
        self.setFixedHeight(36)
        self.setObjectName("TitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 4, 0)
        layout.setSpacing(4)

        self.title = QLabel("Clipboard Translator")
        self.title.setFont(ui_font(9, QFont.Weight.DemiBold))
        self.title.setStyleSheet("color: #e8eaed;")
        layout.addWidget(self.title)
        layout.addStretch(1)

        icon_size = QSize(16, 16)
        pin_normal, pin_active = title_icon_pair("pin", 16)
        self._pin_icon_normal = pin_normal
        self._pin_icon_active = pin_active
        self.pin_btn = QPushButton()
        self.pin_btn.setIcon(pin_active if pinned else pin_normal)
        self.pin_btn.setIconSize(icon_size)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(pinned)
        self.pin_btn.setToolTip("窗口置顶")
        self.pin_btn.setObjectName("TitleBtn")
        self.pin_btn.toggled.connect(self._on_pin_btn_toggled)

        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(svg_icon("settings", "#c4c7cc", 16))
        self.settings_btn.setIconSize(icon_size)
        self.settings_btn.setToolTip("设置")
        self.settings_btn.setObjectName("TitleBtn")
        self.settings_btn.clicked.connect(self.settings_clicked.emit)

        self.history_btn = QPushButton()
        self.history_btn.setIcon(svg_icon("history", "#c4c7cc", 16))
        self.history_btn.setIconSize(icon_size)
        self.history_btn.setToolTip("历史记录")
        self.history_btn.setObjectName("TitleBtn")
        self.history_btn.clicked.connect(self.history_clicked.emit)

        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("TitleBtn")
        self.min_btn.clicked.connect(self.minimize_clicked.emit)

        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.clicked.connect(self.close_clicked.emit)

        for btn in (
            self.pin_btn,
            self.settings_btn,
            self.history_btn,
            self.min_btn,
            self.close_btn,
        ):
            btn.setFixedHeight(28)
            btn.setFixedWidth(32)
            layout.addWidget(btn)

    def _on_pin_btn_toggled(self, checked: bool) -> None:
        self.pin_btn.setIcon(
            self._pin_icon_active if checked else self._pin_icon_normal
        )
        self.pin_toggled.emit(checked)

    def _window_edges_at(self, global_pos: QPoint) -> _ResizeEdge:
        win = self.window()
        if isinstance(win, TranslatorWindow):
            return win._edges_at_global(global_pos)
        return _ResizeEdge.NONE

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._window_edges_at(event.globalPosition().toPoint()):
                event.ignore()
                return
            self._drag_pos = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            self._did_drag = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            self._did_drag = True
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._did_drag:
            self.user_moved.emit()
        self._drag_pos = None
        self._did_drag = False
        super().mouseReleaseEvent(event)


class TranslatorWindow(QMainWindow):
    history_requested = Signal()
    settings_requested = Signal()
    clear_answer_requested = Signal()
    pin_changed = Signal(bool)

    def __init__(self, always_on_top: bool = True, font_size: int = 12) -> None:
        super().__init__()
        self._always_on_top = always_on_top
        self._font_size = font_size
        self._mode = "translate"
        self._user_placed = False
        self._anchored_once = False
        self._resize_edges = _ResizeEdge.NONE
        self._resize_origin_geo = QRect()
        self._resize_origin_global = QPoint()
        self.setWindowTitle("Clipboard Translator")
        self.resize(440, 400)
        self.setMinimumSize(340, 280)
        self.setMouseTracking(True)
        self._apply_window_flags()

        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = TitleBar(self, pinned=always_on_top)
        self.title_bar.pin_toggled.connect(self._on_pin_toggled)
        self.title_bar.settings_clicked.connect(self.settings_requested.emit)
        self.title_bar.history_clicked.connect(self.history_requested.emit)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.close_clicked.connect(self.hide)
        self.title_bar.user_moved.connect(self._on_user_moved)
        layout.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 10, 12, 12)
        body_layout.setSpacing(8)

        self.src_label = QLabel("原文")
        self.source = QTextEdit()
        self.source.setReadOnly(True)
        self.source.setPlaceholderText("复制任意文本后出现在这里…")

        self.dst_label = QLabel("译文")
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("流式译文…")

        # 状态行独占整行宽度，避免与按钮并排时 QLabel 换行宽度算错、过早折行
        self.status = WrappingLabel("就绪")
        self.status.setObjectName("StatusLabel")

        bottom = QHBoxLayout()
        self.billing = WrappingLabel("")
        self.billing.setObjectName("BillingLabel")
        self.clear_answer_btn = QPushButton()
        self.clear_answer_btn.setIcon(svg_icon("rotate-ccw", "#ffffff", 16))
        self.clear_answer_btn.setIconSize(QSize(16, 16))
        self.clear_answer_btn.setFixedSize(32, 32)
        self.clear_answer_btn.setToolTip("清空问答上下文")
        self.clear_answer_btn.setVisible(False)
        self.clear_answer_btn.clicked.connect(self.clear_answer_requested.emit)
        self.copy_btn = QPushButton("复制译文")
        bottom.addWidget(self.billing, stretch=1)
        bottom.addWidget(
            self.clear_answer_btn, alignment=Qt.AlignmentFlag.AlignBottom
        )
        bottom.addWidget(self.copy_btn, alignment=Qt.AlignmentFlag.AlignBottom)

        body_layout.addWidget(self.src_label)
        body_layout.addWidget(self.source, stretch=1)
        body_layout.addWidget(self.dst_label)
        body_layout.addWidget(self.result, stretch=2)
        body_layout.addWidget(self.status)
        body_layout.addLayout(bottom)
        layout.addWidget(body, stretch=1)

        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #1e1f22; color: #e8eaed; }
            #TitleBar { background: #16171a; border-bottom: 1px solid #2f3136; }
            QLabel { color: #9aa0a6; }
            #BillingLabel { color: #8ab4f8; }
            QTextEdit {
                background: #2b2d31;
                border: 1px solid #3c4043;
                border-radius: 6px;
                padding: 8px;
                color: #e8eaed;
                selection-background-color: #3c78d8;
            }
            QPushButton {
                background: #3c78d8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #4b86e0; }
            QPushButton:disabled { background: #555; color: #aaa; }
            #TitleBtn {
                background: transparent;
                color: #c4c7cc;
                border-radius: 4px;
                padding: 0 6px;
            }
            #TitleBtn:hover { background: #2b2d31; color: #fff; }
            #TitleBtn:checked { background: #3c78d8; color: #fff; }
            #CloseBtn {
                background: transparent;
                color: #c4c7cc;
                border-radius: 4px;
                font-size: 16px;
            }
            #CloseBtn:hover { background: #e81123; color: #fff; }
            """
        )
        self.apply_font_size(font_size)
        self._install_resize_filters(self)

    def _install_resize_filters(self, root: QWidget) -> None:
        root.installEventFilter(self)
        root.setMouseTracking(True)
        for child in root.findChildren(QWidget):
            child.installEventFilter(self)
            child.setMouseTracking(True)

    def _edges_at(self, pos: QPoint) -> _ResizeEdge:
        m = _RESIZE_MARGIN
        r = self.rect()
        edges = _ResizeEdge.NONE
        if pos.x() <= m:
            edges |= _ResizeEdge.LEFT
        elif pos.x() >= r.width() - m:
            edges |= _ResizeEdge.RIGHT
        if pos.y() <= m:
            edges |= _ResizeEdge.TOP
        elif pos.y() >= r.height() - m:
            edges |= _ResizeEdge.BOTTOM
        return edges

    def _edges_at_global(self, global_pos: QPoint) -> _ResizeEdge:
        return self._edges_at(self.mapFromGlobal(global_pos))

    def _cursor_for_edges(self, edges: _ResizeEdge) -> Qt.CursorShape:
        if edges in (_ResizeEdge.LEFT, _ResizeEdge.RIGHT):
            return Qt.CursorShape.SizeHorCursor
        if edges in (_ResizeEdge.TOP, _ResizeEdge.BOTTOM):
            return Qt.CursorShape.SizeVerCursor
        if edges in (
            _ResizeEdge.LEFT | _ResizeEdge.TOP,
            _ResizeEdge.RIGHT | _ResizeEdge.BOTTOM,
        ):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (
            _ResizeEdge.RIGHT | _ResizeEdge.TOP,
            _ResizeEdge.LEFT | _ResizeEdge.BOTTOM,
        ):
            return Qt.CursorShape.SizeBDiagCursor
        return Qt.CursorShape.ArrowCursor

    def _update_hover_cursor(self, global_pos: QPoint, target: QObject) -> None:
        if isinstance(target, QAbstractButton):
            self.unsetCursor()
            return
        edges = self._edges_at_global(global_pos)
        if edges:
            self.setCursor(self._cursor_for_edges(edges))
        else:
            self.unsetCursor()

    def _apply_resize(self, global_pos: QPoint) -> None:
        delta = global_pos - self._resize_origin_global
        geo = self._resize_origin_geo
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        edges = self._resize_edges

        if edges & _ResizeEdge.LEFT:
            x += delta.x()
            w -= delta.x()
            if w < min_w:
                x -= min_w - w
                w = min_w
        elif edges & _ResizeEdge.RIGHT:
            w = max(min_w, geo.width() + delta.x())

        if edges & _ResizeEdge.TOP:
            y += delta.y()
            h -= delta.y()
            if h < min_h:
                y -= min_h - h
                h = min_h
        elif edges & _ResizeEdge.BOTTOM:
            h = max(min_h, geo.height() + delta.y())

        self.setGeometry(x, y, w, h)

    def _end_resize(self) -> None:
        if self._resize_edges:
            self._user_placed = True
            self._resize_edges = _ResizeEdge.NONE
            self.releaseMouse()
            self.unsetCursor()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        etype = event.type()
        if etype in (
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
        ) and isinstance(event, QMouseEvent):
            global_pos = event.globalPosition().toPoint()

            if self._resize_edges:
                if etype == QEvent.Type.MouseMove:
                    self._apply_resize(global_pos)
                    return True
                if (
                    etype == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.MouseButton.LeftButton
                ):
                    self._end_resize()
                    return True
                return True

            if etype == QEvent.Type.MouseMove:
                if not (event.buttons() & Qt.MouseButton.LeftButton):
                    self._update_hover_cursor(global_pos, obj)
                return False

            if (
                etype == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and not isinstance(obj, QAbstractButton)
            ):
                edges = self._edges_at_global(global_pos)
                if edges:
                    self._resize_edges = edges
                    self._resize_origin_geo = self.geometry()
                    self._resize_origin_global = global_pos
                    self.setCursor(self._cursor_for_edges(edges))
                    self.grabMouse()
                    return True

            if etype == QEvent.Type.MouseButtonRelease:
                return False

        elif etype == QEvent.Type.Leave and obj is self:
            if not self._resize_edges:
                self.unsetCursor()

        return super().eventFilter(obj, event)

    def apply_font_size(self, size: int) -> None:
        self._font_size = size
        body = ui_font(size)
        label = ui_font(max(9, size - 1), QFont.Weight.DemiBold)
        status = ui_font(max(9, size - 1))
        self.source.setFont(body)
        self.result.setFont(body)
        self.src_label.setFont(label)
        self.dst_label.setFont(label)
        self.status.setFont(status)
        self.billing.setFont(status)
        self.clear_answer_btn.setFont(status)
        self.copy_btn.setFont(status)

    def _apply_window_flags(self) -> None:
        flags = (
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _on_user_moved(self) -> None:
        self._user_placed = True

    def _anchor_bottom_right(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        margin = 16
        x = geo.right() - self.width() - margin
        y = geo.bottom() - self.height() - margin
        self.move(max(geo.left(), x), max(geo.top(), y))

    def _apply_macos_overlay_behavior(self) -> None:
        if sys.platform == "darwin":
            apply_overlay_space_behavior(self)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_macos_overlay_behavior()
        if not self._anchored_once and not self._user_placed:
            self._anchor_bottom_right()
            self._anchored_once = True

    def _on_pin_toggled(self, pinned: bool) -> None:
        self._always_on_top = pinned
        visible = self.isVisible()
        geom = self.geometry()
        self._apply_window_flags()
        if visible:
            self.show()
            self.setGeometry(geom)
            self._apply_macos_overlay_behavior()
        self.pin_changed.emit(pinned)

    def show_raised(self) -> None:
        """Show and raise without stealing keyboard focus."""
        self.show()
        self._apply_macos_overlay_behavior()
        self.raise_()

    def show_and_raise(self) -> None:
        self.show_raised()
        self.activateWindow()

    def set_source(self, text: str) -> None:
        self.source.setPlainText(text)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = "answer" if mode == "answer" else "translate"
        answering = self._mode == "answer"
        self.src_label.setText("问题" if answering else "原文")
        self.dst_label.setText("回答" if answering else "译文")
        self.source.setPlaceholderText(
            "选中的问题出现在这里…" if answering else "复制任意文本后出现在这里…"
        )
        self.result.setPlaceholderText("流式回答…" if answering else "流式译文…")
        self.copy_btn.setText("复制回答" if answering else "复制译文")
        self.clear_answer_btn.setVisible(answering)

    def clear_result(self) -> None:
        self.result.clear()

    def append_result(self, chunk: str) -> None:
        self.result.moveCursor(self.result.textCursor().MoveOperation.End)
        self.result.insertPlainText(chunk)

    def set_result(self, text: str) -> None:
        self.result.setPlainText(text)

    def set_status(self, text: str, error: bool = False) -> None:
        color = "#f28b82" if error else "#9aa0a6"
        self.status.setStyleSheet(f"color: {color};")
        self.status.setText(text)

    def set_billing(self, text: str) -> None:
        self.billing.setText(text)
        self.billing.setVisible(bool(text))

    def alert(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)
