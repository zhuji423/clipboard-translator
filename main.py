from __future__ import annotations

import json
import re
import sys
import webbrowser
from pathlib import Path
from threading import Event

from PySide6.QtCore import QDateTime, QObject, Qt, QThread, QTimer, Signal, Slot
from dataclasses import replace

from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSystemTrayIcon,
)

from balance import BalanceError, BalanceInfo, fetch_balance
from browser_bridge import BridgeConfig, BrowserBridge
from cache import LruCache
from config import (
    BridgeSettings,
    Config,
    LlmConfig,
    load_config,
    save_bridge_settings,
    save_bridge_token,
    save_font_size,
    save_llm_settings,
)
from history import HistoryDialog
from history_store import HistoryEntry, HistoryStore, now_ts
from paths import app_icon_path, ensure_user_config, is_frozen
from platform_ui import ui_font
from pricing import estimate_cost, format_billing_line, format_status_lines
from settings_dialog import BridgeSettingsValues, LlmSettingsValues, SettingsDialog
from translator import OpenAICompatTranslator, UsageInfo
from updater import (
    RELEASES_PAGE,
    ReleaseInfo,
    UpdateError,
    detect_install_kind,
    download_and_stage,
    fetch_latest_release,
    is_newer,
    launch_apply_script,
    prepare_windows_apply,
)
from version import __version__
from window import TranslatorWindow
from word_lookup import WordLookupService, cache_key, normalize_context, normalize_word

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


class UpdateCheckWorker(QObject):
    finished = Signal(object)  # ReleaseInfo
    failed = Signal(str)
    done = Signal()

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(fetch_latest_release())
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.done.emit()


class UpdateDownloadWorker(QObject):
    progress = Signal(int, object)  # done_bytes, total_or_None
    finished = Signal(object)  # Path
    failed = Signal(str)
    done = Signal()

    def __init__(self, release: ReleaseInfo) -> None:
        super().__init__()
        self._release = release

    @Slot()
    def run(self) -> None:
        try:
            kind = detect_install_kind()
            if kind is None:
                raise UpdateError("当前运行方式不支持自动覆盖更新")
            path = download_and_stage(
                self._release,
                kind,
                on_progress=lambda done, total: self.progress.emit(done, total),
            )
            self.finished.emit(path)
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.done.emit()


