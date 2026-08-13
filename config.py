from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from paths import config_path, ensure_user_config, example_config_path

from browser_bridge import DEFAULT_BRIDGE_PORT
from hotkey_defaults import default_manual_input_hotkey, default_question_hotkey


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    timeout_s: float = 30.0
    # DeepSeek V4 默认开启思考；翻译场景应关闭以降低首字延迟
    thinking: bool = False


@dataclass(frozen=True)
class AppConfig:
    target_lang: str = "zh"
    min_chars: int = 2
    max_chars: int = 8000
    always_on_top: bool = True
    cache_size: int = 128
    font_size: int = 12
    question_hotkey: str = "Ctrl+Shift+Q"


@dataclass(frozen=True)
class BridgeSettings:
    enabled: bool = True
    port: int = DEFAULT_BRIDGE_PORT
    token: str = ""


@dataclass(frozen=True)
class DictionarySettings:
    merriam_webster_api_key: str = ""


@dataclass(frozen=True)
class ManualInputSettings:
    hotkey: str = "Ctrl+M"
    x: int | None = None
    y: int | None = None
    width: int = 420
    height: int = 144
    opacity: float = 0.82


@dataclass(frozen=True)
class Config:
    llm: LlmConfig
    app: AppConfig
    bridge: BridgeSettings = BridgeSettings()
    dictionary: DictionarySettings = DictionarySettings()
    manual_input: ManualInputSettings = ManualInputSettings()


def load_config(path: Path | None = None) -> Config:
    if path is None:
        cfg_path, _created = ensure_user_config()
    else:
        cfg_path = path
    if not cfg_path.exists():
        example = example_config_path()
        raise FileNotFoundError(
            f"缺少 {cfg_path.name}。请复制 {example.name} 为 config.toml 并填写端点。"
        )

    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)

    llm_raw = raw.get("llm") or {}
    app_raw = raw.get("app") or {}
    bridge_raw = raw.get("bridge") or {}
    dictionary_raw = raw.get("dictionary") or {}
    manual_raw = raw.get("manual_input") or {}

    base_url = str(llm_raw.get("base_url", "")).rstrip("/")
    api_key = str(llm_raw.get("api_key", ""))
    model = str(llm_raw.get("model", ""))
    if not base_url or not model:
        raise ValueError("config.toml 中 llm.base_url 与 llm.model 不能为空")

    port = int(bridge_raw.get("port", DEFAULT_BRIDGE_PORT))
    if port < 1024 or port > 65535:
        port = DEFAULT_BRIDGE_PORT

    return Config(
        llm=LlmConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_s=float(llm_raw.get("timeout_s", 30)),
            thinking=bool(llm_raw.get("thinking", False)),
        ),
        app=AppConfig(
            target_lang=str(app_raw.get("target_lang", "zh")),
            min_chars=int(app_raw.get("min_chars", 2)),
            max_chars=int(app_raw.get("max_chars", 8000)),
            always_on_top=bool(app_raw.get("always_on_top", True)),
            cache_size=int(app_raw.get("cache_size", 128)),
            font_size=max(10, min(22, int(app_raw.get("font_size", 12)))),
            question_hotkey=str(
                app_raw.get("question_hotkey", default_question_hotkey())
            ).strip()
            or default_question_hotkey(),
        ),
        bridge=BridgeSettings(
            enabled=bool(bridge_raw.get("enabled", True)),
            port=port,
            token=str(bridge_raw.get("token", "")),
        ),
        dictionary=DictionarySettings(
            merriam_webster_api_key=str(
                dictionary_raw.get("merriam_webster_api_key", "")
            ).strip(),
        ),
        manual_input=ManualInputSettings(
            hotkey=str(
                manual_raw.get("hotkey", default_manual_input_hotkey())
            ).strip()
            or default_manual_input_hotkey(),
            x=_optional_int(manual_raw.get("x")),
            y=_optional_int(manual_raw.get("y")),
            width=max(300, int(manual_raw.get("width", 420))),
            height=max(116, int(manual_raw.get("height", 144))),
            opacity=max(0.35, min(1.0, float(manual_raw.get("opacity", 0.82)))),
        ),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _toml_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _upsert_toml_string(text: str, key: str, value: str, section: str) -> str:
    line = f'{key} = "{_toml_escape(value)}"'
    pattern = rf'(?m)^{re.escape(key)}\s*=\s*(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\n#]+)'
    if re.search(pattern, text):
        return re.sub(pattern, line, text, count=1)
    section_pat = rf"(?m)^(\[{re.escape(section)}\]\s*)$"
    if re.search(section_pat, text):
        return re.sub(section_pat, rf"\1\n{line}", text, count=1)
    return text.rstrip() + f"\n\n[{section}]\n{line}\n"


def save_font_size(size: int, path: Path | None = None) -> None:
    cfg_path = path or config_path()
    size = max(10, min(22, int(size)))
    text = cfg_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^font_size\s*=", text):
        text = re.sub(r"(?m)^font_size\s*=\s*\d+", f"font_size = {size}", text)
    elif re.search(r"(?m)^\[app\]\s*$", text):
        text = re.sub(r"(?m)^(\[app\]\s*)$", rf"\1\nfont_size = {size}", text, count=1)
    else:
        text = text.rstrip() + f"\n\n[app]\nfont_size = {size}\n"
    cfg_path.write_text(text, encoding="utf-8")


