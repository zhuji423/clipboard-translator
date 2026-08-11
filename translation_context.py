from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

MAX_CONTEXT_ITEMS = 5
MAX_CONTEXT_ITEM_TOKENS = 500
MAX_CONTEXT_TOKENS = 2000
CONTEXT_IDLE_SECONDS = 5 * 60

_SPACE_RE = re.compile(r"\s+")


def normalize_context_text(value: object) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x3040 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )


def estimate_context_tokens(text: str) -> int:
    """Conservative model-independent estimate used only for context budgets."""
    normalized = normalize_context_text(text)
    if not normalized:
        return 0
    cjk = sum(1 for char in normalized if _is_cjk(char))
    other = len(normalized) - cjk
    return cjk + math.ceil(other / 4)


def trim_context_tail(text: str, max_tokens: int) -> str:
    normalized = normalize_context_text(text)
    if not normalized or max_tokens <= 0:
        return ""
    if estimate_context_tokens(normalized) <= max_tokens:
        return normalized

    low = 0
    high = len(normalized)
    while low < high:
        mid = (low + high) // 2
        if estimate_context_tokens(normalized[mid:]) <= max_tokens:
            high = mid
        else:
            low = mid + 1
    return normalized[low:].lstrip()


@dataclass(frozen=True)
class TranslationContext:
    previous: tuple[str, ...] = ()
    current: str = ""
    source: str = "clipboard"

    @property
    def is_empty(self) -> bool:
        return not self.previous and not self.current

    @property
    def token_estimate(self) -> int:
        return sum(estimate_context_tokens(item) for item in self.previous) + (
            estimate_context_tokens(self.current) if self.current else 0
        )

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "source": self.source,
                "previous": self.previous,
                "current": self.current,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TranslationRequest:
    text: str
    context: TranslationContext = TranslationContext()


def build_translation_context(
    previous: Iterable[object] = (),
    *,
    current: object = "",
    source: str = "clipboard",
    target_text: str = "",
) -> TranslationContext:
    normalized_previous: list[str] = []
    for raw in previous:
        item = trim_context_tail(
            normalize_context_text(raw), MAX_CONTEXT_ITEM_TOKENS
        )
        if item and (not normalized_previous or item != normalized_previous[-1]):
            normalized_previous.append(item)
    normalized_previous = normalized_previous[-MAX_CONTEXT_ITEMS:]

    current_text = normalize_context_text(current)
    current_matches_target = current_text == normalize_context_text(target_text)
    normalized_current = trim_context_tail(
        current_text, MAX_CONTEXT_ITEM_TOKENS
    )
    if current_matches_target:
        normalized_current = ""

    candidates: list[tuple[str, str]] = [
        ("previous", item) for item in normalized_previous
    ]
    if normalized_current:
        candidates.append(("current", normalized_current))

    selected: list[tuple[str, str]] = []
    remaining = MAX_CONTEXT_TOKENS
    for kind, item in reversed(candidates):
        if remaining <= 0:
            break
        bounded = trim_context_tail(
            item, min(MAX_CONTEXT_ITEM_TOKENS, remaining)
        )
        if not bounded:
            continue
        selected.append((kind, bounded))
        remaining -= estimate_context_tokens(bounded)
    selected.reverse()

    return TranslationContext(
        previous=tuple(item for kind, item in selected if kind == "previous"),
        current=next(
            (item for kind, item in selected if kind == "current"), ""
        ),
        source=normalize_context_text(source) or "clipboard",
    )


def translation_cache_key(
    target_lang: str, text: str, context: TranslationContext
) -> str:
    return f"{target_lang}\n{text}\ncontext:{context.fingerprint()}"


class RollingTranslationContext:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        idle_seconds: float = CONTEXT_IDLE_SECONDS,
    ) -> None:
        self._clock = clock
        self._idle_seconds = idle_seconds
        self._entries: deque[str] = deque(maxlen=MAX_CONTEXT_ITEMS)
        self._last_activity: float | None = None

    def clear(self) -> None:
        self._entries.clear()
        self._last_activity = None

    def snapshot_and_record(self, text: str) -> TranslationContext:
        now = self._clock()
        if (
            self._last_activity is not None
            and now - self._last_activity > self._idle_seconds
        ):
            self.clear()

        context = build_translation_context(
            self._entries, source="clipboard", target_text=text
        )
        entry = trim_context_tail(text, MAX_CONTEXT_ITEM_TOKENS)
        if entry and (not self._entries or entry != self._entries[-1]):
            self._entries.append(entry)
        self._last_activity = now
        return context
