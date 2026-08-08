from __future__ import annotations

from pathlib import Path

import pytest

from distribution import EXTENSION_CHROME_ID, NATIVE_HOST_NAME, extension_allowed_origins
from native_messaging import build_nm_manifest, write_nm_manifest


def test_allowed_origins_include_chrome_id() -> None:
    origins = extension_allowed_origins()
    assert f"chrome-extension://{EXTENSION_CHROME_ID}/" in origins


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
