from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"


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


@dataclass(frozen=True)
class Config:
    llm: LlmConfig
    app: AppConfig


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        example = ROOT / "config.example.toml"
        raise FileNotFoundError(
            f"缺少 {cfg_path.name}。请复制 {example.name} 为 config.toml 并填写端点。"
        )

    with cfg_path.open("rb") as f:
        raw = tomllib.load(f)

    llm_raw = raw.get("llm") or {}
    app_raw = raw.get("app") or {}

    base_url = str(llm_raw.get("base_url", "")).rstrip("/")
    api_key = str(llm_raw.get("api_key", ""))
    model = str(llm_raw.get("model", ""))
    if not base_url or not model:
        raise ValueError("config.toml 中 llm.base_url 与 llm.model 不能为空")

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
        ),
    )


def save_font_size(size: int, path: Path | None = None) -> None:
    cfg_path = path or CONFIG_PATH
    size = max(10, min(22, int(size)))
    text = cfg_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^font_size\s*=", text):
        text = re.sub(r"(?m)^font_size\s*=\s*\d+", f"font_size = {size}", text)
    elif re.search(r"(?m)^\[app\]\s*$", text):
        text = re.sub(r"(?m)^(\[app\]\s*)$", rf"\1\nfont_size = {size}", text, count=1)
    else:
        text = text.rstrip() + f"\n\n[app]\nfont_size = {size}\n"
    cfg_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    try:
        print(load_config())
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