class AppController(QObject):
    bridge_token_changed = Signal(str)
    bridge_lookup_recorded = Signal()
    bridge_translate_requested = Signal(str)

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
        self._update_busy = False
        self._update_thread: QThread | None = None
        self._update_progress: QProgressDialog | None = None
        self._pending_release: ReleaseInfo | None = None
        self._lookup = WordLookupService(cfg.llm)
        self._lookup_cache = LruCache(max(32, cfg.app.cache_size))
        self._settings_dialog: SettingsDialog | None = None
        self.bridge_token_changed.connect(self._apply_bridge_token_on_ui)
        self.bridge_lookup_recorded.connect(self.refresh_billing)
        self.bridge_translate_requested.connect(self._on_bridge_translate_requested)
        self._bridge = BrowserBridge(
            config_provider=self._bridge_config,
            target_lang_provider=lambda: self._cfg.app.target_lang,
            on_lookup=self._bridge_lookup,
            on_translate=lambda text: self.bridge_translate_requested.emit(text),
            on_token_saved=lambda token: self.bridge_token_changed.emit(token),
        )

        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(CLIPBOARD_SETTLE_MS)
        self._settle_timer.timeout.connect(self._on_clipboard_settled)

        self._confirm_timer = QTimer(self)
        self._confirm_timer.setSingleShot(True)
        self._confirm_timer.setInterval(CLIPBOARD_CONFIRM_MS)
        self._confirm_timer.timeout.connect(self._on_clipboard_confirmed)

        self._translator.warm_up()
        if cfg.bridge.enabled:
            self._bridge.start()

        QGuiApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        self._window.copy_btn.clicked.connect(self.copy_translation)
        self._window.history_requested.connect(self.open_history)
        self._window.settings_requested.connect(self.open_settings)
        self.refresh_billing()

    def shutdown(self) -> None:
        self._bridge.stop()

    def _bridge_config(self) -> BridgeConfig:
        b = self._cfg.bridge
        return BridgeConfig(enabled=b.enabled, port=b.port, token=b.token)

    @Slot(str)
    def _apply_bridge_token_on_ui(self, token: str) -> None:
        try:
            save_bridge_token(token)
        except Exception:
            pass
        self._cfg = replace(
            self._cfg,
            bridge=replace(self._cfg.bridge, token=token),
        )
        if self._settings_dialog is not None:
            self._settings_dialog.set_bridge_paired(bool(token))

    @Slot(str)
    def _on_bridge_translate_requested(self, text: str) -> None:
        """Apply extension phrase selection on the UI thread (same as clipboard)."""
        normalized = self._normalize_clipboard_text(text)
        if normalized is None:
            return
        self._abort_clipboard_pending()
        self._apply_clipboard_text(normalized)

    def _bridge_lookup(self, word: str, context: str, target_lang: str) -> dict:
        word = normalize_word(word)
        context = normalize_context(context)
        key = cache_key(target_lang, word, context)
        cached = self._lookup_cache.get(key)
        if cached is not None:
            try:
                data = json.loads(cached)
                if isinstance(data, dict):
                    self._record_lookup_history(
                        word,
                        context,
                        data,
                        UsageInfo(),
                        local_cache=True,
                    )
                    return data
            except Exception:
                pass

        result = self._lookup.lookup(word, context, target_lang)
        payload = result.to_dict()
        self._lookup_cache.put(key, json.dumps(payload, ensure_ascii=False))
        self._record_lookup_history(
            word,
            context,
            payload,
            result.usage,
            local_cache=False,
        )
        return payload

    def _record_lookup_history(
        self,
        word: str,
        context: str,
        payload: dict,
        usage: UsageInfo,
        *,
        local_cache: bool,
    ) -> None:
        meaning = str(payload.get("meaning_in_context") or payload.get("gloss") or "")
        source = word if not context else f"{word}  |  {context}"
        if local_cache:
            self._history.append(
                HistoryEntry(
                    ts=now_ts(),
                    source=source,
                    result=meaning,
                    note="youtube_word_lookup|local_cache",
                )
            )
            self.bridge_lookup_recorded.emit()
            return
        cost = estimate_cost(
            self._cfg.llm.model, usage.hit, usage.miss, usage.completion
        )
        self._history.append(
            HistoryEntry(
                ts=now_ts(),
                source=source,
                result=meaning,
                hit=cost.hit,
                miss=cost.miss,
                completion=cost.completion,
                cost_yuan=cost.cost_yuan,
                saved_yuan=cost.saved_yuan,
                note="youtube_word_lookup",
            )
        )
        self.bridge_lookup_recorded.emit()

    def set_listening(self, enabled: bool) -> None:
        self._listening = enabled
        if not enabled:
            self._abort_clipboard_pending()
        self._window.set_status("监听中" if enabled else "已暂停")

    @Slot()
    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self._font_size,
            self._cfg.llm,
            self._cfg.bridge,
            self._window,
        )
        self._settings_dialog = dialog
        dialog.font_size_changed.connect(self.apply_font_size)
        dialog.llm_settings_changed.connect(self.apply_llm_settings)
        dialog.bridge_settings_changed.connect(self.apply_bridge_settings)
        dialog.check_updates_requested.connect(self.check_for_updates)
        dialog.start_pairing_requested.connect(self.start_bridge_pairing)
        dialog.revoke_pairing_requested.connect(self.revoke_bridge_pairing)
        dialog.exec()
        self._settings_dialog = None

    @Slot()
    def check_for_updates(self) -> None:
        if self._update_busy:
            QMessageBox.information(self._window, "检查更新", "正在检查或下载更新，请稍候。")
            return
        self._update_busy = True
        self._window.set_status("正在检查更新…")
        thread = QThread()
        worker = UpdateCheckWorker()
        worker.moveToThread(thread)
        queued = Qt.ConnectionType.QueuedConnection
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_update_check_finished, queued)
        worker.failed.connect(self._on_update_check_failed, queued)
        worker.done.connect(thread.quit, queued)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_update_check_thread_finished)
        self._update_thread = thread
        thread.start()

    @Slot()
    def _on_update_check_thread_finished(self) -> None:
        self._update_thread = None

    @Slot(object)
    def _on_update_check_finished(self, release: object) -> None:
        if not isinstance(release, ReleaseInfo):
            self._update_busy = False
            return
        self._window.set_status("监听中" if self._listening else "已暂停")
        if not is_newer(release.version):
            QMessageBox.information(
                self._window,
                "检查更新",
                f"当前已是最新正式版（v{__version__}）。",
            )
            self._update_busy = False
            return

        kind = detect_install_kind()
        notes_preview = release.notes.strip()
        if len(notes_preview) > 400:
            notes_preview = notes_preview[:400] + "…"
        detail = f"发现新版本 v{release.version}（当前 v{__version__}）。"
        if notes_preview:
            detail += f"\n\n{notes_preview}"

        if kind is None:
            detail += (
                "\n\n当前环境不支持自动覆盖（需要 Windows 安装版或便携版）。"
                "是否打开正式版下载页？"
            )
            answer = QMessageBox.question(
                self._window,
                "检查更新",
                detail,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            self._update_busy = False
            if answer == QMessageBox.StandardButton.Yes:
                webbrowser.open(RELEASES_PAGE)
            return

        mode = "安装版（静默覆盖）" if kind.kind == "setup" else "便携版（替换 exe）"
        detail += f"\n\n将下载并更新：{mode}\n更新后会自动重启。是否继续？"
        answer = QMessageBox.question(
            self._window,
            "检查更新",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._update_busy = False
            return
        self._start_update_download(release)

    @Slot(str)
    def _on_update_check_failed(self, error: str) -> None:
        self._window.set_status("监听中" if self._listening else "已暂停")
        self._update_busy = False
        QMessageBox.warning(self._window, "检查更新", error)

    def _start_update_download(self, release: ReleaseInfo) -> None:
        self._pending_release = release
        self._update_busy = True
        progress = QProgressDialog(
            f"正在下载 v{release.version}…",
            None,
            0,
            0,
            self._window,
        )
        progress.setWindowTitle("更新")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setCancelButton(None)
        self._update_progress = progress
        progress.show()

        thread = QThread()
        worker = UpdateDownloadWorker(release)
        worker.moveToThread(thread)
        queued = Qt.ConnectionType.QueuedConnection
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_update_download_progress, queued)
        worker.finished.connect(self._on_update_download_finished, queued)
        worker.failed.connect(self._on_update_download_failed, queued)
        worker.done.connect(thread.quit, queued)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_update_download_thread_finished)
        self._update_thread = thread
        thread.start()

    @Slot()
    def _on_update_download_thread_finished(self) -> None:
        self._update_thread = None

    @Slot(int, object)
    def _on_update_download_progress(self, done: int, total: object) -> None:
        dlg = self._update_progress
        if dlg is None:
            return
        if isinstance(total, int) and total > 0:
            dlg.setRange(0, total)
            dlg.setValue(min(done, total))
            dlg.setLabelText(
                f"正在下载… {done // 1024} / {total // 1024} KB"
            )
        else:
            dlg.setRange(0, 0)
            dlg.setLabelText(f"正在下载… {done // 1024} KB")

    @Slot(object)
    def _on_update_download_finished(self, path: object) -> None:
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        self._pending_release = None
        if not isinstance(path, Path):
            self._update_busy = False
            return
        kind = detect_install_kind()
        if kind is None:
            self._update_busy = False
            QMessageBox.warning(self._window, "更新", "无法识别安装形态，已取消应用更新。")
            return
        try:
            script = prepare_windows_apply(kind, path)
            launch_apply_script(script)
        except Exception as exc:  # noqa: BLE001
            self._update_busy = False
            QMessageBox.critical(self._window, "更新", f"无法启动更新脚本：{exc}")
            return
        QApplication.quit()

    @Slot(str)
    def _on_update_download_failed(self, error: str) -> None:
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        self._pending_release = None
        self._update_busy = False
        QMessageBox.warning(self._window, "更新", error)

    @Slot(int)
    def apply_font_size(self, size: int) -> None:
        self._font_size = size
        self._window.apply_font_size(size)
        if self._history_dialog is not None:
            self._history_dialog.apply_font_size(size)
        save_font_size(size)

    @Slot(object)
    def apply_llm_settings(self, values: object) -> None:
        if not isinstance(values, LlmSettingsValues):
            return
        try:
            save_llm_settings(values.base_url, values.api_key, values.model)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self._window, "设置", f"保存配置失败：{exc}")
            return

        self._cancel_current()
        self._generation += 1
        llm = replace(
            self._cfg.llm,
            base_url=values.base_url,
            api_key=values.api_key,
            model=values.model,
        )
        self._cfg = replace(self._cfg, llm=llm)
        self._translator = OpenAICompatTranslator(
            llm, target_lang=self._cfg.app.target_lang
        )
        self._lookup.update_config(llm)
        self._translator.warm_up()
        self.refresh_billing()

    @Slot(object)
    def apply_bridge_settings(self, values: object) -> None:
        if not isinstance(values, BridgeSettingsValues):
            return
        try:
            save_bridge_settings(values.enabled, values.port)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self._window, "设置", f"保存浏览器集成失败：{exc}")
            return
        self._cfg = replace(
            self._cfg,
            bridge=BridgeSettings(
                enabled=values.enabled,
                port=values.port,
                token=self._cfg.bridge.token,
            ),
        )
        self._bridge.restart()

    @Slot()
    def start_bridge_pairing(self) -> None:
        # Ensure bridge is enabled before pairing.
        if not self._cfg.bridge.enabled:
            try:
                save_bridge_settings(True, self._cfg.bridge.port)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self._window, "配对", f"无法启用桥接：{exc}")
                return
            self._cfg = replace(
                self._cfg,
                bridge=replace(self._cfg.bridge, enabled=True),
            )
            if self._settings_dialog is not None:
                self._settings_dialog.bridge_enabled.setChecked(True)
            self._bridge.restart()
        try:
            info = self._bridge.begin_pairing()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self._window, "配对", str(exc))
            return
        if self._settings_dialog is not None:
            self._settings_dialog.set_pair_code(
                str(info["code"]),
                int(info["port"]),
                int(info["expires_in"]),
            )

    @Slot()
    def revoke_bridge_pairing(self) -> None:
        self._bridge.revoke_token()
        if self._settings_dialog is not None:
            self._settings_dialog.set_bridge_paired(False)
        QMessageBox.information(self._window, "配对", "已撤销浏览器配对令牌。")

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
        text = re.sub(r"\s+", " ", raw).strip()
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


