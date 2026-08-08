"""Check GitHub Releases and apply Windows updates (download + replace + relaunch)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests

from paths import is_frozen
from version import __version__

GITHUB_OWNER = "zhuji423"
GITHUB_REPO = "clipboard-translator"
RELEASES_LATEST_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
USER_AGENT = f"ClipboardTranslator/{__version__}"


class UpdateError(Exception):
    """User-facing update failure."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    notes: str
    setup_url: str | None
    portable_url: str | None
    setup_size: int | None
    portable_size: int | None


@dataclass(frozen=True)
class InstallKind:
    """How the running Windows build should be replaced."""

    kind: str  # "setup" | "portable"
    target_exe: Path
    relaunch_exe: Path


def parse_version(text: str) -> tuple[int, ...]:
    raw = text.strip()
    if raw.lower().startswith("v"):
        raw = raw[1:]
    parts: list[int] = []
    for piece in raw.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    if not parts:
        raise UpdateError(f"无法解析版本号：{text!r}")
    return tuple(parts)


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def _default_install_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return Path(local) / "Programs" / "ClipboardTranslator"


def detect_install_kind() -> InstallKind | None:
    """Return Windows install/portable target, or None if auto-update is unsupported."""
    if sys.platform != "win32" or not is_frozen():
        return None
    exe = Path(sys.executable).resolve()
    install_dir = _default_install_dir().resolve()
    uninstaller = exe.parent / "unins000.exe"
    if uninstaller.is_file() or exe.parent == install_dir:
        return InstallKind(
            kind="setup",
            target_exe=exe,
            relaunch_exe=install_dir / "ClipboardTranslator.exe",
        )
    return InstallKind(kind="portable", target_exe=exe, relaunch_exe=exe)


def fetch_latest_release(timeout: float = 20.0) -> ReleaseInfo:
    try:
        resp = requests.get(
            RELEASES_LATEST_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise UpdateError(f"无法连接 GitHub Releases：{exc}") from exc

    tag = str(data.get("tag_name") or "")
    if not tag:
        raise UpdateError("正式版 Release 缺少 tag_name")
    version = tag[1:] if tag.lower().startswith("v") else tag
    notes = str(data.get("body") or "").strip()

    setup_url = portable_url = None
    setup_size = portable_size = None
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        size = asset.get("size")
        size_i = int(size) if isinstance(size, int) else None
        if not url:
            continue
        lower = name.lower()
        if lower.endswith("-setup.exe") or (
            "setup" in lower and lower.endswith(".exe")
        ):
            setup_url, setup_size = url, size_i
        elif lower.endswith("-portable.exe") or "portable" in lower:
            portable_url, portable_size = url, size_i

    if setup_url is None and portable_url is None:
        raise UpdateError("正式版 Release 中未找到 Setup 或 portable 资源")

    return ReleaseInfo(
        version=version,
        tag=tag,
        notes=notes,
        setup_url=setup_url,
        portable_url=portable_url,
        setup_size=setup_size,
        portable_size=portable_size,
    )


def select_asset(
    release: ReleaseInfo, kind: InstallKind
) -> tuple[str, int | None]:
    if kind.kind == "setup":
        if not release.setup_url:
            raise UpdateError("该版本没有 Setup 安装包，无法覆盖安装版")
        return release.setup_url, release.setup_size
    if not release.portable_url:
        raise UpdateError("该版本没有便携版，无法覆盖当前程序")
    return release.portable_url, release.portable_size


def download_file(
    url: str,
    dest: Path,
    *,
    expected_size: int | None = None,
    timeout: float = 60.0,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    try:
        with requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            stream=True,
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            total = expected_size
            if total is None:
                cl = resp.headers.get("Content-Length")
                if cl and cl.isdigit():
                    total = int(cl)
            done = 0
            with partial.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    done += len(chunk)
                    if on_progress is not None:
                        on_progress(done, total)
        if expected_size is not None and partial.stat().st_size != expected_size:
            raise UpdateError(
                f"下载大小不匹配：期望 {expected_size}，实际 {partial.stat().st_size}"
            )
        partial.replace(dest)
    except requests.RequestException as exc:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise UpdateError(f"下载失败：{exc}") from exc
    except Exception:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise


def _asset_basename(url: str, fallback: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or fallback


def _write_cmd(path: Path, lines: list[str]) -> None:
    # cmd.exe expects ANSI/system encoding; UTF-8 with BOM helps on modern Windows.
    text = "\r\n".join(lines) + "\r\n"
    path.write_text(text, encoding="utf-8-sig")


def _quote_cmd(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def prepare_windows_apply(
    kind: InstallKind,
    downloaded: Path,
) -> Path:
    """Write a helper .cmd that waits for this PID, applies update, relaunches."""
    pid = os.getpid()
    script = Path(tempfile.gettempdir()) / f"clipboard-translator-update-{pid}.cmd"
    downloaded_q = _quote_cmd(str(downloaded))
    relaunch_q = _quote_cmd(str(kind.relaunch_exe))
    target_q = _quote_cmd(str(kind.target_exe))

    if kind.kind == "setup":
        lines = [
            "@echo off",
            "setlocal",
            f"set PID={pid}",
            ":wait",
            'tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL',
            "if not errorlevel 1 (",
            "  timeout /t 1 /nobreak >NUL",
            "  goto wait",
            ")",
            f"start /wait \"\" {downloaded_q} /VERYSILENT /NORESTART /SUPPRESSMSGBOXES",
            f"if exist {relaunch_q} (",
            f"  start \"\" {relaunch_q}",
            ") else (",
            f"  start \"\" {target_q}",
            ")",
            f"del /f /q {downloaded_q} >NUL 2>&1",
            'del /f /q "%~f0" >NUL 2>&1',
        ]
    else:
        lines = [
            "@echo off",
            "setlocal",
            f"set PID={pid}",
            ":wait",
            'tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL',
            "if not errorlevel 1 (",
            "  timeout /t 1 /nobreak >NUL",
            "  goto wait",
            ")",
            f"copy /y {downloaded_q} {target_q} >NUL",
            f"if errorlevel 1 (",
            f"  timeout /t 2 /nobreak >NUL",
            f"  copy /y {downloaded_q} {target_q} >NUL",
            ")",
            f"start \"\" {relaunch_q}",
            f"del /f /q {downloaded_q} >NUL 2>&1",
            'del /f /q "%~f0" >NUL 2>&1',
        ]
    _write_cmd(script, lines)
    return script


def launch_apply_script(script: Path) -> None:
    creation = 0
    if sys.platform == "win32":
        creation = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        cwd=str(script.parent),
        creationflags=creation,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def download_and_stage(
    release: ReleaseInfo,
    kind: InstallKind,
    *,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    url, size = select_asset(release, kind)
    suffix = "-Setup.exe" if kind.kind == "setup" else "-portable.exe"
    name = _asset_basename(url, f"ClipboardTranslator-{release.version}{suffix}")
    dest = Path(tempfile.gettempdir()) / name
    download_file(url, dest, expected_size=size, on_progress=on_progress)
    return dest
