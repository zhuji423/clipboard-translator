"""macOS NSWindow tweaks for overlay / fullscreen Spaces.

Qt WindowStaysOnTopHint alone stays on the desktop Space; native fullscreen
apps use another Space, so the translator disappears. Joining all Spaces as a
fullScreenAuxiliary window fixes that. Windows is unchanged.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

from PySide6.QtWidgets import QWidget

# NSWindowCollectionBehavior
_CAN_JOIN_ALL_SPACES = 1 << 0
_FULL_SCREEN_AUXILIARY = 1 << 8
_OVERLAY_BEHAVIOR = _CAN_JOIN_ALL_SPACES | _FULL_SCREEN_AUXILIARY


def apply_overlay_space_behavior(widget: QWidget) -> bool:
    """Let a Qt window appear on top of macOS fullscreen Spaces. No-op elsewhere."""
    if sys.platform != "darwin":
        return False
    try:
        wid = int(widget.winId())
        if wid == 0:
            return False

        appkit = ctypes.util.find_library("AppKit")
        objc_path = ctypes.util.find_library("objc")
        if not appkit or not objc_path:
            return False
        ctypes.cdll.LoadLibrary(appkit)
        libobjc = ctypes.cdll.LoadLibrary(objc_path)

        libobjc.objc_getClass.argtypes = [ctypes.c_char_p]
        libobjc.objc_getClass.restype = ctypes.c_void_p
        libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
        libobjc.sel_registerName.restype = ctypes.c_void_p

        msg = libobjc.objc_msgSend
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        msg.restype = ctypes.c_void_p

        ns_window = msg(ctypes.c_void_p(wid), libobjc.sel_registerName(b"window"))
        if not ns_window:
            return False

        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        msg.restype = None
        msg(
            ns_window,
            libobjc.sel_registerName(b"setCollectionBehavior:"),
            _OVERLAY_BEHAVIOR,
        )
        return True
    except Exception:  # noqa: BLE001
        return False
