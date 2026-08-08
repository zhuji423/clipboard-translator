from __future__ import annotations

import sys
from threading import Event

from PySide6.QtCore import QDateTime, QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from balance import BalanceError, BalanceInfo, fetch_balance
from cache import LruCache
from config import Config, LlmConfig, load_config, save_font_size
from history import HistoryDialog
from history_store import HistoryEntry, HistoryStore, now_ts
from paths import ensure_user_config, is_frozen
from pricing import estimate_cost, format_billing_line, format_status_lines
from settings_dialog import SettingsDialog
from translator import OpenAICompatTranslator, UsageInfo
from version import __version__
from window import TranslatorWindow

CLIPBOARD_SETTLE_MS = 350
CLIPBOARD_CONFIRM_MS = 800
COPY_IGNORE_MS = 300


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


class BalanceWorker(QObject):
    finished = Signal(int, object)  # generation, BalanceInfo
    failed = Signal(int, str)  # generation, error
    done = Signal()

    def __init__(self, llm: LlmConfig, generation: int) -> None:
        super().__init__()
        self._llm = llm
        self._generation = generation

    @Slot()
    def run(self) -> None:
        try:
            info = fetch_balance(self._llm)
            self.finished.emit(self._generation, info)
        except BalanceError as exc:
            self.failed.emit(self._generation, str(exc))
        except Exception as exc:  # noqa: BLE001 - surface to UI
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
        self._ignore_clipboard_text: str | None = None
        self._ignore_clipboard_until_ms = 0
        self._last_text = ""
        self._pending_text = ""
        self._confirm_text = ""
        self._generation = 0
        self._cancel_event: Event | None = None
        self._thread: QThread | None = None
        self._worker: TranslateWorker | None = None
        self._billing_generation = 0
        self._billing_thread: QThread | None = None
        self._billing_worker: BalanceWorker | None = None
        self._billing_pending = False
        self._billing_fetching = False
        self._remaining_yuan: float | None = None
        self._balance_error: str | None = None

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(CLIPBOARD_SETTLE_MS)
        self._settle_timer.timeout.connect(self._on_clipboard_settled)

        self._confirm_timer = QTimer(self)
        self._confirm_timer.setSingleShot(True)
        self._confirm_timer.setInterval(CLIPBOARD_CONFIRM_MS)
        self._confirm_timer.timeout.connect(self._on_clipboard_confirmed)

        self._translator.warm_up()

        QGuiApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        self._window.copy_btn.clicked.connect(self.copy_translation)
        self._window.history_requested.connect(self.open_history)
        self._window.settings_requested.connect(self.open_settings)
        self.refresh_billing()

    def set_listening(self, enabled: bool) -> None:
        self._listening = enabled
        if not enabled:
            self._abort_clipboard_pending()
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
        self._invalidate_inflight()
        self._abort_clipboard_pending()
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
        self._ignore_clipboard_text = text
        self._ignore_clipboard_until_ms = (
            QDateTime.currentMSecsSinceEpoch() + COPY_IGNORE_MS
        )
        QGuiApplication.clipboard().setText(text)
        self._window.set_status("已复制译文")

    def _should_ignore_clipboard(self, text: str) -> bool:
        if (
            self._ignore_clipboard_text is not None
            and text == self._ignore_clipboard_text
        ):
            return True
        if QDateTime.currentMSecsSinceEpoch() < self._ignore_clipboard_until_ms:
            return True
        return False

    def _normalize_clipboard_text(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        text = raw.strip()
        if not text:
            return None
        if len(text) < self._cfg.app.min_chars:
            return None
        if len(text) > self._cfg.app.max_chars:
            text = text[: self._cfg.app.max_chars]
        return text

    def _abort_clipboard_pending(self) -> None:
        self._settle_timer.stop()
        self._confirm_timer.stop()
        self._pending_text = ""
        self._confirm_text = ""

    @Slot()
    def on_clipboard_changed(self) -> None:
        if not self._listening:
            return

        text = self._normalize_clipboard_text(QGuiApplication.clipboard().text())
        # Empty / restored to previous source: drop settle+confirm with zero UI change.
        if text is None or text == self._last_text:
            if self._settle_timer.isActive() or self._confirm_timer.isActive():
                self._abort_clipboard_pending()
            return
        if self._should_ignore_clipboard(text):
            return

        self._pending_text = text
        self._confirm_timer.stop()
        self._confirm_text = ""
        self._settle_timer.start()

    @Slot()
    def _on_clipboard_settled(self) -> None:
        if not self._listening:
            return

        text = self._normalize_clipboard_text(QGuiApplication.clipboard().text())
        if text is None:
            text = self._normalize_clipboard_text(self._pending_text)
        self._pending_text = ""
        if text is None:
            return
        if self._should_ignore_clipboard(text):
            return
        if text == self._last_text:
            return

        # Confirm window: still no UI / LLM until content stays new.
        self._confirm_text = text
        self._confirm_timer.start()

    @Slot()
    def _on_clipboard_confirmed(self) -> None:
        if not self._listening:
            return

        text = self._normalize_clipboard_text(QGuiApplication.clipboard().text())
        if text is None:
            text = self._normalize_clipboard_text(self._confirm_text)
        candidate = self._confirm_text
        self._confirm_text = ""
        if text is None:
            return
        if self._should_ignore_clipboard(text):
            return
        if text == self._last_text:
            return
        if candidate and text != candidate:
            # Content changed again; wait for a fresh settle cycle.
            return

        if self._ignore_clipboard_text is not None:
            self._ignore_clipboard_text = None

        self._apply_clipboard_text(text)

    def _invalidate_inflight(self) -> int:
        self._cancel_current()
        self._generation += 1
        return self._generation

    def _apply_clipboard_text(self, text: str) -> None:
        self._last_text = text
        self._window.show_raised()
        self._invalidate_inflight()
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
            self.refresh_billing()
            return

        self._start_translate(text)

    def _start_translate(self, text: str) -> None:
        # Generation already bumped by _apply_clipboard_text / _invalidate_inflight.
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
        self.refresh_billing()

    @Slot(int, str)
    def _on_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self._window.set_status(f"失败: {error}", error=True)

    def _render_billing(self) -> None:
        used = self._history.sum_day_cost()
        error = self._balance_error
        remaining = self._remaining_yuan
        if remaining is None and error is None and self._billing_fetching:
            error = "余额查询中…"
        self._window.set_billing(
            format_billing_line(used, remaining, error=error)
        )

    def refresh_billing(self) -> None:
        """Refresh today-used immediately; fetch remote balance on a worker thread."""
        if self._billing_fetching:
            self._billing_pending = True
            self._render_billing()
            return
        self._start_balance_fetch()

    def _start_balance_fetch(self) -> None:
        self._billing_pending = False
        self._billing_fetching = True
        self._billing_generation += 1
        generation = self._billing_generation
        self._render_billing()

        thread = QThread()
        worker = BalanceWorker(self._cfg.llm, generation)
        worker.moveToThread(thread)

        queued = Qt.ConnectionType.QueuedConnection
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_balance_finished, queued)
        worker.failed.connect(self._on_balance_failed, queued)
        worker.done.connect(thread.quit, queued)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_billing_thread_finished)

        self._billing_thread = thread
        self._billing_worker = worker
        thread.start()

    @Slot()
    def _on_billing_thread_finished(self) -> None:
        self._billing_fetching = False
        self._billing_thread = None
        self._billing_worker = None
        if self._billing_pending:
            self._start_balance_fetch()
        else:
            self._render_billing()

    @Slot(int, object)
    def _on_balance_finished(self, generation: int, info: object) -> None:
        if generation != self._billing_generation:
            return
        if not isinstance(info, BalanceInfo):
            return
        self._remaining_yuan = info.total_yuan
        self._balance_error = None
        self._render_billing()

    @Slot(int, str)
    def _on_balance_failed(self, generation: int, error: str) -> None:
        if generation != self._billing_generation:
            return
        # Keep last known remaining; otherwise show a short hint.
        if self._remaining_yuan is None:
            self._balance_error = "余额暂不可用"
        self._render_billing()


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
        cfg_path, created = ensure_user_config()
        cfg = load_config(cfg_path)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(None, "配置错误", str(exc))
        return 1

    if created and is_frozen():
        QMessageBox.information(
            None,
            "首次运行",
            f"已创建配置文件：\n{cfg_path}\n\n"
            "请编辑其中的 llm.api_key（及端点）后再使用翻译。\n"
            "也可稍后打开该文件继续修改。",
        )

    window = TranslatorWindow(
        always_on_top=cfg.app.always_on_top,
        font_size=cfg.app.font_size,
    )
    controller = AppController(cfg, window)

    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip(f"Clipboard Translator v{__version__}")
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
