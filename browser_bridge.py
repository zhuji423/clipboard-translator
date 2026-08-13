from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from translation_context import TranslationRequest, build_translation_context
from distribution import extension_allowed_origins

DEFAULT_BRIDGE_PORT = 17890
PAIR_CODE_TTL_S = 120
RATE_LIMIT_WINDOW_S = 10.0
RATE_LIMIT_MAX = 30
MAX_BODY_BYTES = 32_768

# Client abort / navigation / AbortSignal.timeout often reset the socket mid-read.
_CLIENT_DISCONNECT_ERRORS = (
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    TimeoutError,
)


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    """Avoid stderr tracebacks when the browser closes /health probes early."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys

        exc = sys.exc_info()[1]
        if isinstance(exc, _CLIENT_DISCONNECT_ERRORS):
            return
        # WinError 10054 / 10053 sometimes wrap as OSError
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10054, 10053):
            return
        super().handle_error(request, client_address)


@dataclass(frozen=True)
class BridgeConfig:
    enabled: bool = False
    port: int = DEFAULT_BRIDGE_PORT
    token: str = ""


@dataclass
class PairingSession:
    code: str
    token: str
    expires_at: float


LookupHandler = Callable[[str, str, str, str], dict[str, Any]]
TranslateHandler = Callable[[TranslationRequest], None]
TranslateInlineHandler = Callable[[TranslationRequest], dict[str, Any]]
ConfigProvider = Callable[[], BridgeConfig]
TargetLangProvider = Callable[[], str]
ContextSessionProvider = Callable[[], str]


class BrowserBridge:
    """Localhost-only HTTP bridge for the browser extension."""

    def __init__(
        self,
        *,
        config_provider: ConfigProvider,
        target_lang_provider: TargetLangProvider,
        on_lookup: LookupHandler,
        on_translate: TranslateHandler | None = None,
        on_translate_inline: TranslateInlineHandler | None = None,
        on_token_saved: Callable[[str], None] | None = None,
        context_session_provider: ContextSessionProvider | None = None,
    ) -> None:
        self._config_provider = config_provider
        self._target_lang_provider = target_lang_provider
        self._on_lookup = on_lookup
        self._on_translate = on_translate
        self._on_translate_inline = on_translate_inline
        self._on_token_saved = on_token_saved
        self._context_session_provider = context_session_provider or (lambda: "")
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._pairing: PairingSession | None = None
        self._request_times: list[float] = []

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        cfg = self._config_provider()
        if not cfg.enabled:
            return
        with self._lock:
            if self._server is not None:
                return
            handler = self._make_handler()
            server = _QuietThreadingHTTPServer(("127.0.0.1", cfg.port), handler)
            server.daemon_threads = True
            thread = threading.Thread(
                target=server.serve_forever,
                name="browser-bridge",
                daemon=True,
            )
            self._server = server
            self._thread = thread
            thread.start()

    def stop(self) -> None:
        with self._lock:
            server = self._server
            self._server = None
            self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()

    def restart(self) -> None:
        self.stop()
        self.start()

    def begin_pairing(self) -> dict[str, Any]:
        cfg = self._config_provider()
        if not cfg.enabled:
            raise RuntimeError("浏览器集成未启用")
        if not self.is_running:
            self.start()
        code = f"{secrets.randbelow(1_000_000):06d}"
        token = secrets.token_urlsafe(32)
        session = PairingSession(
            code=code,
            token=token,
            expires_at=time.time() + PAIR_CODE_TTL_S,
        )
        with self._lock:
            self._pairing = session
        return {
            "code": code,
            "port": cfg.port,
            "expires_in": PAIR_CODE_TTL_S,
        }

    def revoke_token(self) -> None:
        with self._lock:
            self._pairing = None
        if self._on_token_saved:
            self._on_token_saved("")

    def _consume_rate_limit(self) -> bool:
        now = time.time()
        with self._lock:
            self._request_times = [
                t for t in self._request_times if now - t < RATE_LIMIT_WINDOW_S
            ]
            if len(self._request_times) >= RATE_LIMIT_MAX:
                return False
            self._request_times.append(now)
            return True

    def _current_token(self) -> str:
        return (self._config_provider().token or "").strip()

    def _complete_pairing(self, code: str) -> str:
        code = (code or "").strip()
        with self._lock:
            session = self._pairing
            if session is None or time.time() > session.expires_at:
                self._pairing = None
                raise RuntimeError("配对码无效或已过期，请在桌面端重新开始配对")
            if code != session.code:
                raise RuntimeError("配对码不正确")
            token = session.token
            self._pairing = None
        if self._on_token_saved:
            self._on_token_saved(token)
        return token

    def ensure_auto_pair_credentials(self) -> dict[str, Any]:
        """Return bridge token for zero-click HTTP pairing (create if missing)."""
        cfg = self._config_provider()
        if not cfg.enabled:
            raise RuntimeError("浏览器集成未启用")
        token = (cfg.token or "").strip()
        if not token:
            token = secrets.token_urlsafe(32)
            if self._on_token_saved:
                self._on_token_saved(token)
        return {
            "ok": True,
            "token": token,
            "port": cfg.port or DEFAULT_BRIDGE_PORT,
        }

    @staticmethod
    def _normalize_extension_origin(origin: str) -> str:
        value = (origin or "").strip()
        if not value:
            return ""
        return value if value.endswith("/") else f"{value}/"

    def _extension_origin_allowed(self, headers: dict[str, str]) -> bool:
        """Allow chrome-extension origins from distribution; missing Origin OK on loopback."""
        raw = headers.get("Origin") or headers.get("origin") or ""
        if not raw.strip():
            # Extension SW / some clients omit Origin; server is loopback-only.
            return True
        normalized = self._normalize_extension_origin(raw)
        allowed = {
            self._normalize_extension_origin(item) for item in extension_allowed_origins()
        }
        return normalized in allowed

    def _authorized(self, headers: dict[str, str]) -> bool:
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        token_header = headers.get("X-Bridge-Token") or headers.get("x-bridge-token") or ""
        expected = self._current_token()
        if not expected:
            return False
        presented = ""
        if auth.lower().startswith("bearer "):
            presented = auth[7:].strip()
        elif token_header:
            presented = token_header.strip()
        return bool(presented) and secrets.compare_digest(presented, expected)

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return

            def handle(self) -> None:
                try:
                    super().handle()
                except _CLIENT_DISCONNECT_ERRORS:
                    return
                except OSError as exc:
                    if getattr(exc, "winerror", None) in (10054, 10053):
                        return
                    raise

            def _send(
                self,
                status: int,
                payload: dict[str, Any] | None = None,
                *,
                extra_headers: dict[str, str] | None = None,
            ) -> None:
                body = b""
                if payload is not None:
                    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header(
                        "Access-Control-Allow-Headers",
                        "Content-Type, Authorization, X-Bridge-Token",
                    )
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    if extra_headers:
                        for key, value in extra_headers.items():
                            self.send_header(key, value)
                    self.end_headers()
                    if body:
                        self.wfile.write(body)
                except _CLIENT_DISCONNECT_ERRORS:
                    return
                except OSError as exc:
                    if getattr(exc, "winerror", None) in (10054, 10053):
                        return
                    raise

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._send(204)

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                cfg = bridge._config_provider()
                if path == "/health":
                    self._send(
                        200,
                        {
                            "ok": True,
                            "service": "clipboard-translator-bridge",
                            "enabled": cfg.enabled,
                            "paired": bool(cfg.token),
                            "port": cfg.port,
                        },
                    )
                    return
                self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if not bridge._consume_rate_limit():
                    self._send(429, {"error": "请求过于频繁，请稍后再试"})
                    return
                try:
                    length = int(self.headers.get("Content-Length") or "0")
                except ValueError:
                    self._send(400, {"error": "无效 Content-Length"})
                    return
                if length < 0 or length > MAX_BODY_BYTES:
                    self._send(413, {"error": "请求体过大"})
                    return
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send(400, {"error": "JSON 无效"})
                    return
                if not isinstance(data, dict):
                    self._send(400, {"error": "JSON 必须是对象"})
                    return

                if path == "/v1/pair":
                    try:
                        token = bridge._complete_pairing(str(data.get("code") or ""))
                    except RuntimeError as exc:
                        self._send(400, {"error": str(exc)})
                        return
                    self._send(200, {"ok": True, "token": token, "port": bridge._config_provider().port})
                    return

                if path == "/v1/auto_pair":
                    if not bridge._extension_origin_allowed(dict(self.headers)):
                        self._send(403, {"error": "来源未授权"})
                        return
                    try:
                        payload = bridge.ensure_auto_pair_credentials()
                    except RuntimeError as exc:
                        self._send(400, {"error": str(exc)})
                        return
                    self._send(200, payload)
                    return

                if path == "/v1/lookup":
                    if not bridge._authorized(dict(self.headers)):
                        self._send(401, {"error": "未授权：请先在扩展中完成与桌面端的配对"})
                        return
                    word = str(data.get("word") or "").strip()
                    context = str(data.get("context") or "").strip()
                    target_lang = str(
                        data.get("target_lang") or bridge._target_lang_provider()
                    ).strip() or "zh"
                    source = str(data.get("source") or "youtube").strip()
                    if source not in ("web", "youtube"):
                        self._send(400, {"error": "source 仅支持 web 或 youtube"})
                        return
                    if not word:
                        self._send(400, {"error": "word 不能为空"})
                        return
                    try:
                        result = bridge._on_lookup(word, context, target_lang, source)
                    except Exception as exc:  # noqa: BLE001
                        self._send(502, {"error": str(exc)})
                        return
                    self._send(200, {"ok": True, **result})
                    return

                if path == "/v1/translate":
                    if not bridge._authorized(dict(self.headers)):
                        self._send(401, {"error": "未授权：请先在扩展中完成与桌面端的配对"})
                        return
                    inline = bool(data.get("inline"))
                    if inline:
                        if bridge._on_translate_inline is None:
                            self._send(501, {"error": "桌面端未启用页内短语翻译"})
                            return
                    elif bridge._on_translate is None:
                        self._send(501, {"error": "桌面端未启用划词整段翻译"})
                        return
                    text = str(data.get("text") or "").strip()
                    if not text:
                        self._send(400, {"error": "text 不能为空"})
                        return
                    if len(text) > 8000:
                        text = text[:8000]
                    context_session = bridge._context_session_provider()
                    context_raw = data.get("context")
                    context = build_translation_context(
                        (), source="youtube", target_text=text
                    )
                    if isinstance(context_raw, dict):
                        request_session = str(context_raw.get("session") or "")
                        if request_session == context_session:
                            previous_raw = context_raw.get("previous")
                            previous = (
                                previous_raw
                                if isinstance(previous_raw, list)
                                else []
                            )
                            source = (
                                "youtube"
                                if str(context_raw.get("source") or "") == "youtube"
                                else "browser"
                            )
                            context = build_translation_context(
                                previous,
                                current=context_raw.get("current"),
                                source=source,
                                target_text=text,
                            )
                    request = TranslationRequest(text=text, context=context)
                    if inline:
                        try:
                            result = bridge._on_translate_inline(request)
                        except Exception as exc:  # noqa: BLE001
                            self._send(502, {"error": str(exc)})
                            return
                        if not isinstance(result, dict):
                            self._send(502, {"error": "页内翻译返回格式无效"})
                            return
                        translation = str(result.get("translation") or "").strip()
                        if not translation:
                            self._send(502, {"error": "译文为空"})
                            return
                        response: dict[str, Any] = {
                            "ok": True,
                            "translation": translation,
                        }
                        if context_session:
                            response["context_session"] = context_session
                        self._send(200, response)
                        return
                    try:
                        bridge._on_translate(request)
                    except Exception as exc:  # noqa: BLE001
                        self._send(502, {"error": str(exc)})
                        return
                    response = {"ok": True}
                    if context_session:
                        response["context_session"] = context_session
                    self._send(200, response)
                    return

                self._send(404, {"error": "not found"})

        return Handler
