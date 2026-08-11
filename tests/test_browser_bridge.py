from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from browser_bridge import BridgeConfig, BrowserBridge
from translation_context import TranslationRequest


def _request(method: str, url: str, data: dict | None = None, headers: dict | None = None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw) if raw else {}


def test_bridge_health_pair_lookup_and_auth() -> None:
    state = {"token": "", "enabled": True, "port": 17991}
    lookups: list[tuple[str, str, str]] = []
    translates: list[TranslationRequest] = []

    def provider() -> BridgeConfig:
        return BridgeConfig(enabled=state["enabled"], port=state["port"], token=state["token"])

    def on_token(token: str) -> None:
        state["token"] = token

    def on_lookup(word: str, context: str, target_lang: str) -> dict:
        lookups.append((word, context, target_lang))
        return {
            "word": word,
            "lemma": word,
            "pos": "n.",
            "gloss": "测试",
            "meaning_in_context": "语境测试",
        }

    def on_translate(request: TranslationRequest) -> None:
        translates.append(request)

    bridge = BrowserBridge(
        config_provider=provider,
        target_lang_provider=lambda: "zh",
        on_lookup=on_lookup,
        on_translate=on_translate,
        on_token_saved=on_token,
        context_session_provider=lambda: "desktop-session",
    )
    bridge.start()
    try:
        status, health = _request("GET", f"http://127.0.0.1:{state['port']}/health")
        assert status == 200
        assert health["ok"] is True
        assert health["paired"] is False

        pairing = bridge.begin_pairing()
        status, bad = _request(
            "POST",
            f"http://127.0.0.1:{state['port']}/v1/pair",
            {"code": "000000"},
        )
        assert status == 400

        status, paired = _request(
            "POST",
            f"http://127.0.0.1:{state['port']}/v1/pair",
            {"code": pairing["code"]},
        )
        assert status == 200
        assert paired["ok"] is True
        assert state["token"]

        status, denied = _request(
            "POST",
            f"http://127.0.0.1:{state['port']}/v1/lookup",
            {"word": "hello", "context": "hello world"},
        )
        assert status == 401

        status, ok = _request(
            "POST",
            f"http://127.0.0.1:{state['port']}/v1/lookup",
            {"word": "hello", "context": "hello world"},
            headers={"Authorization": f"Bearer {state['token']}"},
        )
        assert status == 200
        assert ok["meaning_in_context"] == "语境测试"
        assert lookups == [("hello", "hello world", "zh")]

        status, translated = _request(
            "POST",
            f"http://127.0.0.1:{state['port']}/v1/translate",
            {"text": "hello world phrase"},
            headers={"Authorization": f"Bearer {state['token']}"},
        )
        assert status == 200
        assert translated["ok"] is True
        assert [request.text for request in translates] == ["hello world phrase"]
        assert translates[0].context.is_empty

        status, contextual = _request(
            "POST",
            f"http://127.0.0.1:{state['port']}/v1/translate",
            {
                "text": "bank",
                "context": {
                    "source": "youtube",
                    "session": "desktop-session",
                    "previous": ["We sat beside the river."],
                    "current": "The bank was muddy.",
                },
            },
            headers={"Authorization": f"Bearer {state['token']}"},
        )
        assert status == 200
        assert contextual["context_session"] == "desktop-session"
        assert translates[-1].context.previous == ("We sat beside the river.",)
        assert translates[-1].context.current == "The bank was muddy."

        status, stale = _request(
            "POST",
            f"http://127.0.0.1:{state['port']}/v1/translate",
            {
                "text": "bank",
                "context": {
                    "source": "youtube",
                    "session": "stale-session",
                    "previous": ["must not be used"],
                },
            },
            headers={"Authorization": f"Bearer {state['token']}"},
        )
        assert status == 200
        assert stale["context_session"] == "desktop-session"
        assert translates[-1].context.is_empty

        # Must bind loopback only
        assert bridge._server is not None
        assert bridge._server.server_address[0] == "127.0.0.1"
    finally:
        bridge.stop()


def test_word_lookup_json_parse() -> None:
    from word_lookup import _parse_lookup_json

    parsed = _parse_lookup_json(
        '```json\n{"lemma":"run","pos":"v.","gloss":"跑","meaning_in_context":"奔跑"}\n```'
    )
    assert parsed["lemma"] == "run"
    assert parsed["meaning_in_context"] == "奔跑"


if __name__ == "__main__":
    test_bridge_health_pair_lookup_and_auth()
    test_word_lookup_json_parse()
    print("ok")
