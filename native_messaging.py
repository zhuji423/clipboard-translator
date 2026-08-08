"""Register / unregister Chrome & Edge Native Messaging hosts (Windows HKCU)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from distribution import (
    NATIVE_HOST_DESCRIPTION,
    NATIVE_HOST_EXE_NAME,
    NATIVE_HOST_NAME,
    extension_allowed_origins,
)
from paths import is_frozen, user_data_dir

_CHROME_NM_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{NATIVE_HOST_NAME}"
_EDGE_NM_KEY = rf"Software\Microsoft\Edge\NativeMessagingHosts\{NATIVE_HOST_NAME}"


def nm_host_executable() -> Path | None:
    """Resolve ClipboardTranslatorNmHost.exe next to the frozen app."""
    if not is_frozen():
        # Dev: run via python -m native_host.bridge_host (no registry by default).
        return None
    exe_dir = Path(sys.executable).resolve().parent
    candidate = exe_dir / NATIVE_HOST_EXE_NAME
    if candidate.is_file():
        return candidate
    # Release assets may be named ClipboardTranslator-{ver}-NmHost.exe
    matches = sorted(exe_dir.glob("ClipboardTranslator*NmHost.exe"))
    for path in matches:
        if path.is_file():
            return path
    return None


def nm_manifest_path() -> Path:
    return user_data_dir() / "native_messaging" / f"{NATIVE_HOST_NAME}.json"


def build_nm_manifest(host_path: Path) -> dict:
    origins = extension_allowed_origins()
    if not origins:
        raise ValueError("distribution.EXTENSION_*_ID 未配置，无法注册 Native Messaging")
    return {
        "name": NATIVE_HOST_NAME,
        "description": NATIVE_HOST_DESCRIPTION,
        "path": str(host_path.resolve()),
        "type": "stdio",
        "allowed_origins": origins,
    }


def write_nm_manifest(host_path: Path) -> Path:
    manifest = build_nm_manifest(host_path)
    path = nm_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def _set_hkcu_default(subkey: str, value: str) -> None:
    if sys.platform != "win32":
        return
    import winreg

    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def _delete_hkcu_key(subkey: str) -> None:
    if sys.platform != "win32":
        return
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
    except FileNotFoundError:
        return
    except OSError:
        return


def register_native_messaging_host(host_path: Path | None = None) -> Path | None:
    """Write NM manifest and HKCU registry entries for Chrome + Edge.

    Returns the manifest path, or None if skipped (non-Windows / no host binary).
    """
    if sys.platform != "win32":
        return None
    host = host_path or nm_host_executable()
    if host is None or not host.is_file():
        return None
    if not extension_allowed_origins():
        return None
    manifest_file = write_nm_manifest(host)
    value = str(manifest_file.resolve())
    _set_hkcu_default(_CHROME_NM_KEY, value)
    _set_hkcu_default(_EDGE_NM_KEY, value)
    return manifest_file


def unregister_native_messaging_host() -> None:
    if sys.platform != "win32":
        return
    _delete_hkcu_key(_CHROME_NM_KEY)
    _delete_hkcu_key(_EDGE_NM_KEY)
    path = nm_manifest_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