def _fallback_app_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#3c78d8"))
    painter.setPen(QColor("#3c78d8"))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor("white"))
    painter.setFont(ui_font(22, QFont.Weight.Bold))
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "译")
    painter.end()
    return QIcon(pix)


def _load_app_icon() -> QIcon:
    path = app_icon_path()
    if path.is_file():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return _fallback_app_icon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Clipboard Translator")
    app_icon = _load_app_icon()
    app.setWindowIcon(app_icon)

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
            "请在「设置」中填写 API URL、API Key 与模型名后再使用翻译。\n"
            "也可直接编辑该配置文件。",
        )

    window = TranslatorWindow(
        always_on_top=cfg.app.always_on_top,
        font_size=cfg.app.font_size,
    )
    window.setWindowIcon(app_icon)
    controller = AppController(cfg, window)

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
    act_update = QAction("检查更新", menu)
    act_update.triggered.connect(controller.check_for_updates)
    menu.addAction(act_update)

    menu.addSeparator()
    act_quit = QAction("退出", menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)

    tray: QSystemTrayIcon | None = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(app_icon, app)
        tray.setToolTip(f"Clipboard Translator v{__version__}")
        tray.setContextMenu(menu)

        def on_tray_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
            if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
            ):
                # Context menu remains via setContextMenu (right-click /
                # macOS menu-bar click patterns vary by OS).
                window.show_and_raise()

        tray.activated.connect(on_tray_activated)
        tray.show()
    else:
        QMessageBox.information(
            window,
            "系统托盘不可用",
            "当前环境没有系统托盘。主窗口将保持显示；请从窗口关闭应用进程。",
        )

    window.set_status("监听中")
    window.show()
    code = app.exec()
    controller.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
