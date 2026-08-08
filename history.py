from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent

from platform_ui import ui_font
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from history_store import HistoryEntry, HistoryStore
from pricing import fmt_money, fmt_tokens


class HistoryCard(QFrame):
    clicked = Signal(object)

    def __init__(self, entry: HistoryEntry, font_size: int = 12, parent=None) -> None:
        super().__init__(parent)
        self._entry = entry
        self.setObjectName("HistoryCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        ts = entry.ts[-8:] if len(entry.ts) >= 8 else entry.ts
        self.ts_label = QLabel(ts)
        self.ts_label.setObjectName("MetaLabel")

        self.src_label = QLabel(f"原文：{entry.source}")
        self.src_label.setWordWrap(True)
        self.src_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.dst_label = QLabel(f"译文：{entry.result}")
        self.dst_label.setWordWrap(True)
        self.dst_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        if entry.note == "local_cache":
            cost = "本地缓存 · 0分"
        else:
            cost = (
                f"{fmt_money(entry.cost_yuan)} · "
                f"hit {fmt_tokens(entry.hit)} / miss {fmt_tokens(entry.miss)} / "
                f"out {fmt_tokens(entry.completion)}"
            )
            if entry.saved_yuan > 0:
                cost += f" · 省 {fmt_money(entry.saved_yuan)}"
        self.cost_label = QLabel(cost)
        self.cost_label.setObjectName("MetaLabel")

        layout.addWidget(self.ts_label)
        layout.addWidget(self.src_label)
        layout.addWidget(self.dst_label)
        layout.addWidget(self.cost_label)
        self.apply_font_size(font_size)

    def apply_font_size(self, size: int) -> None:
        body = ui_font(size)
        meta = ui_font(max(9, size - 1))
        self.src_label.setFont(body)
        self.dst_label.setFont(body)
        self.ts_label.setFont(meta)
        self.cost_label.setFont(meta)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._entry)
        super().mousePressEvent(event)


class HistoryDialog(QDialog):
    entry_selected = Signal(object)  # HistoryEntry

    def __init__(
        self, store: HistoryStore, parent=None, font_size: int = 12
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._font_size = font_size
        self.setWindowTitle("翻译历史")
        self.resize(520, 520)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("日期"))
        self.day_combo = QComboBox()
        self.day_combo.currentTextChanged.connect(self._load_day)
        top.addWidget(self.day_combo, stretch=1)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.reload_days)
        top.addWidget(refresh)
        layout.addLayout(top)

        self.list = QListWidget()
        self.list.setSpacing(6)
        layout.addWidget(self.list, stretch=1)

        hint = QLabel("点击条目回填到主窗口 · 日志按日永久保留")
        hint.setObjectName("MetaLabel")
        layout.addWidget(hint)

        self.setStyleSheet(
            """
            QDialog, QWidget { background: #1e1f22; color: #e8eaed; }
            QComboBox, QListWidget {
                background: #2b2d31;
                border: 1px solid #3c4043;
                border-radius: 6px;
                padding: 4px;
                color: #e8eaed;
            }
            QListWidget::item { border: none; }
            #HistoryCard {
                background: #25272b;
                border: 1px solid #3c4043;
                border-radius: 8px;
            }
            #HistoryCard:hover { border-color: #3c78d8; }
            #MetaLabel { color: #9aa0a6; }
            QPushButton {
                background: #3c78d8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #4b86e0; }
            """
        )
        self.reload_days()

    def apply_font_size(self, size: int) -> None:
        self._font_size = size
        self.reload_days()

    def reload_days(self) -> None:
        current = self.day_combo.currentText()
        days = self._store.list_days()
        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        self.day_combo.addItems(days)
        if current and current in days:
            self.day_combo.setCurrentText(current)
        self.day_combo.blockSignals(False)
        self._load_day(self.day_combo.currentText())

    def _load_day(self, day: str) -> None:
        self.list.clear()
        if not day:
            return
        width = max(280, self.list.viewport().width() - 12)
        for entry in self._store.load_day(day):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, entry)
            card = HistoryCard(entry, font_size=self._font_size)
            card.setFixedWidth(width)
            card.clicked.connect(self.entry_selected.emit)
            # 先放进列表再量高，确保 wordWrap 按宽度计算
            self.list.addItem(item)
            self.list.setItemWidget(item, card)
            hint = card.sizeHint()
            item.setSizeHint(QSize(width, max(hint.height(), 80)))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = max(280, self.list.viewport().width() - 12)
        for i in range(self.list.count()):
            item = self.list.item(i)
            card = self.list.itemWidget(item)
            if isinstance(card, HistoryCard):
                card.setFixedWidth(width)
                item.setSizeHint(QSize(width, max(card.sizeHint().height(), 80)))
