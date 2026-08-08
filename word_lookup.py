from __future__ import annotations

import json
import re
from dataclasses import dataclass
from threading import Event, Lock
from typing import Any

import requests

from config import LlmConfig
from translator import UsageInfo

LANG_LABELS = {
    "zh": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}

_MAX_WORD = 64
_MAX_CONTEXT = 500


@dataclass(frozen=True)
class LookupResult:
    word: str
    lemma: str
    pos: str
    gloss: str
    meaning_in_context: str
    usage: UsageInfo = UsageInfo()

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "lemma": self.lemma,
            "pos": self.pos,
            "gloss": self.gloss,
            "meaning_in_context": self.meaning_in_context,
        }


def normalize_word(word: str) -> str:
    return re.sub(r"\s+", " ", (word or "").strip())[:_MAX_WORD]


def normalize_context(context: str) -> str:
    return re.sub(r"\s+", " ", (context or "").strip())[:_MAX_CONTEXT]


def cache_key(target_lang: str, word: str, context: str) -> str:
    return f"{target_lang}\n{normalize_word(word).lower()}\n{normalize_context(context)}"


def _build_lookup_prompt(target_lang: str) -> str:
    lang = LANG_LABELS.get(target_lang, target_lang)
    return (
        "你是视频字幕语境查词助手。用户会给出一个单词/短语以及它所在的整句字幕。"
        f"请结合该句语境，用{lang}解释这个词在本句中的含义。"
        "只输出一个 JSON 对象，不要 Markdown、不要代码块、不要额外说明。"
        "字段必须且仅为："
        '{"lemma":"原形或词典形","pos":"词性（简短）","gloss":"简短词典义",'
        '"meaning_in_context":"本句中的简短释义"}。'
        "若无法判断词性，pos 可为空字符串。释义要短，不要扩写成段落。"
    )


class WordLookupService:
    """Stateless, single-shot word lookup — does not share clipboard translator history."""

    def __init__(self, cfg: LlmConfig) -> None:
        self._cfg = cfg
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            }
        )
        self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        self._lock = Lock()

    def update_config(self, cfg: LlmConfig) -> None:
        with self._lock:
            self._cfg = cfg
            self._session.headers["Authorization"] = f"Bearer {cfg.api_key}"
            self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"

    def lookup(
        self,
        word: str,
        context: str,
        target_lang: str,
        cancel_event: Event | None = None,
    ) -> LookupResult:
        word = normalize_word(word)
        context = normalize_context(context)
        if not word:
            raise ValueError("word 不能为空")

        user_content = (
            f"单词/短语：{word}\n"
            f"字幕原句：{context or word}\n"
            f"目标语言：{LANG_LABELS.get(target_lang, target_lang)}"
        )
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "stream": False,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": _build_lookup_prompt(target_lang)},
                {"role": "user", "content": user_content},
            ],
            "thinking": {"type": "enabled" if self._cfg.thinking else "disabled"},
        }

        with self._lock:
            session = self._session
            url = self._url
            timeout = self._cfg.timeout_s

        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("cancelled")

        resp = session.post(url, json=payload, timeout=timeout)
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("cancelled")
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        content = _extract_content(data)
        parsed = _parse_lookup_json(content)
        usage = _parse_usage(data.get("usage") or {})
        return LookupResult(
            word=word,
            lemma=str(parsed.get("lemma") or word),
            pos=str(parsed.get("pos") or ""),
            gloss=str(parsed.get("gloss") or ""),
            meaning_in_context=str(
                parsed.get("meaning_in_context")
                or parsed.get("gloss")
                or content.strip()
            ),
            usage=usage,
        )


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("模型未返回 choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    # Some providers return list parts
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        joined = "".join(parts).strip()
        if joined:
            return joined
    raise RuntimeError("模型未返回文本内容")


def _parse_lookup_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return {
        "lemma": "",
        "pos": "",
        "gloss": "",
        "meaning_in_context": text[:200],
    }


def _parse_usage(usage: dict[str, Any]) -> UsageInfo:
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    if completion == 0:
        prompt = int(usage.get("prompt_tokens") or 0)
        total = int(usage.get("total_tokens") or 0)
        if total > prompt:
            completion = total - prompt
        if miss == 0 and prompt:
            miss = prompt
    return UsageInfo(hit=hit, miss=miss, completion=completion)
