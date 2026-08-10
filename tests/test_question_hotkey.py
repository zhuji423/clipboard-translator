from __future__ import annotations

import os
import ctypes
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import global_hotkey
from config import (
    AppConfig,
    Config,
    LlmConfig,
    load_config,
    save_manual_input_settings,
    save_question_hotkey,
)
from global_hotkey import GlobalHotkeyManager, HotkeySpec, parse_hotkey
from history_store import HistoryEntry, HistoryStore
from main import AppController

_APP = QApplication.instance() or QApplication([])


class _FakeHotkeyBackend:
    def __init__(self, rejected: str = "") -> None:
        self.rejected = rejected
        self.registered: list[str] = []
        self.unregister_count = 0

    def register(self, spec: HotkeySpec, callback) -> bool:
        self.registered.append(spec.text)
        return spec.text != self.rejected

    def unregister(self) -> None:
        self.unregister_count += 1

    def close(self) -> None:
        self.unregister()


class _FakeTimer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def isActive(self) -> bool:  # noqa: N802
        return self.started and not self.stopped


def test_parse_hotkey_canonicalizes_and_validates() -> None:
    spec = parse_hotkey("shift+control+q")
    assert spec.text == "Ctrl+Shift+Q"
    assert spec.virtual_key == ord("Q")

    for invalid in ("", "Q", "Ctrl+Shift", "Ctrl+PageDown", "Ctrl+Q+W"):
        try:
            parse_hotkey(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid shortcut: {invalid}")


def test_windows_input_structure_matches_win64_abi() -> None:
    if sys.platform == "win32" and ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(global_hotkey._INPUT) == 40


def test_rebind_rolls_back_when_new_hotkey_is_occupied() -> None:
    backend = _FakeHotkeyBackend(rejected="Ctrl+Shift+W")
    manager = GlobalHotkeyManager(backend=backend)
    try:
        assert manager.rebind("Ctrl+Shift+Q") == (True, "")

        ok, error = manager.rebind("Ctrl+Shift+W")
        assert ok is False
        assert "占用" in error
        assert manager.shortcut == "Ctrl+Shift+Q"
        assert backend.registered == [
            "Ctrl+Shift+Q",
            "Ctrl+Shift+W",
            "Ctrl+Shift+Q",
        ]
    finally:
        manager.close()
    assert backend.unregister_count == 3


def test_question_hotkey_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[llm]\nbase_url = \"https://api.example.com\"\n"
        "model = \"model\"\n\n[app]\ntarget_lang = \"zh\"\n",
        encoding="utf-8",
    )
    assert load_config(path).app.question_hotkey == "Ctrl+Shift+Q"
    save_question_hotkey("Ctrl+Alt+F8", path=path)
    assert load_config(path).app.question_hotkey == "Ctrl+Alt+F8"


def test_manual_input_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[llm]\nbase_url = \"https://api.example.com\"\n"
        "model = \"model\"\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.manual_input.hotkey == "Ctrl+M"
    assert cfg.manual_input.opacity == 0.82

    save_manual_input_settings(
        x=100,
        y=120,
        width=500,
        height=180,
        opacity=0.41,
        path=path,
    )
    cfg = load_config(path)
    assert cfg.manual_input.x == 100
    assert cfg.manual_input.y == 120
    assert cfg.manual_input.width == 500
    assert cfg.manual_input.height == 180
    assert cfg.manual_input.opacity == 0.41


def test_multiple_hotkey_managers_keep_independent_shortcuts() -> None:
    first = _FakeHotkeyBackend()
    second = _FakeHotkeyBackend()
    question = GlobalHotkeyManager(backend=first)
    manual = GlobalHotkeyManager(backend=second)
    try:
        assert question.rebind("Ctrl+Shift+Q") == (True, "")
        assert manual.rebind("Ctrl+M") == (True, "")
        assert question.shortcut == "Ctrl+Shift+Q"
        assert manual.shortcut == "Ctrl+M"
        assert first.registered == ["Ctrl+Shift+Q"]
        assert second.registered == ["Ctrl+M"]
    finally:
        question.close()
        manual.close()


def test_question_clipboard_event_is_consumed_without_translation() -> None:
    controller = SimpleNamespace()
    controller._cfg = Config(
        llm=LlmConfig("https://api.example.com", "", "model"),
        app=AppConfig(),
    )
    controller._question_capture_state = "waiting_clipboard"
    controller._question_capture_sequence = 1
    controller._selection_input = SimpleNamespace(clipboard_sequence=lambda: 2)
    controller._question_capture_timer = _FakeTimer()
    controller._question_copied_text = ""
    controller._question_copy_generation = 0
    controller._generation = 4
    captured: list[str] = []
    controller._apply_question_text = captured.append
    controller._normalize_clipboard_text = MethodType(
        AppController._normalize_clipboard_text, controller
    )
    controller._consume_question_selection = MethodType(
        AppController._consume_question_selection, controller
    )

    _APP.clipboard().setText("DeepSeek 是什么？")
    AppController.on_clipboard_changed(controller)

    assert captured == ["DeepSeek 是什么？"]
    assert controller._question_capture_state == ""
    assert controller._question_capture_timer.stopped is True

    controller._listening = True
    controller._settle_timer = _FakeTimer()
    controller._confirm_timer = _FakeTimer()
    controller._last_text = ""
    controller._ignore_clipboard_text = None
    controller._ignore_clipboard_until_ms = 0
    AppController.on_clipboard_changed(controller)
    assert controller._settle_timer.started is False


def test_ordinary_clipboard_event_keeps_translation_settle_path() -> None:
    controller = SimpleNamespace()
    controller._cfg = Config(
        llm=LlmConfig("https://api.example.com", "", "model"),
        app=AppConfig(),
    )
    controller._question_capture_state = ""
    controller._question_copied_text = ""
    controller._question_copy_generation = 0
    controller._listening = True
    controller._last_text = "旧文本"
    controller._ignore_clipboard_text = None
    controller._ignore_clipboard_until_ms = 0
    controller._pending_text = ""
    controller._confirm_text = ""
    controller._settle_timer = _FakeTimer()
    controller._confirm_timer = _FakeTimer()
    controller._normalize_clipboard_text = MethodType(
        AppController._normalize_clipboard_text, controller
    )
    controller._should_ignore_clipboard = MethodType(
        AppController._should_ignore_clipboard, controller
    )
    controller._abort_clipboard_pending = MethodType(
        AppController._abort_clipboard_pending, controller
    )

    _APP.clipboard().setText("普通复制仍然翻译")
    AppController.on_clipboard_changed(controller)

    assert controller._pending_text == "普通复制仍然翻译"
    assert controller._settle_timer.started is True


def test_history_mode_is_backward_compatible(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    store._path_for("2026-08-10").write_text(
        '{"ts":"2026-08-10 10:00:00","source":"old","result":"旧译文"}\n',
        encoding="utf-8",
    )
    store.append(
        HistoryEntry(
            ts="2026-08-10 11:00:00",
            source="question",
            result="answer",
            mode="answer",
        )
    )
    entries = store.load_day("2026-08-10")
    assert entries[0].mode == "answer"
    assert entries[1].mode == "translate"
