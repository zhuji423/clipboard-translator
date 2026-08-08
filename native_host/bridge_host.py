"""stdio Native Messaging host: return bridge port + token (never API keys).

Protocol (Chrome length-prefixed JSON):
  Request:  { "type": "get_bridge_credentials" }
  Response: { "ok": true, "port": 17890, "token": "..." }
"""

from __future__ import annotations

import json
import secrets
import struct
import sys
from pathlib import Path

# Allow running as script / frozen exe from repo root or package.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from browser_bridge import DEFAULT_BRIDGE_PORT  # noqa: E402
from config import load_config, save_bridge_settings, save_bridge_token  # noqa: E402
from paths import ensure_user_config  # noqa: E402


def _read_message() -> dict | None:
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    (length,) = struct.unpack("<I", raw_len)
    if length == 0 or length > 1024 * 1024:
        return None
    data = sys.stdin.buffer.read(length)
    if len(data) < length:
        return None
    try:
        msg = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return msg if isinstance(msg, dict) else None


def _write_message(payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def ensure_bridge_credentials() -> dict:
    """Load config; enable bridge and create token if missing."""
    ensure_user_config()
    cfg = load_config()
    port = cfg.bridge.port or DEFAULT_BRIDGE_PORT
    token = (cfg.bridge.token or "").strip()
    enabled = cfg.bridge.enabled

    if not enabled:
        save_bridge_settings(True, port, token if token else None)
        enabled = True

    if not token:
        token = secrets.token_urlsafe(32)
        save_bridge_token(token)

    return {
        "ok": True,
        "port": port,
        "token": token,
        "enabled": enabled,
    }


def handle_message(msg: dict) -> dict:
    msg_type = str(msg.get("type") or "").strip()
    if msg_type == "get_bridge_credentials":
        try:
            return ensure_bridge_credentials()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
    if msg_type == "ping":
        return {"ok": True, "pong": True}
    return {"ok": False, "error": f"unknown type: {msg_type or '(empty)'}"}


def run_host() -> int:
    while True:
        msg = _read_message()
        if msg is None:
            return 0
        _write_message(handle_message(msg))


def main() -> int:
    return run_host()


if __name__ == "__main__":
    raise SystemExit(main())
