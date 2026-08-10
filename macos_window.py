"""macOS fullscreen Space overlay via an invisible NSPanel anchor.

Qt WindowStaysOnTopHint alone keeps the translator on the desktop Space.
On current macOS, fullScreenAuxiliary is honored only for NSPanel; applying
it to a plain NSWindow (what QMainWindow creates) still pins the window to
the desktop Space. Fix: attach the Qt window as a child of an invisible
non-activating NSPanel that carries canJoinAllSpaces | fullScreenAuxiliary.
Child windows follow their parent onto fullscreen Spaces. Windows unchanged.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from typing import Any

from PySide6.QtWidgets import QWidget

# NSWindowCollectionBehavior
_CAN_JOIN_ALL_SPACES = 1 << 0
_FULL_SCREEN_AUXILIARY = 1 << 8
_OVERLAY_BEHAVIOR = _CAN_JOIN_ALL_SPACES | _FULL_SCREEN_AUXILIARY

# NSWindowStyleMask
_BORDERLESS = 0
_NONACTIVATING_PANEL = 1 << 7
_PANEL_STYLE = _BORDERLESS | _NONACTIVATING_PANEL

# NSWindowOrderingMode
_ORDERED_ABOVE = 1

# Module-level anchor panel (app lifetime; intentionally retained).
_anchor_panel: ctypes.c_void_p | None = None
_libobjc: Any = None


def _ensure_objc() -> Any | None:
    global _libobjc
    if _libobjc is not None:
        return _libobjc
    if sys.platform != "darwin":
        return None
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
    _libobjc = libobjc
    return libobjc


def _sel(libobjc: Any, name: bytes) -> ctypes.c_void_p:
    return libobjc.sel_registerName(name)


def _msg(libobjc: Any) -> Any:
    return libobjc.objc_msgSend


def _ns_window_from_widget(widget: QWidget, libobjc: Any) -> ctypes.c_void_p | None:
    wid = int(widget.winId())
    if wid == 0:
        return None
    msg = _msg(libobjc)
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    msg.restype = ctypes.c_void_p
    ns_window = msg(ctypes.c_void_p(wid), _sel(libobjc, b"window"))
    return ns_window or None


def _get_or_create_anchor(libobjc: Any, level: int) -> ctypes.c_void_p | None:
    """Invisible 1x1 non-activating NSPanel singleton for Space membership."""
    global _anchor_panel
    if _anchor_panel:
        return _anchor_panel

    msg = _msg(libobjc)
    cls = libobjc.objc_getClass(b"NSPanel")
    if not cls:
        return None

    # alloc
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    msg.restype = ctypes.c_void_p
    panel = msg(cls, _sel(libobjc, b"alloc"))
    if not panel:
        return None

    # init — avoid NSRect / NSSize struct args (unreliable via ctypes on arm64)
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    msg.restype = ctypes.c_void_p
    panel = msg(panel, _sel(libobjc, b"init"))
    if not panel:
        return None

    # retain for app lifetime
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    msg.restype = ctypes.c_void_p
    panel = msg(panel, _sel(libobjc, b"retain"))
    if not panel:
        return None

    # setStyleMask: Borderless | NonactivatingPanel
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    msg.restype = None
    msg(panel, _sel(libobjc, b"setStyleMask:"), _PANEL_STYLE)

    # collection behavior for fullscreen Spaces
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    msg.restype = None
    msg(panel, _sel(libobjc, b"setCollectionBehavior:"), _OVERLAY_BEHAVIOR)

    # match child window level (usually floating from always-on-top)
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
    msg.restype = None
    msg(panel, _sel(libobjc, b"setLevel:"), int(level))

    # invisible / ignore mouse / stay when app deactivates
    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double]
    msg.restype = None
    msg(panel, _sel(libobjc, b"setAlphaValue:"), 0.0)

    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
    msg.restype = None
    msg(panel, _sel(libobjc, b"setIgnoresMouseEvents:"), True)
    msg(panel, _sel(libobjc, b"setHidesOnDeactivate:"), False)
    msg(panel, _sel(libobjc, b"setReleasedWhenClosed:"), False)

    # opaque / clear background if selectors exist
    try:
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        msg.restype = None
        msg(panel, _sel(libobjc, b"setOpaque:"), False)
    except Exception:  # noqa: BLE001
        pass

    _anchor_panel = ctypes.c_void_p(panel)
    return _anchor_panel


def apply_overlay_space_behavior(widget: QWidget) -> bool:
    """Attach widget's NSWindow to a Space-joining NSPanel anchor. No-op elsewhere."""
    if sys.platform != "darwin":
        return False
    try:
        libobjc = _ensure_objc()
        if libobjc is None:
            return False

        ns_window = _ns_window_from_widget(widget, libobjc)
        if not ns_window:
            return False

        msg = _msg(libobjc)

        # Idempotent: already a child of some parent
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        msg.restype = ctypes.c_void_p
        parent = msg(ns_window, _sel(libobjc, b"parentWindow"))
        if parent:
            return True

        # Read current window level so the anchor matches
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        msg.restype = ctypes.c_long
        level = int(msg(ns_window, _sel(libobjc, b"level")) or 0)

        # Also set collection behavior on the Qt window (harmless; panel does the real work)
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        msg.restype = None
        msg(ns_window, _sel(libobjc, b"setCollectionBehavior:"), _OVERLAY_BEHAVIOR)

        anchor = _get_or_create_anchor(libobjc, level)
        if not anchor:
            return False

        # Keep anchor ordered front so Space membership stays active
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        msg.restype = None
        msg(anchor, _sel(libobjc, b"orderFrontRegardless"))

        # Sync level in case always-on-top changed after first create
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        msg.restype = None
        msg(anchor, _sel(libobjc, b"setLevel:"), level)

        # Parent the Qt window under the anchor
        msg.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
        ]
        msg.restype = None
        msg(
            anchor,
            _sel(libobjc, b"addChildWindow:ordered:"),
            ns_window,
            _ORDERED_ABOVE,
        )
        return True
    except Exception:  # noqa: BLE001
        return False
