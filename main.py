from __future__ import annotations

import sys
from threading import Event

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from cache import LruCache
from config import Config, load_config, save_font_size
from history import HistoryDialog
from history_store import HistoryEntry, HistoryStore, now_ts
from pricing import estimate_cost, format_status_lines
from settings_dialog import SettingsDialog
from translator import OpenAICompatTranslator, UsageInfo
from window import TranslatorWindow


class TranslateWorker(QObject):
    delta = Signal(int, str)  # generation, chunk
    finished = Signal(int, str, str, object)  # generation, source, result, UsageInfo
    failed = Signal(int, str)  # generation, error
    done = Signal()

    def __init__(
        self,
        translator: OpenAICompatTranslator,
        text: str,
        target_lang: str,
        cancel_event: Event,
        generation: int,
    ) -> None:
        super().__init__()
        self._translator = translator
        self._text = text
        self._target_lang = target_lang
        self._cancel_event = cancel_event
        self._generation = generation

    @Slot()
    def run(self) -> None:
        try:
            result = self._translator.translate_stream(
                self._text,
                self._target_lang,
                self._cancel_event,
                on_delta=lambda chunk: self.delta.emit(self._generation, chunk),
            )
            if not self._cancel_event.is_set():
                self.finished.emit(
                    self._generation,
                    self._text,
                    result.text,
                    result.usage,
                )
        except Exception as exc:  # noqa: BLE001 - surface to UI
            if not self._cancel_event.is_set():
                self.failed.emit(self._generation, str(exc))
        finally:
            self.done.emit()


