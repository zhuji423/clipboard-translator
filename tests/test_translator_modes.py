from __future__ import annotations

import copy
import json
from threading import Event

from config import LlmConfig
from translation_context import build_translation_context
from translator import OpenAICompatTranslator


class _Response:
    status_code = 200
    text = ""

    def __init__(self, answer: str) -> None:
        self._answer = answer

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = True):
        payload = {"choices": [{"delta": {"content": self._answer}}]}
        yield "data: " + json.dumps(payload, ensure_ascii=False)
        yield 'data: {"usage":{"prompt_tokens":10,"completion_tokens":2}}'
        yield "data: [DONE]"

    def close(self) -> None:
        return None


class _Session:
    def __init__(self, answers: list[str]) -> None:
        self.headers: dict[str, str] = {}
        self.answers = iter(answers)
        self.payloads: list[dict] = []

    def post(self, _url: str, *, json: dict, stream: bool, timeout: float):
        self.payloads.append(copy.deepcopy(json))
        return _Response(next(self.answers))

    def get(self, *args, **kwargs):
        return _Response("")


def _session(mode: str, answers: list[str]):
    cfg = LlmConfig("https://api.example.com", "key", "deepseek")
    client = OpenAICompatTranslator(cfg, target_lang="zh", mode=mode)
    fake = _Session(answers)
    client._session = fake
    return client, fake


def test_answer_context_is_continuous_and_resettable() -> None:
    answerer, fake = _session("answer", ["第一答", "第二答", "重置后"])
    answerer.answer_stream("第一问", "zh", Event())
    answerer.answer_stream("为什么？", "zh", Event())

    second_messages = fake.payloads[1]["messages"]
    assert [item["content"] for item in second_messages[-3:]] == [
        "第一问",
        "第一答",
        "为什么？",
    ]

    answerer.reset_context()
    answerer.answer_stream("新问题", "zh", Event())
    reset_messages = fake.payloads[2]["messages"]
    assert len(reset_messages) == 2
    assert reset_messages[-1]["content"] == "新问题"


def test_translation_and_answer_sessions_do_not_share_messages() -> None:
    translator, translation_http = _session("translate", ["译文"])
    answerer, answer_http = _session("answer", ["答案"])

    translator.translate_stream("hello", "zh", Event())
    answerer.answer_stream("what is Python?", "zh", Event())

    answer_messages = answer_http.payloads[0]["messages"]
    translation_messages = translation_http.payloads[0]["messages"]
    assert all(item["content"] != "hello" for item in answer_messages)
    assert all(item["content"] != "what is Python?" for item in translation_messages)


def test_translation_is_stateless_and_uses_explicit_context() -> None:
    translator, fake = _session("translate", ["第一译", "第二译"])
    translator.translate_stream("first", "zh", Event())
    translator.translate_stream(
        "bank",
        "zh",
        Event(),
        context=build_translation_context(["We sat beside the river."], source="clipboard"),
    )

    second_messages = fake.payloads[1]["messages"]
    assert all(item["content"] not in {"first", "第一译"} for item in second_messages)
    structured = json.loads(second_messages[-1]["content"])
    assert structured["text_to_translate"] == "bank"
    assert structured["context"]["previous"] == ["We sat beside the river."]
