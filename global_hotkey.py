from __future__ import annotations

import ctypes
import ctypes.util
import sys
from dataclasses import dataclass
from typing import Callable, Protocol

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from hotkey_defaults import default_manual_input_hotkey, default_question_hotkey


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
    "option": ("Alt", MOD_ALT),
    "shift": ("Shift", MOD_SHIFT),
    "win": ("Win", MOD_WIN),
    "meta": ("Win", MOD_WIN),
    "cmd": ("Cmd", MOD_WIN),
    "command": ("Cmd", MOD_WIN),
}
_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win", "Cmd")

# ANSI virtual key codes (US keyboard) for Carbon / CGEvent.
_MAC_LETTER_CODES = {
    "A": 0x00,
    "S": 0x01,
    "D": 0x02,
    "F": 0x03,
    "H": 0x04,
    "G": 0x05,
    "Z": 0x06,
    "X": 0x07,
    "C": 0x08,
    "V": 0x09,
    "B": 0x0B,
    "Q": 0x0C,
    "W": 0x0D,
    "E": 0x0E,
    "R": 0x0F,
    "Y": 0x10,
    "T": 0x11,
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "6": 0x16,
    "5": 0x17,
    "9": 0x19,
    "7": 0x1A,
    "8": 0x1C,
    "0": 0x1D,
    "O": 0x1F,
    "U": 0x20,
    "I": 0x22,
    "P": 0x23,
    "L": 0x25,
    "J": 0x26,
    "K": 0x28,
    "N": 0x2D,
    "M": 0x2E,
}
_MAC_F_KEY_CODES = {
    1: 0x7A,
    2: 0x78,
    3: 0x63,
    4: 0x76,
    5: 0x60,
    6: 0x61,
    7: 0x62,
    8: 0x64,
    9: 0x65,
    10: 0x6D,
    11: 0x67,
    12: 0x6F,
    13: 0x69,
    14: 0x6B,
    15: 0x71,
    16: 0x6A,
    17: 0x40,
    18: 0x4F,
    19: 0x50,
    20: 0x5A,
}

# Carbon RegisterEventHotKey modifier bits
_CARBON_CMD = 0x0100
_CARBON_SHIFT = 0x0200
_CARBON_OPTION = 0x0800
_CARBON_CONTROL = 0x1000

_K_EVENT_CLASS_KEYBOARD = 0x6B657962  # 'keyb'
_K_EVENT_HOT_KEY_PRESSED = 5
_NO_ERR = 0

_MAC_VK_SHIFT = 0x38
_MAC_VK_RIGHT_SHIFT = 0x3C
_MAC_VK_CONTROL = 0x3B
_MAC_VK_RIGHT_CONTROL = 0x3E
_MAC_VK_OPTION = 0x3A
_MAC_VK_RIGHT_OPTION = 0x3D
_MAC_VK_COMMAND = 0x37
_MAC_VK_RIGHT_COMMAND = 0x36
_MAC_MODIFIER_VKS = (
    _MAC_VK_SHIFT,
    _MAC_VK_RIGHT_SHIFT,
    _MAC_VK_CONTROL,
    _MAC_VK_RIGHT_CONTROL,
    _MAC_VK_OPTION,
    _MAC_VK_RIGHT_OPTION,
    _MAC_VK_COMMAND,
    _MAC_VK_RIGHT_COMMAND,
)

_CG_HID_EVENT_TAP = 0
_CG_EVENT_FLAG_COMMAND = 0x100000
_CG_EVENT_SOURCE_COMBINED = 1


@dataclass(frozen=True)
class HotkeySpec:
    text: str
    modifiers: int
    virtual_key: int
    key_name: str


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
            raise ValueError("快捷键只能包含一个普通键")
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
            raise ValueError("仅支持字母、数字或 F1-F24 作为快捷键")

    if not modifiers:
        raise ValueError("快捷键至少需要 Ctrl、Alt、Shift、Win 或 Cmd 中的一个")
    if not key_name:
        raise ValueError("快捷键缺少普通键")

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
        key_name=key_name,
    )


