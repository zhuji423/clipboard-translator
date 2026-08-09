from __future__ import annotations

import gc
import os
import time
import weakref
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QWidget

import main
import updater
from main import AppController
from updater import InstallKind, ReleaseInfo, UpdateError, prepare_windows_apply

_APP = QApplication.instance() or QApplication([])


class _Window(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.status = ""

    def set_status(self, value: str) -> None:
        self.status = value


def _app() -> QApplication:
    return _APP


def _controller() -> AppController:
    controller = AppController.__new__(AppController)
    QObject.__init__(controller)
    controller._window = _Window()
    controller._listening = True
    controller._settings_dialog = None
    controller._update_busy = False
    controller._update_check_thread = None
    controller._update_check_worker = None
    controller._update_download_thread = None
    controller._update_download_worker = None
    controller._update_progress = None
    controller._pending_release = None
    return controller


def _wait_until(predicate, timeout: float = 3.0) -> None:
    app = _app()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Qt condition was not reached before timeout")


def test_update_check_worker_is_retained_until_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    controller = _controller()
    gate = Event()
    messages: list[str] = []
    release = ReleaseInfo(
        version="0.9.3",
        tag="v0.9.3",
        notes="",
        setup_url="https://example.invalid/setup.exe",
        portable_url="https://example.invalid/portable.exe",
        setup_size=1,
        portable_size=1,
    )

    def fetch() -> ReleaseInfo:
        assert gate.wait(2)
        return release

    monkeypatch.setattr(main, "fetch_latest_release", fetch)
    monkeypatch.setattr(
        main.QMessageBox,
        "information",
        lambda _parent, _title, text: messages.append(text),
    )

    controller.check_for_updates()
    worker_ref = weakref.ref(controller._update_check_worker)
    gc.collect()
    assert worker_ref() is not None
    assert controller._update_busy is True

    gate.set()
    _wait_until(lambda: bool(messages))
    _wait_until(lambda: controller._update_check_thread is None)

    assert "当前已是最新正式版" in messages[0]
    assert controller._update_busy is False
    assert controller._update_check_worker is None
    assert controller._window.status == "监听中"
    controller._window.close()


def test_update_check_failure_restores_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    controller = _controller()
    warnings: list[str] = []

    def fetch() -> ReleaseInfo:
        raise UpdateError("模拟 GitHub 连接失败")

    monkeypatch.setattr(main, "fetch_latest_release", fetch)
    monkeypatch.setattr(
        main.QMessageBox,
        "warning",
        lambda _parent, _title, text: warnings.append(text),
    )

    controller.check_for_updates()
    _wait_until(lambda: bool(warnings))
    _wait_until(lambda: controller._update_check_thread is None)

    assert warnings == ["模拟 GitHub 连接失败"]
    assert controller._update_busy is False
    assert controller._update_check_worker is None
    assert controller._window.status == "监听中"
    controller._window.close()


def test_update_download_worker_is_retained_until_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app()
    controller = _controller()
    gate = Event()
    warnings: list[str] = []
    release = ReleaseInfo(
        version="9.9.9",
        tag="v9.9.9",
        notes="",
        setup_url="https://example.invalid/setup.exe",
        portable_url="https://example.invalid/portable.exe",
        setup_size=1,
        portable_size=1,
    )

    monkeypatch.setattr(main, "detect_install_kind", lambda: object())

    def download(_release, _kind, *, on_progress=None):
        assert gate.wait(2)
        raise UpdateError("模拟下载失败")

    monkeypatch.setattr(main, "download_and_stage", download)
    monkeypatch.setattr(
        main.QMessageBox,
        "warning",
        lambda _parent, _title, text: warnings.append(text),
    )

    controller._start_update_download(release)
    worker_ref = weakref.ref(controller._update_download_worker)
    gc.collect()
    assert worker_ref() is not None
    assert controller._update_busy is True

    gate.set()
    _wait_until(lambda: bool(warnings))
    _wait_until(lambda: controller._update_download_thread is None)

    assert warnings == ["模拟下载失败"]
    assert controller._update_busy is False
    assert controller._update_download_worker is None
    assert controller._update_progress is None
    controller._window.close()


def test_apply_script_retries_copy_without_external_pid_polling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updater.os, "getpid", lambda: 424242)
    monkeypatch.setattr(updater.tempfile, "gettempdir", lambda: str(tmp_path))
    kind = InstallKind(
        kind="portable",
        target_exe=tmp_path / "ClipboardTranslator.exe",
        relaunch_exe=tmp_path / "ClipboardTranslator.exe",
    )

    script = prepare_windows_apply(kind, tmp_path / "new-portable.exe")
    text = script.read_text(encoding="utf-8-sig")

    assert "tasklist" not in text
    assert "find \"%PID%\"" not in text
    assert ":copy" in text
    assert "if not errorlevel 1 goto copied" in text
    assert "if %RETRIES% GEQ 500 goto copy_failed" in text
    assert "goto cleanup" in text
