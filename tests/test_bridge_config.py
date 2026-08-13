from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from config import (
    load_config,
    save_bridge_settings,
    save_bridge_token,
    save_dictionary_settings,
)


def test_save_bridge_settings_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        shutil.copy(Path(__file__).resolve().parents[1] / "config.example.toml", path)
        save_bridge_settings(True, 17891, path=path)
        save_bridge_token("abc123", path=path)
        save_dictionary_settings("mw-key", path=path)
        cfg = load_config(path)
        assert cfg.bridge.enabled is True
        assert cfg.bridge.port == 17891
        assert cfg.bridge.token == "abc123"
        assert cfg.dictionary.merriam_webster_api_key == "mw-key"


if __name__ == "__main__":
    test_save_bridge_settings_roundtrip()
    print("ok")
