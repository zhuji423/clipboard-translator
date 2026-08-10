from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Callable, Protocol

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

_MODIFIER_ALIASES = {
    "ctrl": ("Ctrl", MOD_CONTROL),
    "control": ("Ctrl", MOD_CONTROL),
    "alt": ("Alt", MOD_ALT),
    "shift": ("Shift", MOD_SHIFT),
    "win": ("Win", MOD_WIN),
    "meta": ("Win", MOD_WIN),
}
_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")


@dataclass(frozen=True)
class HotkeySpec:
    text: str
    modifiers: int
    virtual_key: int


def parse_hotkey(text: str) -> HotkeySpec:
    raw_parts = [part.strip() for part in str(text).split("+")]
    if not raw_parts or any(not part for part in raw_parts):
        raise ValueError("快捷键不能为空")

    modifiers: dict[str, int] = {}
    key_name = ""
    virtual_key = 0
    for part in raw_parts:
        modifier = _MODIFIER_ALIASES.get(part.lower())
        if modifier is not None:
            modifiers[modifier[0]] = modifier[1]
            continue
        if key_name:
            raise ValueError("问答快捷键只能包含一个普通键")
        upper = part.upper()
        if len(upper) == 1 and ("A" <= upper <= "Z" or "0" <= upper <= "9"):
            key_name = upper
            virtual_key = ord(upper)
        elif upper.startswith("F") and upper[1:].isdigit():
            number = int(upper[1:])
            if 1 <= number <= 24:
                key_name = f"F{number}"
                virtual_key = 0x70 + number - 1
        if not key_name:
            raise ValueError("仅支持字母、数字或 F1-F24 作为问答快捷键")

    if not modifiers:
        raise ValueError("问答快捷键至少需要 Ctrl、Alt、Shift 或 Win 中的一个")
    if not key_name:
        raise ValueError("问答快捷键缺少普通键")

    modifier_bits = 0
    ordered_names: list[str] = []
    for name in _MODIFIER_ORDER:
        if name in modifiers:
            ordered_names.append(name)
            modifier_bits |= modifiers[name]
    return HotkeySpec(
        text="+".join([*ordered_names, key_name]),
        modifiers=modifier_bits,
        virtual_key=virtual_key,
    )


class HotkeyBackend(Protocol):
    def register(self, spec: HotkeySpec, callback: Callable[[], None]) -> bool: ...

    def unregister(self) -> None: ...

    def close(self) -> None: ...


class _WindowsNativeEventFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and int(msg.wParam) == self._hotkey_id:
                self._callback()
        except (TypeError, ValueError):
            pass
        return False, 0


class WindowsHotkeyBackend:
    HOTKEY_ID = 0x4351

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("全局问答快捷键当前仅支持 Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._filter: _WindowsNativeEventFilter | None = None
        self._registered = False

    def register(self, spec: HotkeySpec, callback: Callable[[], None]) -> bool:
        if self._registered:
            self.unregister()
        ok = bool(
            self._user32.RegisterHotKey(
                None,
                self.HOTKEY_ID,
                spec.modifiers | MOD_NOREPEAT,
                spec.virtual_key,
            )
        )
        if not ok:
            return False
        app = QCoreApplication.instance()
        if app is None:
            self._user32.UnregisterHotKey(None, self.HOTKEY_ID)
            return False
        self._filter = _WindowsNativeEventFilter(self.HOTKEY_ID, callback)
        app.installNativeEventFilter(self._filter)
        self._registered = True
        return True

    def unregister(self) -> None:
        if not self._registered:
            return
        self._user32.UnregisterHotKey(None, self.HOTKEY_ID)
        app = QCoreApplication.instance()
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
        self._registered = False

    def close(self) -> None:
        self.unregister()


class GlobalHotkeyManager(QObject):
    activated = Signal()

    def __init__(self, backend: HotkeyBackend | None = None, parent=None) -> None:
        super().__init__(parent)
        self._backend = backend
        if self._backend is None and sys.platform == "win32":
            self._backend = WindowsHotkeyBackend()
        self._shortcut = ""

    @property
    def supported(self) -> bool:
        return self._backend is not None

    @property
    def shortcut(self) -> str:
        return self._shortcut

    def rebind(self, shortcut: str) -> tuple[bool, str]:
        try:
            spec = parse_hotkey(shortcut)
        except ValueError as exc:
            return False, str(exc)
        if not self.supported:
            return False, "全局问答快捷键当前仅支持 Windows"
        if spec.text == self._shortcut:
            return True, ""

        old_text = self._shortcut
        old_spec = parse_hotkey(old_text) if old_text else None
        self._backend.unregister()
        if self._backend.register(spec, self.activated.emit):
            self._shortcut = spec.text
            return True, ""

        if old_spec is not None:
            self._backend.register(old_spec, self.activated.emit)
        return False, f"快捷键 {spec.text} 已被其他程序占用"

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()
        self._shortcut = ""


if sys.platform == "win32":
    from ctypes import wintypes

    ULONG_PTR = wintypes.WPARAM

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        )

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = (
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        )

    class _INPUTUNION(ctypes.Union):
        _fields_ = (
            ("mi", _MOUSEINPUT),
            ("ki", _KEYBDINPUT),
            ("hi", _HARDWAREINPUT),
        )

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = (("type", wintypes.DWORD), ("union", _INPUTUNION))


class WindowsSelectionInput:
    _MODIFIER_KEYS = (0x10, 0x11, 0x12, 0x5B, 0x5C)
    _KEYEVENTF_KEYUP = 0x0002
    _INPUT_KEYBOARD = 1
    _VK_CONTROL = 0x11
    _VK_C = 0x43

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("选区复制当前仅支持 Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

    def clipboard_sequence(self) -> int:
        return int(self._user32.GetClipboardSequenceNumber())

    def modifiers_released(self) -> bool:
        return all(
            not (int(self._user32.GetAsyncKeyState(key)) & 0x8000)
            for key in self._MODIFIER_KEYS
        )

    def send_copy(self) -> bool:
        inputs = (_INPUT * 4)(
            self._key_input(self._VK_CONTROL, key_up=False),
            self._key_input(self._VK_C, key_up=False),
            self._key_input(self._VK_C, key_up=True),
            self._key_input(self._VK_CONTROL, key_up=True),
        )
        sent = int(self._user32.SendInput(len(inputs), inputs, ctypes.sizeof(_INPUT)))
        return sent == len(inputs)

    def _key_input(self, key: int, *, key_up: bool) -> _INPUT:
        flags = self._KEYEVENTF_KEYUP if key_up else 0
        return _INPUT(
            type=self._INPUT_KEYBOARD,
            ki=_KEYBDINPUT(
                wVk=key,
                wScan=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )
