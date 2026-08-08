from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "ClipboardTranslator"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Read-only assets (icons, config.example.toml)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """Writable config / history. Packaged builds use %APPDATA%; source uses repo root."""
    if is_frozen():
        base = os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_NAME
    else:
        path = Path(__file__).resolve().parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return user_data_dir() / "config.toml"


def example_config_path() -> Path:
    return resource_dir() / "config.example.toml"


def data_dir() -> Path:
    path = user_data_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def icons_dir() -> Path:
    return resource_dir() / "assets" / "icons"


def app_icon_path() -> Path:
    return resource_dir() / "assets" / "app.ico"


def ensure_user_config() -> tuple[Path, bool]:
    """
    Ensure config.toml exists under the user data dir.
    Returns (path, created) where created is True if seeded from example.
    """
    cfg = config_path()
    if cfg.exists():
        return cfg, False
    example = example_config_path()
    if not example.exists():
        raise FileNotFoundError(
            f"缺少配置模板 {example.name}，无法创建 {cfg}."
        )
    shutil.copyfile(example, cfg)
    return cfg, True
