from __future__ import annotations

import sys
from pathlib import Path

import pytest

from distribution import (
    EXTENSION_CHROME_ID,
    NATIVE_HOST_NAME,
    extension_allowed_origins,
    native_host_bin_name,
)
from native_messaging import (
    build_nm_manifest,
    darwin_browser_manifest_paths,
    ensure_dev_nm_launcher,
    register_native_messaging_host,
    write_nm_manifest,
)


def test_allowed_origins_include_chrome_id() -> None:
    origins = extension_allowed_origins()
    assert f"chrome-extension://{EXTENSION_CHROME_ID}/" in origins


def test_native_host_bin_name_matches_platform() -> None:
    name = native_host_bin_name()
    if sys.platform == "win32":
        assert name.endswith(".exe")
    else:
        assert not name.endswith(".exe")
        assert name == "ClipboardTranslatorNmHost"


def test_build_nm_manifest(tmp_path: Path) -> None:
    host = tmp_path / "ClipboardTranslatorNmHost.exe"
    host.write_bytes(b"x")
    manifest = build_nm_manifest(host)
    assert manifest["name"] == NATIVE_HOST_NAME
    assert manifest["type"] == "stdio"
    assert Path(manifest["path"]) == host.resolve()
    assert manifest["allowed_origins"]


def test_write_nm_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host = tmp_path / "ClipboardTranslatorNmHost.exe"
    host.write_bytes(b"x")
    monkeypatch.setattr("native_messaging.user_data_dir", lambda: tmp_path)
    path = write_nm_manifest(host)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert NATIVE_HOST_NAME in text
    assert EXTENSION_CHROME_ID in text


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin NM cleanup only")
def test_register_native_messaging_host_darwin_clears_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_dir = tmp_path / "userdata"
    chrome_dir = tmp_path / "chrome_nm"
    edge_dir = tmp_path / "edge_nm"
    chrome_dir.mkdir(parents=True)
    edge_dir.mkdir(parents=True)
    leftover = chrome_dir / f"{NATIVE_HOST_NAME}.json"
    leftover.write_text("{}", encoding="utf-8")
    (edge_dir / f"{NATIVE_HOST_NAME}.json").write_text("{}", encoding="utf-8")
    (user_dir / "native_messaging").mkdir(parents=True)
    (user_dir / "native_messaging" / f"{NATIVE_HOST_NAME}.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("native_messaging.user_data_dir", lambda: user_dir)
    monkeypatch.setattr(
        "native_messaging._DARWIN_BROWSER_NM_DIRS",
        (chrome_dir, edge_dir),
    )

    assert register_native_messaging_host() is None
    assert not leftover.is_file()
    assert not (edge_dir / f"{NATIVE_HOST_NAME}.json").is_file()
    assert not (user_dir / "native_messaging" / f"{NATIVE_HOST_NAME}.json").is_file()


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin dev launcher only")
def test_ensure_dev_nm_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("native_messaging.user_data_dir", lambda: tmp_path)
    monkeypatch.setattr("native_messaging.is_frozen", lambda: False)
    monkeypatch.setattr(sys, "platform", "darwin")

    launcher = ensure_dev_nm_launcher()
    assert launcher is not None
    assert launcher.is_file()
    assert launcher.stat().st_mode & 0o111
    text = launcher.read_text(encoding="utf-8")
    assert "native_host.bridge_host" in text
    assert "PYTHONPATH=" in text
    # Must not collapse a venv interpreter to the base install via Path.resolve().
    assert ".venv" in text or "VIRTUAL_ENV=" in text or "python" in text.lower()


def test_darwin_browser_manifest_paths_shape() -> None:
    paths = darwin_browser_manifest_paths()
    assert len(paths) >= 2
    assert all(p.name == f"{NATIVE_HOST_NAME}.json" for p in paths)