class AppController(QObject):
    def __init__(self, cfg: Config, window: TranslatorWindow) -> None:
        super().__init__()
        self._cfg = cfg
        self._window = window
        self._translator = OpenAICompatTranslator(
            cfg.llm, target_lang=cfg.app.target_lang
        )
        self._cache = LruCache(cfg.app.cache_size)
        self._history = HistoryStore()
        self._history_dialog: HistoryDialog | None = None
        self._font_size = cfg.app.font_size
        self._listening = True
        self._ignore_clipboard = False
        self._last_text = ""
        self._generation = 0
        self._cancel_event: Event | None = None
        self._thread: QThread | None = None
        self._worker: TranslateWorker | None = None

        self._translator.warm_up()

        QGuiApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        self._window.copy_btn.clicked.connect(self.copy_translation)
        self._window.history_requested.connect(self.open_history)
        self._window.settings_requested.connect(self.open_settings)

    def set_listening(self, enabled: bool) -> None:
        self._listening = enabled
        self._window.set_status("监听中" if enabled else "已暂停")

    @Slot()
    def open_settings(self) -> None:
        dialog = SettingsDialog(self._font_size, self._window)
        dialog.font_size_changed.connect(self.apply_font_size)
        dialog.exec()

    @Slot(int)
    def apply_font_size(self, size: int) -> None:
        self._font_size = size
        self._window.apply_font_size(size)
        if self._history_dialog is not None:
            self._history_dialog.apply_font_size(size)
        save_font_size(size)

    @Slot()
    def open_history(self) -> None:
        if self._history_dialog is None:
            self._history_dialog = HistoryDialog(
                self._history, self._window, font_size=self._font_size
            )
            self._history_dialog.entry_selected.connect(self._on_history_selected)
        else:
            self._history_dialog.apply_font_size(self._font_size)
        self._history_dialog.reload_days()
        self._history_dialog.show()
        self._history_dialog.raise_()
        self._history_dialog.activateWindow()

    @Slot(object)
    def _on_history_selected(self, entry: object) -> None:
        if not isinstance(entry, HistoryEntry):
            return
        self._last_text = entry.source.strip()
        self._window.set_source(entry.source)
        self._window.set_result(entry.result)
        if entry.note == "local_cache":
            self._window.set_status(format_status_lines(
                estimate_cost(self._cfg.llm.model, 0, 0, 0), local_cache=True
            ))
        else:
            cost = estimate_cost(
                self._cfg.llm.model, entry.hit, entry.miss, entry.completion
            )
            self._window.set_status(format_status_lines(cost))
        self._window.show_and_raise()

    @Slot()
    def copy_translation(self) -> None:
        text = self._window.result.toPlainText().strip()
        if not text:
            return
        self._ignore_clipboard = True
        try:
            QGuiApplication.clipboard().setText(text)
        finally:
            self._ignore_clipboard = False
        self._window.set_status("已复制译文")

    @Slot()
    def on_clipboard_changed(self) -> None:
        if not self._listening or self._ignore_clipboard:
            return

        text = QGuiApplication.clipboard().text()
        if text is None:
            return
        text = text.strip()
        if not text or text == self._last_text:
            return
        if len(text) < self._cfg.app.min_chars:
            return
        if len(text) > self._cfg.app.max_chars:
            text = text[: self._cfg.app.max_chars]

        self._last_text = text
        self._window.show_and_raise()
        self._window.set_source(text)
        self._window.clear_result()

        cache_key = f"{self._cfg.app.target_lang}\n{text}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._window.set_result(cached)
            self._window.set_status(
                format_status_lines(
                    estimate_cost(self._cfg.llm.model, 0, 0, 0), local_cache=True
                )
            )
            self._history.append(
                HistoryEntry(
                    ts=now_ts(),
                    source=text,
                    result=cached,
                    note="local_cache",
                )
            )
            return

        self._start_translate(text)

    def _start_translate(self, text: str) -> None:
        self._cancel_current()
        self._generation += 1
        generation = self._generation
        cancel_event = Event()
        self._cancel_event = cancel_event

        thread = QThread()
        worker = TranslateWorker(
            self._translator,
            text,
            self._cfg.app.target_lang,
            cancel_event,
            generation,
        )
        worker.moveToThread(thread)

        queued = Qt.ConnectionType.QueuedConnection
        thread.started.connect(worker.run)
        worker.delta.connect(self._on_delta, queued)
        worker.finished.connect(self._on_finished, queued)
        worker.failed.connect(self._on_failed, queued)
        worker.done.connect(thread.quit, queued)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        self._window.set_status("翻译中…")
        thread.start()

    def _cancel_current(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    @Slot(int, str)
    def _on_delta(self, generation: int, chunk: str) -> None:
        if generation != self._generation:
            return
        self._window.append_result(chunk)

    @Slot(int, str, str, object)
    def _on_finished(
        self, generation: int, source: str, result: str, usage: object
    ) -> None:
        if generation != self._generation:
            return
        info = usage if isinstance(usage, UsageInfo) else UsageInfo()
        if result:
            self._window.set_result(result)
            self._cache.put(f"{self._cfg.app.target_lang}\n{source}", result)
        cost = estimate_cost(
            self._cfg.llm.model, info.hit, info.miss, info.completion
        )
        self._window.set_status(format_status_lines(cost))
        if result:
            self._history.append(
                HistoryEntry(
                    ts=now_ts(),
                    source=source,
                    result=result,
                    hit=cost.hit,
                    miss=cost.miss,
                    completion=cost.completion,
                    cost_yuan=cost.cost_yuan,
                    saved_yuan=cost.saved_yuan,
                    note="",
                )
            )

    @Slot(int, str)
    def _on_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self._window.set_status(f"失败: {error}", error=True)


def _make_tray_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#3c78d8"))
    painter.setPen(QColor("#3c78d8"))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI", 22, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "译")
    painter.end()
    return QIcon(pix)


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Clipboard Translator")

    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(None, "配置错误", str(exc))
        return 1

    window = TranslatorWindow(
        always_on_top=cfg.app.always_on_top,
        font_size=cfg.app.font_size,
    )
    controller = AppController(cfg, window)

    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip("Clipboard Translator")
    menu = QMenu()

    act_show = QAction("显示窗口", menu)
    act_show.triggered.connect(window.show_and_raise)
    menu.addAction(act_show)

    act_settings = QAction("设置", menu)
    act_settings.triggered.connect(controller.open_settings)
    menu.addAction(act_settings)

    act_history = QAction("翻译历史", menu)
    act_history.triggered.connect(controller.open_history)
    menu.addAction(act_history)

    act_pause = QAction("暂停监听", menu)
    act_pause.setCheckable(True)

    def on_pause_toggled(checked: bool) -> None:
        controller.set_listening(not checked)
        act_pause.setText("继续监听" if checked else "暂停监听")

    act_pause.toggled.connect(on_pause_toggled)
    menu.addAction(act_pause)

    menu.addSeparator()
    act_quit = QAction("退出", menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (
            window.show_and_raise()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
    )
    tray.show()

    window.set_status("监听中")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
