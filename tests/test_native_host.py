from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from config import load_config, save_bridge_settings, save_bridge_token
from native_host import bridge_host


def test_handle_ping() -> None:
    assert bridge_host.handle_message({"type": "ping"}) == {"ok": True, "pong": True}


def test_handle_unknown() -> None:
    resp = bridge_host.handle_message({"type": "nope"})
    assert resp["ok"] is False
    assert "unknown" in str(resp.get("error", "")).lower()


def test_ensure_bridge_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    example = Path(__file__).resolve().parent.parent / "config.example.toml"
    cfg = tmp_path / "config.toml"
    text = example.read_text(encoding="utf-8").replace("enabled = true", "enabled = false")
    cfg.write_text(text, encoding="utf-8")

    monkeypatch.setattr(bridge_host, "ensure_user_config", lambda: (cfg, False))
    monkeypatch.setattr(bridge_host, "load_config", lambda: load_config(cfg))
    monkeypatch.setattr(
        bridge_host,
        "save_bridge_settings",
        lambda enabled, port, token=None: save_bridge_settings(enabled, port, token, path=cfg),
    )
    monkeypatch.setattr(
        bridge_host,
        "save_bridge_token",
        lambda token: save_bridge_token(token, path=cfg),
    )

    first = bridge_host.handle_message({"type": "get_bridge_credentials"})
    assert first["ok"] is True
    assert first["port"] == 17890
    assert isinstance(first["token"], str) and len(first["token"]) > 10

    reloaded = load_config(cfg)
    assert reloaded.bridge.enabled is True
    assert reloaded.bridge.token == first["token"]

    second = bridge_host.handle_message({"type": "get_bridge_credentials"})
    assert second["token"] == first["token"]


def test_length_prefixed_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"type": "ping"}
    encoded = json.dumps(payload).encode("utf-8")
    stdin_bytes = struct.pack("<I", len(encoded)) + encoded

    class _Buf:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self._i = 0
            self.out = bytearray()

        def read(self, n: int) -> bytes:
            chunk = self._data[self._i : self._i + n]
            self._i += len(chunk)
            return chunk

        def write(self, data: bytes) -> int:
            self.out.extend(data)
            return len(data)

        def flush(self) -> None:
            return None

    buf = _Buf(stdin_bytes)

    class _Stdin:
        buffer = buf

    class _Stdout:
        buffer = buf

    monkeypatch.setattr(bridge_host.sys, "stdin", _Stdin())
    monkeypatch.setattr(bridge_host.sys, "stdout", _Stdout())

    assert bridge_host.run_host() == 0
    assert len(buf.out) >= 4
    (length,) = struct.unpack("<I", bytes(buf.out[:4]))
    body = json.loads(bytes(buf.out[4 : 4 + length]).decode("utf-8"))
    assert body == {"ok": True, "pong": True}
