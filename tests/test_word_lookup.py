from __future__ import annotations

import json
from typing import Any

from config import DictionarySettings, LlmConfig
from word_lookup import (
    DictionaryFacts,
    LookupSource,
    WordLookupService,
    _build_lookup_prompt,
    _find_english_etymology_sections,
    _html_to_text,
    _parse_free_dictionary,
    _parse_merriam_webster,
)


class _Response:
    status_code = 200
    text = ""

    def __init__(self, data: Any) -> None:
        self._data = data

    def json(self) -> Any:
        return self._data


class _LlmSession:
    def __init__(self, data: Any) -> None:
        self.data = data
        self.headers: dict[str, str] = {}
        self.payload: dict[str, Any] = {}

    def post(self, _url: str, *, json: dict[str, Any], timeout: float) -> _Response:
        assert timeout > 0
        self.payload = json
        return _Response(self.data)


def _service() -> WordLookupService:
    return WordLookupService(
        LlmConfig("https://api.example.com", "key", "model"),
        DictionarySettings(),
    )


def test_parse_free_dictionary_facts() -> None:
    facts = _parse_free_dictionary(
        {
            "word": "unpredictable",
            "entries": [
                {
                    "partOfSpeech": "adjective",
                    "pronunciations": [
                        {"type": "IPA", "text": "/test/"},
                    ],
                    "senses": [{"definition": "Not able to be predicted."}],
                }
            ],
            "source": {"url": "https://en.wiktionary.org/wiki/unpredictable"},
        },
        "unpredictable",
    )
    assert facts.lemma == "unpredictable"
    assert facts.pos == "adjective"
    assert facts.phonetic == "/test/"
    assert facts.definitions == ("Not able to be predicted.",)
    assert facts.sources[0].url.endswith("/unpredictable")


def test_parse_merriam_webster_etymology() -> None:
    facts = _parse_merriam_webster(
        [
            {
                "meta": {"id": "predict:1"},
                "fl": "verb",
                "hwi": {"prs": [{"mw": "pri-ˈdikt"}]},
                "shortdef": ["to declare in advance"],
                "et": [["text", "Latin {it}praedicere{/it}"]],
            }
        ],
        "predict",
    )
    assert facts.lemma == "predict"
    assert facts.pos == "verb"
    assert facts.phonetic == "pri-ˈdikt"
    assert "Latin" in facts.etymology_evidence
    assert facts.sources[0].name == "Merriam-Webster"


def test_wiktionary_sections_are_limited_to_english() -> None:
    data = {
        "parse": {
            "sections": [
                {"line": "French", "level": "2", "index": "1"},
                {"line": "Etymology", "level": "3", "index": "2"},
                {"line": "English", "level": "2", "index": "3"},
                {"line": "Etymology 1", "level": "3", "index": "4"},
                {"line": "Noun", "level": "3", "index": "5"},
                {"line": "Etymology 2", "level": "3", "index": "6"},
                {"line": "German", "level": "2", "index": "7"},
                {"line": "Etymology", "level": "3", "index": "8"},
            ]
        }
    }
    assert _find_english_etymology_sections(data) == ["4", "6"]


def test_html_to_text_removes_reference_noise() -> None:
    value = "<p>From <i>Latin</i> test<sup>[1]</sup>.</p><script>bad()</script>"
    assert _html_to_text(value) == "From Latin test."


def test_no_evidence_forces_empty_word_parts() -> None:
    service = _service()
    service._load_facts = lambda _word: DictionaryFacts(  # type: ignore[method-assign]
        lemma="opaque",
        pos="adjective",
        phonetic="/oʊˈpeɪk/",
        definitions=("not transparent",),
        sources=(LookupSource("FreeDictionaryAPI / Wiktionary", "https://example.com"),),
    )
    service._llm_session = _LlmSession(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "lemma": "opaque",
                                "pos": "adjective",
                                "gloss": "不透明的",
                                "meaning_in_context": "难以理解的",
                                "word_parts": [
                                    {"part": "op-", "type": "prefix", "meaning": "伪造"}
                                ],
                                "etymology": "伪造词源",
                                "mnemonic": "联想一块不透明玻璃",
                                "mnemonic_kind": "evidence_based",
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
            "usage": {},
        }
    )
    result = service.lookup("opaque", "The process was opaque.", "zh", "web")
    assert result.word_parts == ()
    assert result.etymology == ""
    assert result.mnemonic_kind == "associative"
    prompt = service._llm_session.payload["messages"][0]["content"]  # type: ignore[attr-defined]
    assert "不得根据拼写猜测" in prompt


def test_dictionary_key_change_clears_fact_cache() -> None:
    service = _service()
    service._fact_cache.put("free+wikt\nword", "cached")
    service.update_dictionary_config(DictionarySettings("new-key"))
    assert service._fact_cache.get("free+wikt\nword") is None
    assert service.data_version == "mw+wikt"


def test_fact_cache_adds_lemma_alias() -> None:
    service = _service()
    calls = {"free": 0}

    def free(_word: str) -> DictionaryFacts:
        calls["free"] += 1
        return DictionaryFacts(lemma="run", definitions=("move quickly",))

    service._fetch_free_dictionary = free  # type: ignore[method-assign]
    service._fetch_merriam_webster = lambda *_args: DictionaryFacts()  # type: ignore[method-assign]
    service._fetch_wiktionary_etymology = lambda _lemma: DictionaryFacts()  # type: ignore[method-assign]

    assert service._load_facts("running").lemma == "run"
    assert service._load_facts("run").lemma == "run"
    assert calls["free"] == 1


def test_prompt_distinguishes_etymology_and_morphology() -> None:
    prompt = _build_lookup_prompt("zh", True)
    assert "词源是历史来源" in prompt
    assert "现代构词拆分" in prompt
