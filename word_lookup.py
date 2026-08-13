from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html.parser import HTMLParser
from threading import Event, Lock
from typing import Any
from urllib.parse import quote

import requests

from cache import LruCache
from config import DictionarySettings, LlmConfig
from translator import UsageInfo

LANG_LABELS = {
    "zh": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}

_MAX_WORD = 64
_MAX_CONTEXT = 500
_MAX_EVIDENCE = 4000
_FACT_CACHE_CAPACITY = 256
_USER_AGENT = (
    "ClipboardTranslator/0.18.0 "
    "(https://github.com/zhuji423/clipboard-translator)"
)
_FREE_DICTIONARY_URL = "https://freedictionaryapi.com/api/v1/entries/en/{word}"
_MW_URL = "https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}"
_WIKTIONARY_API = "https://en.wiktionary.org/w/api.php"


@dataclass(frozen=True)
class WordPart:
    part: str
    type: str
    meaning: str

    def to_dict(self) -> dict[str, str]:
        return {"part": self.part, "type": self.type, "meaning": self.meaning}


@dataclass(frozen=True)
class LookupSource:
    name: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "url": self.url}


@dataclass(frozen=True)
class DictionaryFacts:
    lemma: str = ""
    pos: str = ""
    phonetic: str = ""
    definitions: tuple[str, ...] = ()
    etymology_evidence: str = ""
    sources: tuple[LookupSource, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LookupResult:
    word: str
    lemma: str
    pos: str
    phonetic: str
    gloss: str
    meaning_in_context: str
    word_parts: tuple[WordPart, ...] = ()
    etymology: str = ""
    mnemonic: str = ""
    mnemonic_kind: str = "associative"
    sources: tuple[LookupSource, ...] = ()
    warnings: tuple[str, ...] = ()
    usage: UsageInfo = UsageInfo()

    def to_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "lemma": self.lemma,
            "pos": self.pos,
            "phonetic": self.phonetic,
            "gloss": self.gloss,
            "meaning_in_context": self.meaning_in_context,
            "word_parts": [part.to_dict() for part in self.word_parts],
            "etymology": self.etymology,
            "mnemonic": self.mnemonic,
            "mnemonic_kind": self.mnemonic_kind,
            "sources": [source.to_dict() for source in self.sources],
            "warnings": list(self.warnings),
        }


def normalize_word(word: str) -> str:
    return re.sub(r"\s+", " ", (word or "").strip())[:_MAX_WORD]


def normalize_context(context: str) -> str:
    return re.sub(r"\s+", " ", (context or "").strip())[:_MAX_CONTEXT]


def normalize_source(source: str) -> str:
    return source if source in ("web", "youtube") else "youtube"


def cache_key(
    target_lang: str,
    word: str,
    context: str,
    source: str = "youtube",
    data_version: str = "free+wikt",
) -> str:
    return (
        f"{data_version}\n{normalize_source(source)}\n{target_lang}\n"
        f"{normalize_word(word).lower()}\n{normalize_context(context)}"
    )


def _build_lookup_prompt(target_lang: str, has_evidence: bool) -> str:
    lang = LANG_LABELS.get(target_lang, target_lang)
    evidence_rule = (
        "可以依据 ETYMOLOGY_EVIDENCE 给出简短的现代构词拆分。"
        if has_evidence
        else (
            "没有词源证据：word_parts 必须为 []，etymology 必须为空字符串；"
            "不得根据拼写猜测前缀、词根或后缀。"
        )
    )
    return (
        "你是严谨的英语语境查词与记忆助手。输入包含单词、当前句和词典事实。"
        f"请用{lang}返回一个 JSON 对象，不要 Markdown 或额外说明。"
        "字段必须且仅为 lemma、pos、gloss、meaning_in_context、word_parts、"
        "etymology、mnemonic、mnemonic_kind。"
        "word_parts 是对象数组，每项字段为 part、type、meaning，type 只能是 "
        "prefix、root、suffix、base、other。词源是历史来源，现代构词拆分是当前结构，"
        "两者不能混为一谈。"
        f"{evidence_rule}"
        "mnemonic 只写一句；有证据支持构词助记时 mnemonic_kind=evidence_based，"
        "否则可写不声称词源事实的联想助记并令 mnemonic_kind=associative。"
        "结合当前句选择义项，释义保持简短。词典事实不含中文时自行准确翻译。"
    )


class WordLookupService:
    """Combine dictionary facts with one evidence-grounded LLM explanation."""

    def __init__(
        self,
        cfg: LlmConfig,
        dictionary: DictionarySettings = DictionarySettings(),
    ) -> None:
        self._cfg = cfg
        self._dictionary = dictionary
        self._llm_session = requests.Session()
        self._free_dictionary_session = requests.Session()
        self._reference_session = requests.Session()
        self._llm_session.headers.update(
            {
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            }
        )
        for session in (self._free_dictionary_session, self._reference_session):
            session.headers.update(
                {"User-Agent": _USER_AGENT, "Accept": "application/json"}
            )
        self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        self._lock = Lock()
        self._fact_cache = LruCache(_FACT_CACHE_CAPACITY)

    @property
    def data_version(self) -> str:
        return "mw+wikt" if self._dictionary.merriam_webster_api_key else "free+wikt"

    def update_config(self, cfg: LlmConfig) -> None:
        with self._lock:
            self._cfg = cfg
            self._llm_session.headers["Authorization"] = f"Bearer {cfg.api_key}"
            self._url = f"{cfg.base_url.rstrip('/')}/chat/completions"

    def update_dictionary_config(self, dictionary: DictionarySettings) -> None:
        with self._lock:
            if dictionary == self._dictionary:
                return
            self._dictionary = dictionary
            self._fact_cache.clear()

    def lookup(
        self,
        word: str,
        context: str,
        target_lang: str,
        source: str = "youtube",
        cancel_event: Event | None = None,
    ) -> LookupResult:
        word = normalize_word(word)
        context = normalize_context(context)
        source = normalize_source(source)
        if not word:
            raise ValueError("word 不能为空")

        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("cancelled")

        facts = self._load_facts(word)
        lemma = facts.lemma or word
        evidence = facts.etymology_evidence[:_MAX_EVIDENCE]
        user_content = (
            f"WORD: {word}\n"
            f"LEMMA: {lemma}\n"
            f"SOURCE: {source}\n"
            f"CONTEXT: {context or word}\n"
            f"DICTIONARY_POS: {facts.pos}\n"
            f"PHONETIC: {facts.phonetic}\n"
            "DICTIONARY_DEFINITIONS:\n- "
            + "\n- ".join(facts.definitions[:8])
            + f"\nETYMOLOGY_EVIDENCE:\n{evidence or '[NONE]'}"
        )
        payload: dict[str, Any] = {
            "model": self._cfg.model,
            "stream": False,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": _build_lookup_prompt(target_lang, bool(evidence)),
                },
                {"role": "user", "content": user_content},
            ],
            "thinking": {"type": "enabled" if self._cfg.thinking else "disabled"},
        }

        with self._lock:
            session = self._llm_session
            url = self._url
            timeout = self._cfg.timeout_s

        resp = session.post(url, json=payload, timeout=timeout)
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("cancelled")
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        content = _extract_content(data)
        parsed = _parse_lookup_json(content)
        word_parts = _parse_word_parts(parsed.get("word_parts")) if evidence else ()
        etymology = str(parsed.get("etymology") or "").strip() if evidence else ""
        mnemonic_kind = str(parsed.get("mnemonic_kind") or "associative")
        if mnemonic_kind not in ("evidence_based", "associative"):
            mnemonic_kind = "associative"
        if not evidence:
            mnemonic_kind = "associative"

        return LookupResult(
            word=word,
            lemma=str(parsed.get("lemma") or lemma),
            pos=str(parsed.get("pos") or facts.pos),
            phonetic=facts.phonetic,
            gloss=str(parsed.get("gloss") or ""),
            meaning_in_context=str(
                parsed.get("meaning_in_context")
                or parsed.get("gloss")
                or content.strip()
            ),
            word_parts=word_parts,
            etymology=etymology,
            mnemonic=str(parsed.get("mnemonic") or "").strip(),
            mnemonic_kind=mnemonic_kind,
            sources=facts.sources,
            warnings=facts.warnings,
            usage=_parse_usage(data.get("usage") or {}),
        )

    def _load_facts(self, word: str) -> DictionaryFacts:
        cache_id = f"{self.data_version}\n{word.lower()}"
        cached = self._fact_cache.get(cache_id)
        if cached is not None:
            return _facts_from_json(cached)

        mw_key = self._dictionary.merriam_webster_api_key
        with ThreadPoolExecutor(max_workers=2) as executor:
            free_future = executor.submit(self._fetch_free_dictionary, word)
            mw_future = executor.submit(self._fetch_merriam_webster, word, mw_key)
            free_facts = free_future.result()
            mw_facts = mw_future.result()

        lemma = free_facts.lemma or mw_facts.lemma or word
        wikt_facts = DictionaryFacts()
        if not mw_facts.etymology_evidence:
            wikt_facts = self._fetch_wiktionary_etymology(lemma)

        combined = _combine_facts(word, free_facts, mw_facts, wikt_facts)
        serialized = _facts_to_json(combined)
        self._fact_cache.put(cache_id, serialized)
        lemma_cache_id = f"{self.data_version}\n{combined.lemma.lower()}"
        if combined.lemma and lemma_cache_id != cache_id:
            self._fact_cache.put(lemma_cache_id, serialized)
        return combined

    def _fetch_free_dictionary(self, word: str) -> DictionaryFacts:
        try:
            data = self._get_json(
                self._free_dictionary_session,
                _FREE_DICTIONARY_URL.format(word=quote(word, safe="")),
                timeout=8,
            )
            return _parse_free_dictionary(data, word)
        except Exception:  # noqa: BLE001 - optional source; expose as warning
            return DictionaryFacts(warnings=("免费词典暂不可用",))

    def _fetch_merriam_webster(self, word: str, key: str) -> DictionaryFacts:
        if not key:
            return DictionaryFacts()
        try:
            data = self._get_json(
                self._reference_session,
                _MW_URL.format(word=quote(word, safe="")),
                params={"key": key},
                timeout=8,
            )
            return _parse_merriam_webster(data, word)
        except Exception:  # noqa: BLE001 - fall back to Wiktionary
            return DictionaryFacts(warnings=("Merriam-Webster 暂不可用，已回退",))

    def _fetch_wiktionary_etymology(self, lemma: str) -> DictionaryFacts:
        source = LookupSource(
            "Wiktionary", f"https://en.wiktionary.org/wiki/{quote(lemma, safe='')}"
        )
        try:
            sections_data = self._get_json(
                self._reference_session,
                _WIKTIONARY_API,
                params={
                    "action": "parse",
                    "page": lemma,
                    "prop": "sections",
                    "format": "json",
                    "formatversion": 2,
                    "origin": "*",
                },
                timeout=8,
            )
            indexes = _find_english_etymology_sections(sections_data)
            chunks: list[str] = []
            for index in indexes[:4]:
                section_data = self._get_json(
                    self._reference_session,
                    _WIKTIONARY_API,
                    params={
                        "action": "parse",
                        "page": lemma,
                        "section": index,
                        "prop": "text",
                        "format": "json",
                        "formatversion": 2,
                        "origin": "*",
                    },
                    timeout=8,
                )
                rendered = str((section_data.get("parse") or {}).get("text") or "")
                plain = _html_to_text(rendered)
                if plain:
                    chunks.append(plain)
            evidence = "\n".join(chunks)[:_MAX_EVIDENCE]
            if not evidence:
                return DictionaryFacts(warnings=("暂无可靠词源拆解",))
            return DictionaryFacts(etymology_evidence=evidence, sources=(source,))
        except Exception:  # noqa: BLE001 - optional source
            return DictionaryFacts(warnings=("Wiktionary 词源暂不可用",))

    def _get_json(
        self,
        session: requests.Session,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float,
    ) -> Any:
        for attempt in range(2):
            response = session.get(url, params=params, timeout=timeout)
            if response.status_code == 429 and attempt == 0:
                retry_after = response.headers.get("Retry-After", "1")
                try:
                    delay = max(0.1, min(2.0, float(retry_after)))
                except ValueError:
                    delay = 1.0
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("dictionary rate limited")


def _parse_free_dictionary(data: Any, fallback_word: str) -> DictionaryFacts:
    if not isinstance(data, dict):
        return DictionaryFacts()
    entries = data.get("entries")
    if not isinstance(entries, list):
        return DictionaryFacts()
    lemma = str(data.get("word") or fallback_word)
    pos = ""
    phonetic = ""
    definitions: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not pos:
            pos = str(entry.get("partOfSpeech") or "")
        for pronunciation in entry.get("pronunciations") or []:
            if isinstance(pronunciation, dict):
                text = str(pronunciation.get("text") or "").strip()
                if text and ("IPA" in str(pronunciation.get("type") or "").upper() or not phonetic):
                    phonetic = text
        for sense in entry.get("senses") or []:
            if isinstance(sense, dict):
                definition = str(sense.get("definition") or "").strip()
                if definition and definition not in definitions:
                    definitions.append(definition)
    source_data = data.get("source") if isinstance(data.get("source"), dict) else {}
    source_url = str(source_data.get("url") or f"https://en.wiktionary.org/wiki/{quote(lemma)}")
    return DictionaryFacts(
        lemma=lemma,
        pos=pos,
        phonetic=phonetic,
        definitions=tuple(definitions[:12]),
        sources=(LookupSource("FreeDictionaryAPI / Wiktionary", source_url),),
    )


def _parse_merriam_webster(data: Any, fallback_word: str) -> DictionaryFacts:
    if not isinstance(data, list):
        return DictionaryFacts()
    entries = [item for item in data if isinstance(item, dict)]
    if not entries:
        return DictionaryFacts()
    entry = entries[0]
    meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
    lemma = str(meta.get("id") or fallback_word).split(":", 1)[0]
    phonetic = ""
    hwi = entry.get("hwi") if isinstance(entry.get("hwi"), dict) else {}
    for pronunciation in hwi.get("prs") or []:
        if isinstance(pronunciation, dict) and pronunciation.get("mw"):
            phonetic = str(pronunciation["mw"])
            break
    etymology_chunks: list[str] = []
    for etymology in entry.get("et") or []:
        if isinstance(etymology, (list, tuple)) and len(etymology) >= 2:
            etymology_chunks.append(_strip_mw_markup(str(etymology[1])))
    definitions = tuple(str(item) for item in (entry.get("shortdef") or []) if item)
    source = LookupSource(
        "Merriam-Webster",
        f"https://www.merriam-webster.com/dictionary/{quote(lemma, safe='')}",
    )
    return DictionaryFacts(
        lemma=lemma,
        pos=str(entry.get("fl") or ""),
        phonetic=phonetic,
        definitions=definitions[:8],
        etymology_evidence="\n".join(filter(None, etymology_chunks))[:_MAX_EVIDENCE],
        sources=(source,),
    )


def _find_english_etymology_sections(data: Any) -> list[str]:
    sections = (data.get("parse") or {}).get("sections") if isinstance(data, dict) else []
    if not isinstance(sections, list):
        return []
    in_english = False
    english_level = 0
    found: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        line = html.unescape(str(section.get("line") or "")).strip()
        level = int(section.get("level") or section.get("toclevel") or 0)
        if line == "English":
            in_english = True
            english_level = level
            continue
        if in_english and level <= english_level:
            break
        if in_english and re.fullmatch(r"Etymology(?:\s+\d+)?", line, re.I):
            found.append(str(section.get("index") or ""))
    return [index for index in found if index]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script", "sup"):
            self._skip_depth += 1
        elif tag in ("p", "li", "br") and self.parts:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "sup") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    text = html.unescape("".join(parser.parts))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _strip_mw_markup(value: str) -> str:
    value = re.sub(r"\{[^{}]*\|([^{}|]+)\}", r"\1", value)
    value = re.sub(r"\{[^{}]+\}", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _combine_facts(
    fallback_word: str,
    free: DictionaryFacts,
    mw: DictionaryFacts,
    wiktionary: DictionaryFacts,
) -> DictionaryFacts:
    evidence_source = mw if mw.etymology_evidence else wiktionary
    sources: list[LookupSource] = []
    for source in (*free.sources, *mw.sources, *wiktionary.sources):
        if source not in sources:
            sources.append(source)
    warnings = tuple(dict.fromkeys((*free.warnings, *mw.warnings, *wiktionary.warnings)))
    return DictionaryFacts(
        lemma=free.lemma or mw.lemma or fallback_word,
        pos=free.pos or mw.pos,
        phonetic=free.phonetic or mw.phonetic,
        definitions=free.definitions or mw.definitions,
        etymology_evidence=evidence_source.etymology_evidence,
        sources=tuple(sources),
        warnings=warnings,
    )


def _facts_to_json(facts: DictionaryFacts) -> str:
    return json.dumps(
        {
            "lemma": facts.lemma,
            "pos": facts.pos,
            "phonetic": facts.phonetic,
            "definitions": list(facts.definitions),
            "etymology_evidence": facts.etymology_evidence,
            "sources": [source.to_dict() for source in facts.sources],
            "warnings": list(facts.warnings),
        },
        ensure_ascii=False,
    )


def _facts_from_json(value: str) -> DictionaryFacts:
    data = json.loads(value)
    return DictionaryFacts(
        lemma=str(data.get("lemma") or ""),
        pos=str(data.get("pos") or ""),
        phonetic=str(data.get("phonetic") or ""),
        definitions=tuple(str(item) for item in data.get("definitions") or []),
        etymology_evidence=str(data.get("etymology_evidence") or ""),
        sources=tuple(
            LookupSource(str(item.get("name") or ""), str(item.get("url") or ""))
            for item in data.get("sources") or []
            if isinstance(item, dict)
        ),
        warnings=tuple(str(item) for item in data.get("warnings") or []),
    )


def _parse_word_parts(value: Any) -> tuple[WordPart, ...]:
    if not isinstance(value, list):
        return ()
    allowed_types = {"prefix", "root", "suffix", "base", "other"}
    parts: list[WordPart] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        part = str(item.get("part") or "").strip()[:40]
        part_type = str(item.get("type") or "other").strip()
        meaning = str(item.get("meaning") or "").strip()[:160]
        if not part or not meaning:
            continue
        if part_type not in allowed_types:
            part_type = "other"
        parts.append(WordPart(part, part_type, meaning))
    return tuple(parts)


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("模型未返回 choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
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
        "word_parts": [],
        "etymology": "",
        "mnemonic": "",
        "mnemonic_kind": "associative",
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