def config_hotkey_to_qt_portable(text: str) -> str:
    """Map our config string to QKeySequence PortableText (Mac Ctrl↔Meta swap)."""
    spec = parse_hotkey(text)
    if sys.platform != "darwin":
        return spec.text
    parts: list[str] = []
    if spec.modifiers & MOD_CONTROL:
        parts.append("Meta")
    if spec.modifiers & MOD_ALT:
        parts.append("Alt")
    if spec.modifiers & MOD_SHIFT:
        parts.append("Shift")
    if spec.modifiers & MOD_WIN:
        parts.append("Ctrl")
    parts.append(spec.key_name)
    return "+".join(parts)


def qt_portable_to_config_hotkey(text: str) -> str:
    """Map QKeySequence PortableText back to our config string on Mac."""
    raw = str(text).strip()
    if not raw:
        raise ValueError("快捷键不能为空")
    if sys.platform != "darwin":
        return parse_hotkey(raw).text
    mapped: list[str] = []
    for part in raw.split("+"):
        lower = part.strip().lower()
        if lower in ("ctrl", "control"):
            mapped.append("Cmd")
        elif lower == "meta":
            mapped.append("Ctrl")
        else:
            mapped.append(part.strip())
    return parse_hotkey("+".join(mapped)).text


def _mac_key_code(key_name: str) -> int:
    if key_name in _MAC_LETTER_CODES:
        return _MAC_LETTER_CODES[key_name]
    if key_name.startswith("F") and key_name[1:].isdigit():
        number = int(key_name[1:])
        if number in _MAC_F_KEY_CODES:
            return _MAC_F_KEY_CODES[number]
    raise ValueError(f"当前平台不支持快捷键键位 {key_name}")


def _mac_carbon_modifiers(modifiers: int) -> int:
    bits = 0
    if modifiers & MOD_CONTROL:
        bits |= _CARBON_CONTROL
    if modifiers & MOD_ALT:
        bits |= _CARBON_OPTION
    if modifiers & MOD_SHIFT:
        bits |= _CARBON_SHIFT
    if modifiers & MOD_WIN:
        bits |= _CARBON_CMD
    return bits


class HotkeyBackend(Protocol):
    def register(self, spec: HotkeySpec, callback: Callable[[], None]) -> bool: ...

    def unregister(self) -> None: ...

    def close(self) -> None: ...


class SelectionInput(Protocol):
    def clipboard_sequence(self) -> int: ...

    def modifiers_released(self) -> bool: ...

    def send_copy(self) -> bool: ...


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
    DEFAULT_HOTKEY_ID = 0x4351

    def __init__(self, hotkey_id: int = DEFAULT_HOTKEY_ID) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows 全局快捷键仅可在 Windows 上创建")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._hotkey_id = hotkey_id
        self._filter: _WindowsNativeEventFilter | None = None
        self._registered = False

    def register(self, spec: HotkeySpec, callback: Callable[[], None]) -> bool:
        if self._registered:
            self.unregister()
        ok = bool(
            self._user32.RegisterHotKey(
                None,
                self._hotkey_id,
                spec.modifiers | MOD_NOREPEAT,
                spec.virtual_key,
            )
        )
        if not ok:
            return False
        app = QCoreApplication.instance()
        if app is None:
            self._user32.UnregisterHotKey(None, self._hotkey_id)
            return False
        self._filter = _WindowsNativeEventFilter(self._hotkey_id, callback)
        app.installNativeEventFilter(self._filter)
        self._registered = True
        return True

    def unregister(self) -> None:
        if not self._registered:
            return
        self._user32.UnregisterHotKey(None, self._hotkey_id)
        app = QCoreApplication.instance()
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
        self._registered = False

    def close(self) -> None:
        self.unregister()


class _EventHotKeyID(ctypes.Structure):
    _fields_ = (("signature", ctypes.c_uint32), ("id", ctypes.c_uint32))


