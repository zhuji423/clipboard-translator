"""Register / unregister Chrome & Edge Native Messaging hosts (Windows + macOS)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from distribution import (
    NATIVE_HOST_DESCRIPTION,
    NATIVE_HOST_NAME,
    extension_allowed_origins,
    native_host_bin_name,
)
from paths import is_frozen, user_data_dir

_CHROME_NM_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{NATIVE_HOST_NAME}"
_EDGE_NM_KEY = rf"Software\Microsoft\Edge\NativeMessagingHosts\{NATIVE_HOST_NAME}"

_DARWIN_BROWSER_NM_DIRS = (
    Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts",
    Path.home() / "Library" / "Application Support" / "Microsoft Edge" / "NativeMessagingHosts",
)


def nm_host_bin_name() -> str:
    return native_host_bin_name()


def _dev_launcher_path() -> Path:
    return user_data_dir() / "native_messaging" / nm_host_bin_name()


def _dev_python_executable() -> Path | None:
    """Interpreter path that keeps the active venv (do not resolve() through symlinks)."""
    prefix = Path(sys.prefix)
    if (prefix / "pyvenv.cfg").is_file():
        for name in ("python3", "python"):
            candidate = prefix / "bin" / name
            if candidate.is_file():
                return candidate.absolute()
    exe = Path(sys.executable)
    if exe.is_file():
        # absolute() keeps a venv symlink target usable via PATH/name; avoid resolve().
        return exe.absolute()
    return None


def ensure_dev_nm_launcher() -> Path | None:
    """Write an executable launcher that runs `python -m native_host.bridge_host` (dev / source)."""
    if is_frozen() or sys.platform != "darwin":
        return None
    python = _dev_python_executable()
    if python is None:
        return None
    # native_messaging.py lives at repo root in source trees.
    repo_root = Path(__file__).resolve().parent
    launcher = _dev_launcher_path()
    launcher.parent.mkdir(parents=True, exist_ok=True)
    venv_export = ""
    if (Path(sys.prefix) / "pyvenv.cfg").is_file():
        venv_export = f'export VIRTUAL_ENV="{Path(sys.prefix).absolute()}"\n'
    # Absolute paths; Chrome requires an executable host path (script is OK if +x).
    script = (
        "#!/bin/sh\n"
        f"{venv_export}"
        f'export PYTHONPATH="{repo_root}${{PYTHONPATH:+:$PYTHONPATH}}"\n'
        f'exec "{python}" -m native_host.bridge_host "$@"\n'
    )
    launcher.write_text(script, encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | 0o111)
    return launcher


def nm_host_executable() -> Path | None:
    """Resolve ClipboardTranslatorNmHost next to the frozen app, or a Darwin dev launcher."""
    if not is_frozen():
        return ensure_dev_nm_launcher()

    exe_dir = Path(sys.executable).resolve().parent
    bin_name = nm_host_bin_name()
    candidate = exe_dir / bin_name
    if candidate.is_file():
        return candidate

    pattern = "ClipboardTranslator*NmHost.exe" if sys.platform == "win32" else "ClipboardTranslator*NmHost"
    for path in sorted(exe_dir.glob(pattern)):
        if path.is_file():
            return path
    return None


def nm_manifest_path() -> Path:
    return user_data_dir() / "native_messaging" / f"{NATIVE_HOST_NAME}.json"


def darwin_browser_manifest_paths() -> list[Path]:
    return [directory / f"{NATIVE_HOST_NAME}.json" for directory in _DARWIN_BROWSER_NM_DIRS]


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


def _write_manifest_file(path: Path, host_path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_nm_manifest(host_path), indent=2) + "\n", encoding="utf-8")
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
    """Write NM manifest and register with Chrome + Edge.

    Windows: HKCU registry pointing at user-data manifest.
    macOS: Native Messaging host is not used (HTTP /v1/auto_pair instead);
    calling register clears any previously installed manifests so Edge does not
    launch a Gatekeeper-blocked PyInstaller host.

    Returns the primary manifest path, or None if skipped / cleaned.
    """
    if sys.platform == "darwin":
        unregister_native_messaging_host()
        return None
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
    if sys.platform == "win32":
        _delete_hkcu_key(_CHROME_NM_KEY)
        _delete_hkcu_key(_EDGE_NM_KEY)
    elif sys.platform == "darwin":
        for path in darwin_browser_manifest_paths():
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
    else:
        return

    path = nm_manifest_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    if sys.platform == "darwin":
        launcher = _dev_launcher_path()
        if launcher.is_file() and not is_frozen():
            try:
                launcher.unlink()
            except OSError:
                pass
