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
    QWidget,
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
    save_manual_input_settings,
    save_question_hotkey,
)
from distribution import ONBOARDING_URL, preferred_extension_install_url
from native_messaging import register_native_messaging_host
from history import HistoryDialog
from history_store import HistoryEntry, HistoryStore, now_ts
from macos_clipboard import MacClipboardPoller
from global_hotkey import GlobalHotkeyManager, WindowsSelectionInput
from manual_input_window import ManualInputWindow
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
    format_release_date,
    format_version_with_date,
    is_newer,
    launch_apply_script,
    local_changelog_date,
    prepare_windows_apply,
)
from version import __version__
from window import TranslatorWindow
from word_lookup import WordLookupService, cache_key, normalize_context, normalize_word

CLIPBOARD_SETTLE_MS = 350
CLIPBOARD_CONFIRM_MS = 800
COPY_IGNORE_MS = 300
QUESTION_CAPTURE_TIMEOUT_MS = 1200
QUESTION_CAPTURE_POLL_MS = 20
QUESTION_COPY_RELEASE_MS = 1000
MANUAL_INPUT_HOTKEY_ID = 0x434D


class TranslateWorker(QObject):
    delta = Signal(int, str)  # generation, chunk
    finished = Signal(int, str, str, str, object)  # generation, mode, source, result, usage
    failed = Signal(int, str)  # generation, error
    done = Signal()

    def __init__(
        self,
        translator: OpenAICompatTranslator,
        text: str,
        target_lang: str,
        cancel_event: Event,
        generation: int,
        mode: str = "translate",
    ) -> None:
        super().__init__()
        self._translator = translator
        self._text = text
        self._target_lang = target_lang
        self._cancel_event = cancel_event
        self._generation = generation
        self._mode = mode

    @Slot()
    def run(self) -> None:
        try:
            method = (
                self._translator.answer_stream
                if self._mode == "answer"
                else self._translator.translate_stream
            )
            result = method(
                self._text,
                self._target_lang,
                self._cancel_event,
                on_delta=lambda chunk: self.delta.emit(self._generation, chunk),
            )
            if not self._cancel_event.is_set():
                self.finished.emit(
                    self._generation,
                    self._mode,
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
        self._answerer = OpenAICompatTranslator(
            cfg.llm, target_lang=cfg.app.target_lang, mode="answer"
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
        self._tasks: dict[int, tuple[QThread, TranslateWorker]] = {}
        self._current_mode = "translate"
        self._question_capture_state = ""
        self._question_capture_sequence = 0
        self._question_capture_deadline_ms = 0
        self._question_copied_text = ""
        self._question_copy_generation = 0
        self._billing_generation = 0
        self._billing_thread: QThread | None = None
        self._billing_worker: BalanceWorker | None = None
        self._billing_pending = False
        self._billing_fetching = False
        self._remaining_yuan: float | None = None
        self._balance_error: str | None = None
        self._update_busy = False
        self._update_check_thread: QThread | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_download_thread: QThread | None = None
        self._update_download_worker: UpdateDownloadWorker | None = None
        self._update_progress: QProgressDialog | None = None
        self._pending_release: ReleaseInfo | None = None
        self._lookup = WordLookupService(cfg.llm)
        self._lookup_cache = LruCache(max(32, cfg.app.cache_size))
        self._settings_dialog: SettingsDialog | None = None
        self._hotkey_manager = GlobalHotkeyManager(parent=self)
        self._manual_input_hotkey_manager = GlobalHotkeyManager(
            parent=self,
            hotkey_id=MANUAL_INPUT_HOTKEY_ID,
        )
        self._selection_input = (
            WindowsSelectionInput() if self._hotkey_manager.supported else None
        )
        self._question_hotkey_error = ""
        self._manual_input_hotkey_error = ""
        self._hotkey_manager.activated.connect(self.capture_question_selection)
        self._manual_input_hotkey_manager.activated.connect(self.show_manual_input)
        if self._hotkey_manager.supported:
            registered, error = self._hotkey_manager.rebind(
                cfg.app.question_hotkey
            )
            if not registered:
                self._question_hotkey_error = error
        if self._manual_input_hotkey_manager.supported:
            registered, error = self._manual_input_hotkey_manager.rebind(
                cfg.manual_input.hotkey
            )
            if not registered:
                self._manual_input_hotkey_error = error
        self._manual_input_window = ManualInputWindow(
            x=cfg.manual_input.x,
            y=cfg.manual_input.y,
            width=cfg.manual_input.width,
            height=cfg.manual_input.height,
            opacity=cfg.manual_input.opacity,
        )
        self._manual_input_window.submitted.connect(
            self._on_manual_input_submitted
        )
        self._manual_input_window.state_changed.connect(
            self._save_manual_input_state
        )
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

        self._question_capture_timer = QTimer(self)
        self._question_capture_timer.setInterval(QUESTION_CAPTURE_POLL_MS)
        self._question_capture_timer.timeout.connect(
            self._poll_question_selection_capture
        )

        self._translator.warm_up()
        self._answerer.warm_up()
        if cfg.bridge.enabled:
            self._bridge.start()

        QGuiApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        # macOS: Qt only delivers cross-app clipboard changes when activated;
        # poll NSPasteboard.changeCount so menu-bar / background copy still works.
        self._mac_clip_poller: MacClipboardPoller | None = None
        if sys.platform == "darwin":
            self._mac_clip_poller = MacClipboardPoller(parent=self)
            self._mac_clip_poller.changed.connect(self.on_clipboard_changed)
            self._mac_clip_poller.start()
        self._window.copy_btn.clicked.connect(self.copy_translation)
        self._window.clear_answer_requested.connect(self.clear_answer_context)
        self._window.history_requested.connect(self.open_history)
        self._window.settings_requested.connect(self.open_settings)
        self.refresh_billing()

    def shutdown(self) -> None:
        if self._mac_clip_poller is not None:
            self._mac_clip_poller.stop()
        self._question_capture_timer.stop()
        self._hotkey_manager.close()
        self._manual_input_hotkey_manager.close()
        self._manual_input_window.close()
        self._cancel_current()
        self._bridge.stop()

    @property
    def question_hotkey_error(self) -> str:
        return self._question_hotkey_error

    @property
    def manual_input_hotkey_error(self) -> str:
        return self._manual_input_hotkey_error

    @Slot()
    def show_manual_input(self) -> None:
        self._manual_input_window.show_prompt()

    @Slot(str)
    def _on_manual_input_submitted(self, text: str) -> None:
        normalized = self._normalize_clipboard_text(text)
        if normalized is None:
            self._window.show_raised()
            self._window.set_status("输入内容太短或为空", error=True)
            return
        self._abort_clipboard_pending()
        self._apply_clipboard_text(normalized)

    @Slot(int, int, int, int, float)
    def _save_manual_input_state(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        opacity: float,
    ) -> None:
        try:
            save_manual_input_settings(
                x=x,
                y=y,
                width=width,
                height=height,
                opacity=opacity,
            )
        except Exception:
            pass

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
    def capture_question_selection(self) -> None:
        if self._selection_input is None:
            self._window.set_status("全局问答快捷键当前仅支持 Windows", error=True)
            return
        self._abort_clipboard_pending()
        self._invalidate_inflight()
        self._question_capture_state = "waiting_release"
        self._question_capture_deadline_ms = (
            QDateTime.currentMSecsSinceEpoch() + QUESTION_CAPTURE_TIMEOUT_MS
        )
        self._window.set_mode("answer")
        self._window.set_status("正在复制问题…")
        self._question_capture_timer.start()

    @Slot()
    def _poll_question_selection_capture(self) -> None:
        if not self._question_capture_state or self._selection_input is None:
            self._question_capture_timer.stop()
            return
        if QDateTime.currentMSecsSinceEpoch() >= self._question_capture_deadline_ms:
            self._fail_question_selection_capture()
            return

        if self._question_capture_state == "waiting_release":
            if not self._selection_input.modifiers_released():
                return
            self._question_capture_sequence = (
                self._selection_input.clipboard_sequence()
            )
            self._question_capture_state = "waiting_clipboard"
            if not self._selection_input.send_copy():
                self._fail_question_selection_capture("无法发送复制快捷键")
            return

        if (
            self._selection_input.clipboard_sequence()
            != self._question_capture_sequence
        ):
            self._consume_question_selection()

    def _consume_question_selection(self) -> None:
        text = self._normalize_clipboard_text(QGuiApplication.clipboard().text())
        self._question_capture_state = ""
        self._question_capture_timer.stop()
        if text is None:
            self._fail_question_selection_capture()
            return
        self._question_copied_text = text
        self._apply_question_text(text)
        self._question_copy_generation = self._generation

    def _fail_question_selection_capture(
        self, message: str = "未检测到选中文本"
    ) -> None:
        self._question_capture_state = ""
        self._question_capture_timer.stop()
        self._window.show_raised()
        self._window.set_status(message, error=True)

    def apply_question_hotkey(self, hotkey: str) -> tuple[bool, str]:
        old_hotkey = self._cfg.app.question_hotkey
        registered, error = self._hotkey_manager.rebind(hotkey)
        if not registered:
            return False, error
        try:
            save_question_hotkey(self._hotkey_manager.shortcut)
        except Exception as exc:  # noqa: BLE001
            self._hotkey_manager.rebind(old_hotkey)
            return False, f"保存问答快捷键失败：{exc}"
        self._cfg = replace(
            self._cfg,
            app=replace(
                self._cfg.app,
                question_hotkey=self._hotkey_manager.shortcut,
            ),
        )
        self._question_hotkey_error = ""
        return True, ""

    @Slot()
    def clear_answer_context(self) -> None:
        self._invalidate_inflight()
        self._answerer.reset_context()
        if self._window.mode == "answer":
            self._window.set_status("问答上下文已清空")

    @Slot()
    def open_settings(self) -> None:
        dialog = SettingsDialog(
            font_size=self._font_size,
            llm=self._cfg.llm,
            bridge=self._cfg.bridge,
            question_hotkey=self._cfg.app.question_hotkey,
            question_hotkey_applier=self.apply_question_hotkey,
            parent=self._window,
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

    def _update_message_parent(self) -> QWidget:
        if self._settings_dialog is not None:
            return self._settings_dialog
        return self._window

    def _set_update_checking_ui(
        self, checking: bool, *, status: str | None = None
    ) -> None:
        dlg = self._settings_dialog
        if dlg is not None:
            dlg.set_update_checking(checking, status=status)

    def _finish_update_check_ui(self) -> None:
        self._update_busy = False
        self._set_update_checking_ui(False)
        self._window.set_status("监听中" if self._listening else "已暂停")

    @Slot()
    def check_for_updates(self) -> None:
        if self._update_busy:
            # Already checking/downloading; avoid a misleading "please wait" popup.
            return
        self._update_busy = True
        self._set_update_checking_ui(True)
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
        thread.destroyed.connect(self._on_update_check_thread_destroyed)
        self._update_check_thread = thread
        self._update_check_worker = worker
        thread.start()

    @Slot()
    def _on_update_check_thread_destroyed(self) -> None:
        self._update_check_thread = None
        self._update_check_worker = None

    @Slot(object)
    def _on_update_check_finished(self, release: object) -> None:
        if not isinstance(release, ReleaseInfo):
            self._finish_update_check_ui()
            return
        remote_date = format_release_date(release.published_at)
        local_date = local_changelog_date(__version__)
        parent = self._update_message_parent()
        if not is_newer(release.version):
            shown = format_version_with_date(
                __version__, remote_date or local_date
            )
            self._finish_update_check_ui()
            QMessageBox.information(
                parent,
                "检查更新",
                f"当前已是最新正式版（{shown}）。",
            )
            return

        kind = detect_install_kind()
        notes_preview = release.notes.strip()
        if len(notes_preview) > 400:
            notes_preview = notes_preview[:400] + "…"
        remote_label = format_version_with_date(release.version, remote_date)
        local_label = format_version_with_date(__version__, local_date)
        detail = f"发现新版本 {remote_label}（当前 {local_label}）。"
        if notes_preview:
            detail += f"\n\n{notes_preview}"

        if kind is None:
            detail += (
                "\n\n当前环境不支持自动覆盖（需要 Windows 安装版或便携版）。"
                "是否打开该版本的 GitHub 发布页？"
            )
            self._finish_update_check_ui()
            answer = QMessageBox.question(
                parent,
                "检查更新",
                detail,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                webbrowser.open(release.html_url or RELEASES_PAGE)
            return

        mode = "安装版（静默覆盖）" if kind.kind == "setup" else "便携版（替换 exe）"
        detail += f"\n\n将下载并更新：{mode}\n更新后会自动重启。是否继续？"
        self._finish_update_check_ui()
        answer = QMessageBox.question(
            parent,
            "检查更新",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_update_download(release)

    @Slot(str)
    def _on_update_check_failed(self, error: str) -> None:
        parent = self._update_message_parent()
        self._finish_update_check_ui()
        QMessageBox.warning(parent, "检查更新", error)

    def _start_update_download(self, release: ReleaseInfo) -> None:
        self._pending_release = release
        self._update_busy = True
        self._set_update_checking_ui(True, status="正在下载…")
        parent = self._update_message_parent()
        progress = QProgressDialog(
            f"正在下载 v{release.version}…",
            None,
            0,
            0,
            parent,
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
        thread.destroyed.connect(self._on_update_download_thread_destroyed)
        self._update_download_thread = thread
        self._update_download_worker = worker
        thread.start()

    @Slot()
    def _on_update_download_thread_destroyed(self) -> None:
        self._update_download_thread = None
        self._update_download_worker = None

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
        parent = self._update_message_parent()
        if not isinstance(path, Path):
            self._finish_update_check_ui()
            return
        kind = detect_install_kind()
        if kind is None:
            self._finish_update_check_ui()
            QMessageBox.warning(
                parent, "更新", "无法识别安装形态，已取消应用更新。"
            )
            return
        try:
            script = prepare_windows_apply(kind, path)
            launch_apply_script(script)
        except Exception as exc:  # noqa: BLE001
            self._finish_update_check_ui()
            QMessageBox.critical(parent, "更新", f"无法启动更新脚本：{exc}")
            return
        QApplication.quit()

    @Slot(str)
    def _on_update_download_failed(self, error: str) -> None:
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        self._pending_release = None
        parent = self._update_message_parent()
        self._finish_update_check_ui()
        QMessageBox.warning(parent, "更新", error)

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
        self._answerer = OpenAICompatTranslator(
            llm, target_lang=self._cfg.app.target_lang, mode="answer"
        )
        self._lookup.update_config(llm)
        self._translator.warm_up()
        self._answerer.warm_up()
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
        if entry.mode == "translate":
            self._last_text = entry.source.strip()
        self._current_mode = entry.mode
        self._window.set_mode(entry.mode)
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
        copied_name = "回答" if self._window.mode == "answer" else "译文"
        self._window.set_status(f"已复制{copied_name}")

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
        if self._question_capture_state:
            if (
                self._question_capture_state == "waiting_clipboard"
                and self._selection_input is not None
                and self._selection_input.clipboard_sequence()
                != self._question_capture_sequence
            ):
                self._consume_question_selection()
            return
        if self._question_copied_text:
            repeated = self._normalize_clipboard_text(
                QGuiApplication.clipboard().text()
            )
            if repeated == self._question_copied_text:
                return
            self._question_copied_text = ""
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
        self._current_mode = "translate"
        self._window.show_raised()
        self._invalidate_inflight()
        self._window.set_mode("translate")
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
                    mode="translate",
                    note="local_cache",
                )
            )
            self.refresh_billing()
            return

        self._start_request(text, "translate")

    def _apply_question_text(self, text: str) -> None:
        self._current_mode = "answer"
        self._window.show_raised()
        self._invalidate_inflight()
        self._window.set_mode("answer")
        self._window.set_source(text)
        self._window.clear_result()
        self._start_request(text, "answer")

    def _start_translate(self, text: str) -> None:
        self._start_request(text, "translate")

    def _start_request(self, text: str, mode: str) -> None:
        generation = self._generation
        cancel_event = Event()
        self._cancel_event = cancel_event

        thread = QThread()
        session = self._answerer if mode == "answer" else self._translator
        worker = TranslateWorker(
            session,
            text,
            self._cfg.app.target_lang,
            cancel_event,
            generation,
            mode,
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
        thread.destroyed.connect(
            lambda _obj=None, generation=generation: self._on_task_thread_destroyed(
                generation
            )
        )

        self._thread = thread
        self._worker = worker
        self._tasks[generation] = (thread, worker)
        self._window.set_status("回答中…" if mode == "answer" else "翻译中…")
        thread.start()

    def _on_task_thread_destroyed(self, generation: int) -> None:
        refs = self._tasks.pop(generation, None)
        if refs is not None and self._thread is refs[0]:
            self._thread = None
            self._worker = None

    def _cancel_current(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    @Slot(int, str)
    def _on_delta(self, generation: int, chunk: str) -> None:
        if generation != self._generation:
            return
        self._window.append_result(chunk)

    @Slot(int, str, str, str, object)
    def _on_finished(
        self,
        generation: int,
        mode: str,
        source: str,
        result: str,
        usage: object,
    ) -> None:
        if generation != self._generation:
            return
        info = usage if isinstance(usage, UsageInfo) else UsageInfo()
        if result:
            self._window.set_result(result)
            if mode == "translate":
                self._cache.put(
                    f"{self._cfg.app.target_lang}\n{source}", result
                )
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
                    mode=("answer" if mode == "answer" else "translate"),
                    hit=cost.hit,
                    miss=cost.miss,
                    completion=cost.completion,
                    cost_yuan=cost.cost_yuan,
                    saved_yuan=cost.saved_yuan,
                    note="",
                )
            )
        self.refresh_billing()
        if mode == "answer":
            QTimer.singleShot(
                QUESTION_COPY_RELEASE_MS,
                lambda generation=generation: self._release_question_copy(
                    generation
                ),
            )

    @Slot(int, str)
    def _on_failed(self, generation: int, error: str) -> None:
        if generation != self._generation:
            return
        self._window.set_status(f"失败: {error}", error=True)
        if self._current_mode == "answer":
            QTimer.singleShot(
                QUESTION_COPY_RELEASE_MS,
                lambda generation=generation: self._release_question_copy(
                    generation
                ),
            )

    def _release_question_copy(self, generation: int) -> None:
        if generation == self._question_copy_generation:
            self._question_copied_text = ""

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
        thread.destroyed.connect(self._on_billing_thread_destroyed)

        self._billing_thread = thread
        self._billing_worker = worker
        thread.start()

    @Slot()
    def _on_billing_thread_destroyed(self) -> None:
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

    if is_frozen():
        try:
            register_native_messaging_host()
        except Exception:  # noqa: BLE001
            pass

    if created and is_frozen():
        QMessageBox.information(
            None,
            "首次运行",
            f"已创建配置文件：\n{cfg_path}\n\n"
            "请在「设置」中填写 API URL、API Key 与模型名后再使用翻译。\n"
            "也可直接编辑该配置文件。\n\n"
            "接下来将打开浏览器扩展安装引导页（需在商店中确认添加扩展）。",
        )
        try:
            webbrowser.open(ONBOARDING_URL)
        except Exception:  # noqa: BLE001
            pass

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

    act_manual_input = QAction("手动输入翻译", menu)
    act_manual_input.triggered.connect(controller.show_manual_input)
    menu.addAction(act_manual_input)

    act_settings = QAction("设置", menu)
    act_settings.triggered.connect(controller.open_settings)
    menu.addAction(act_settings)

    act_history = QAction("历史记录", menu)
    act_history.triggered.connect(controller.open_history)
    menu.addAction(act_history)

    act_clear_answer = QAction("清空问答上下文", menu)
    act_clear_answer.triggered.connect(controller.clear_answer_context)
    menu.addAction(act_clear_answer)

    act_pause = QAction("暂停监听", menu)
    act_pause.setCheckable(True)

    def on_pause_toggled(checked: bool) -> None:
        controller.set_listening(not checked)
        act_pause.setText("继续监听" if checked else "暂停监听")

    act_pause.toggled.connect(on_pause_toggled)
    menu.addAction(act_pause)

    menu.addSeparator()
    act_ext = QAction("安装浏览器扩展", menu)
    act_ext.triggered.connect(lambda: webbrowser.open(preferred_extension_install_url()))
    menu.addAction(act_ext)

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
        if controller.question_hotkey_error:
            tray.showMessage(
                "问答快捷键不可用",
                controller.question_hotkey_error,
                QSystemTrayIcon.MessageIcon.Warning,
                8000,
            )
        if controller.manual_input_hotkey_error:
            tray.showMessage(
                "手动输入快捷键不可用",
                controller.manual_input_hotkey_error,
                QSystemTrayIcon.MessageIcon.Warning,
                8000,
            )
        if is_frozen() and cfg.bridge.enabled and not (cfg.bridge.token or "").strip():
            tray.showMessage(
                "Clipboard Translator",
                "浏览器扩展尚未配对：托盘菜单可打开安装引导；安装后一般会自动连接。",
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )
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