class _EventTypeSpec(ctypes.Structure):
    _fields_ = (("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32))


_CarbonHandler = ctypes.CFUNCTYPE(
    ctypes.c_int32,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


class MacHotkeyBackend:
    DEFAULT_HOTKEY_ID = 0x4351
    _SIGNATURE = 0x434C5054  # 'CLPT'
    _callbacks: dict[int, Callable[[], None]] = {}
    _handler_ref_holder: list[ctypes.c_void_p | None] = [None]
    _handler_proc_holder: list[object | None] = [None]

    def __init__(self, hotkey_id: int = DEFAULT_HOTKEY_ID) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("macOS 全局快捷键仅可在 macOS 上创建")
        carbon_path = ctypes.util.find_library("Carbon")
        if not carbon_path:
            raise RuntimeError("无法加载 Carbon 框架")
        self._carbon = ctypes.CDLL(carbon_path)
        self._hotkey_id = int(hotkey_id)
        self._hotkey_ref: ctypes.c_void_p | None = None
        self._registered = False
        self._configure_carbon()
        self._ensure_shared_handler()

    def _configure_carbon(self) -> None:
        c = self._carbon
        c.GetApplicationEventTarget.restype = ctypes.c_void_p
        c.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        c.InstallEventHandler.restype = ctypes.c_int32
        c.RemoveEventHandler.argtypes = [ctypes.c_void_p]
        c.RemoveEventHandler.restype = ctypes.c_int32
        c.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            _EventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        c.RegisterEventHotKey.restype = ctypes.c_int32
        c.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        c.UnregisterEventHotKey.restype = ctypes.c_int32

    @classmethod
    def _ensure_shared_handler(cls) -> None:
        if cls._handler_ref_holder[0] is not None:
            return
        carbon_path = ctypes.util.find_library("Carbon")
        if not carbon_path:
            raise RuntimeError("无法加载 Carbon 框架")
        carbon = ctypes.CDLL(carbon_path)
        carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.InstallEventHandler.restype = ctypes.c_int32

        @_CarbonHandler
        def _dispatch(call_ref, event, user_data):  # noqa: ARG001
            try:
                hot_id = _EventHotKeyID()
                carbon.GetEventParameter.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.POINTER(ctypes.c_uint32),
                    ctypes.c_void_p,
                ]
                carbon.GetEventParameter.restype = ctypes.c_int32
                # kEventParamDirectObject='----', typeEventHotKeyID='hkid'
                status = carbon.GetEventParameter(
                    event,
                    0x2D2D2D2D,
                    0x686B6964,
                    None,
                    ctypes.sizeof(_EventHotKeyID),
                    None,
                    ctypes.byref(hot_id),
                )
                callback = None
                if status == _NO_ERR:
                    callback = cls._callbacks.get(int(hot_id.id))
                if callback is None and user_data:
                    callback = cls._callbacks.get(int(ctypes.cast(user_data, ctypes.c_void_p).value or 0))
                if callback is not None:
                    callback()
            except Exception:  # noqa: BLE001
                pass
            return _NO_ERR

        cls._handler_proc_holder[0] = _dispatch
        specs = (_EventTypeSpec * 1)(
            _EventTypeSpec(_K_EVENT_CLASS_KEYBOARD, _K_EVENT_HOT_KEY_PRESSED)
        )
        handler_ref = ctypes.c_void_p()
        status = carbon.InstallEventHandler(
            carbon.GetApplicationEventTarget(),
            _dispatch,
            1,
            specs,
            None,
            ctypes.byref(handler_ref),
        )
        if status != _NO_ERR or not handler_ref:
            raise RuntimeError(f"安装 macOS 快捷键处理器失败（{status}）")
        cls._handler_ref_holder[0] = handler_ref

    def register(self, spec: HotkeySpec, callback: Callable[[], None]) -> bool:
        if self._registered:
            self.unregister()
        try:
            key_code = _mac_key_code(spec.key_name)
            modifiers = _mac_carbon_modifiers(spec.modifiers)
        except ValueError:
            return False
        hotkey_id = _EventHotKeyID(signature=self._SIGNATURE, id=self._hotkey_id)
        hotkey_ref = ctypes.c_void_p()
        status = self._carbon.RegisterEventHotKey(
            key_code,
            modifiers,
            hotkey_id,
            self._carbon.GetApplicationEventTarget(),
            0,
            ctypes.byref(hotkey_ref),
        )
        if status != _NO_ERR or not hotkey_ref:
            return False
        type(self)._callbacks[self._hotkey_id] = callback
        self._hotkey_ref = hotkey_ref
        self._registered = True
        return True

    def unregister(self) -> None:
        if not self._registered:
            return
        if self._hotkey_ref is not None:
            self._carbon.UnregisterEventHotKey(self._hotkey_ref)
        type(self)._callbacks.pop(self._hotkey_id, None)
        self._hotkey_ref = None
        self._registered = False

    def close(self) -> None:
        self.unregister()


class GlobalHotkeyManager(QObject):
    activated = Signal()

    def __init__(
        self,
        backend: HotkeyBackend | None = None,
        parent=None,
        hotkey_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        if self._backend is None:
            resolved_id = (
                WindowsHotkeyBackend.DEFAULT_HOTKEY_ID
                if hotkey_id is None
                else hotkey_id
            )
            if sys.platform == "win32":
                self._backend = WindowsHotkeyBackend(resolved_id)
            elif sys.platform == "darwin":
                try:
                    self._backend = MacHotkeyBackend(resolved_id)
                except RuntimeError:
                    self._backend = None
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
            return False, "当前平台暂不支持全局快捷键"
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


class MacSelectionInput:
    """Simulate Cmd+C and watch pasteboard changeCount for selection capture."""

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("选区复制当前仅支持 macOS")
        as_path = ctypes.util.find_library("ApplicationServices")
        if not as_path:
            raise RuntimeError("无法加载 ApplicationServices")
        self._as = ctypes.CDLL(as_path)
        self._as.CGEventSourceKeyState.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        self._as.CGEventSourceKeyState.restype = ctypes.c_bool
        self._as.CGEventCreateKeyboardEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_bool,
        ]
        self._as.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        self._as.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._as.CGEventSetFlags.restype = None
        self._as.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self._as.CGEventPost.restype = None
        self._as.CFRelease.argtypes = [ctypes.c_void_p]
        self._as.AXIsProcessTrusted.restype = ctypes.c_bool

    def clipboard_sequence(self) -> int:
        from macos_clipboard import pasteboard_change_count

        count = pasteboard_change_count()
        return int(count) if count is not None else -1

    def modifiers_released(self) -> bool:
        return all(
            not self._as.CGEventSourceKeyState(_CG_EVENT_SOURCE_COMBINED, key)
            for key in _MAC_MODIFIER_VKS
        )

    def accessibility_trusted(self) -> bool:
        try:
            return bool(self._as.AXIsProcessTrusted())
        except Exception:  # noqa: BLE001
            return False

    def send_copy(self) -> bool:
        if not self.accessibility_trusted():
            return False
        key_c = _MAC_LETTER_CODES["C"]
        down = self._as.CGEventCreateKeyboardEvent(None, key_c, True)
        up = self._as.CGEventCreateKeyboardEvent(None, key_c, False)
        if not down or not up:
            if down:
                self._as.CFRelease(down)
            if up:
                self._as.CFRelease(up)
            return False
        try:
            self._as.CGEventSetFlags(down, _CG_EVENT_FLAG_COMMAND)
            self._as.CGEventSetFlags(up, _CG_EVENT_FLAG_COMMAND)
            self._as.CGEventPost(_CG_HID_EVENT_TAP, down)
            self._as.CGEventPost(_CG_HID_EVENT_TAP, up)
            return True
        finally:
            self._as.CFRelease(down)
            self._as.CFRelease(up)


def create_selection_input() -> SelectionInput | None:
    if sys.platform == "win32":
        return WindowsSelectionInput()
    if sys.platform == "darwin":
        try:
            return MacSelectionInput()
        except RuntimeError:
            return None
    return None
