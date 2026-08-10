"""macOS pasteboard change polling.

Qt's QClipboard.dataChanged on macOS only reports changes made by other apps
when this process is activated. Background / menu-bar use therefore needs a
native changeCount poll. Windows keeps using QClipboard alone.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

_POLL_MS = 300


def pasteboard_change_count() -> int | None:
    """Return NSPasteboard.generalPasteboard.changeCount, or None on failure."""
    if sys.platform != "darwin":
        return None
    try:
        appkit = ctypes.util.find_library("AppKit")
        objc_path = ctypes.util.find_library("objc")
        if not appkit or not objc_path:
            return None
        ctypes.cdll.LoadLibrary(appkit)
        libobjc = ctypes.cdll.LoadLibrary(objc_path)

        libobjc.objc_getClass.argtypes = [ctypes.c_char_p]
        libobjc.objc_getClass.restype = ctypes.c_void_p
        libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
        libobjc.sel_registerName.restype = ctypes.c_void_p

        msg = libobjc.objc_msgSend
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        msg.restype = ctypes.c_void_p

        ns_pasteboard = libobjc.objc_getClass(b"NSPasteboard")
        if not ns_pasteboard:
            return None
        pasteboard = msg(ns_pasteboard, libobjc.sel_registerName(b"generalPasteboard"))
        if not pasteboard:
            return None

        msg.restype = ctypes.c_long
        return int(msg(pasteboard, libobjc.sel_registerName(b"changeCount")))
    except Exception:  # noqa: BLE001
        return None


class MacClipboardPoller(QObject):
    """Emit when the general pasteboard changeCount advances."""

    changed = Signal()

    def __init__(
        self,
        interval_ms: int = _POLL_MS,
        count_provider: Callable[[], int | None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._count_provider = count_provider or pasteboard_change_count
        self._last_count: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(max(100, interval_ms))
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._last_count = self._count_provider()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        count = self._count_provider()
        if count is None:
            return
        if self._last_count is None:
            self._last_count = count
            return
        if count != self._last_count:
            self._last_count = count
            self.changed.emit()