def save_question_hotkey(hotkey: str, path: Path | None = None) -> None:
    cfg_path = path or config_path()
    text = cfg_path.read_text(encoding="utf-8")
    text = _upsert_toml_string(text, "question_hotkey", hotkey.strip(), "app")
    cfg_path.write_text(text, encoding="utf-8")


def save_manual_input_hotkey(hotkey: str, path: Path | None = None) -> None:
    cfg_path = path or config_path()
    text = cfg_path.read_text(encoding="utf-8")
    text = _upsert_toml_string(text, "hotkey", hotkey.strip(), "manual_input")
    cfg_path.write_text(text, encoding="utf-8")


def save_llm_settings(
    base_url: str,
    api_key: str,
    model: str,
    path: Path | None = None,
) -> None:
    cfg_path = path or config_path()
    base_url = base_url.strip().rstrip("/")
    api_key = api_key.strip()
    model = model.strip()
    if not base_url or not model:
        raise ValueError("llm.base_url 与 llm.model 不能为空")

    text = cfg_path.read_text(encoding="utf-8")
    text = _upsert_toml_string(text, "base_url", base_url, "llm")
    text = _upsert_toml_string(text, "api_key", api_key, "llm")
    text = _upsert_toml_string(text, "model", model, "llm")
    cfg_path.write_text(text, encoding="utf-8")


def _upsert_toml_bool(text: str, key: str, value: bool, section: str) -> str:
    line = f"{key} = {'true' if value else 'false'}"
    pattern = rf"(?m)^{re.escape(key)}\s*=\s*(?:true|false|True|False|1|0)"
    if re.search(pattern, text):
        return re.sub(pattern, line, text, count=1)
    section_pat = rf"(?m)^(\[{re.escape(section)}\]\s*)$"
    if re.search(section_pat, text):
        return re.sub(section_pat, rf"\1\n{line}", text, count=1)
    return text.rstrip() + f"\n\n[{section}]\n{line}\n"


def _upsert_toml_int(text: str, key: str, value: int, section: str) -> str:
    line = f"{key} = {int(value)}"
    pattern = rf"(?m)^{re.escape(key)}\s*=\s*-?\d+"
    if re.search(pattern, text):
        return re.sub(pattern, line, text, count=1)
    section_pat = rf"(?m)^(\[{re.escape(section)}\]\s*)$"
    if re.search(section_pat, text):
        return re.sub(section_pat, rf"\1\n{line}", text, count=1)
    return text.rstrip() + f"\n\n[{section}]\n{line}\n"


def _upsert_toml_float(text: str, key: str, value: float, section: str) -> str:
    line = f"{key} = {float(value):.2f}"
    pattern = rf"(?m)^{re.escape(key)}\s*=\s*-?\d+(?:\.\d+)?"
    if re.search(pattern, text):
        return re.sub(pattern, line, text, count=1)
    section_pat = rf"(?m)^(\[{re.escape(section)}\]\s*)$"
    if re.search(section_pat, text):
        return re.sub(section_pat, rf"\1\n{line}", text, count=1)
    return text.rstrip() + f"\n\n[{section}]\n{line}\n"


def save_manual_input_settings(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    opacity: float,
    path: Path | None = None,
) -> None:
    cfg_path = path or config_path()
    text = cfg_path.read_text(encoding="utf-8")
    text = _upsert_toml_int(text, "x", x, "manual_input")
    text = _upsert_toml_int(text, "y", y, "manual_input")
    text = _upsert_toml_int(text, "width", max(300, width), "manual_input")
    text = _upsert_toml_int(text, "height", max(116, height), "manual_input")
    text = _upsert_toml_float(
        text,
        "opacity",
        max(0.35, min(1.0, opacity)),
        "manual_input",
    )
    cfg_path.write_text(text, encoding="utf-8")


def save_bridge_settings(
    enabled: bool,
    port: int,
    token: str | None = None,
    path: Path | None = None,
) -> None:
    cfg_path = path or config_path()
    port = int(port)
    if port < 1024 or port > 65535:
        raise ValueError("bridge.port 需在 1024–65535")
    text = cfg_path.read_text(encoding="utf-8")
    text = _upsert_toml_bool(text, "enabled", enabled, "bridge")
    text = _upsert_toml_int(text, "port", port, "bridge")
    if token is not None:
        text = _upsert_toml_string(text, "token", token, "bridge")
    cfg_path.write_text(text, encoding="utf-8")


def save_bridge_token(token: str, path: Path | None = None) -> None:
    cfg_path = path or config_path()
    text = cfg_path.read_text(encoding="utf-8")
    text = _upsert_toml_string(text, "token", token, "bridge")
    cfg_path.write_text(text, encoding="utf-8")


def save_dictionary_settings(
    merriam_webster_api_key: str,
    path: Path | None = None,
) -> None:
    cfg_path = path or config_path()
    text = cfg_path.read_text(encoding="utf-8")
    text = _upsert_toml_string(
        text,
        "merriam_webster_api_key",
        merriam_webster_api_key.strip(),
        "dictionary",
    )
    cfg_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    try:
        print(load_config())
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
