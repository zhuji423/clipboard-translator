from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QLocale, QObject, Signal
from PySide6.QtTextToSpeech import QTextToSpeech

_HAN_RE = re.compile(r"[\u4e00-\u9fff]")
_ENGLISH_PREFERRED = ("en-US", "en-GB")
_CHINESE_PREFERRED = ("zh-CN",)


class SpeechService(QObject):
    """Read source text through the platform's native TTS engine."""

    speaking_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None, engine: Any | None = None) -> None:
        super().__init__(parent)
        self._english: tuple[QLocale, Any] | None = None
        self._chinese: tuple[QLocale, Any] | None = None
        if engine is None:
            self._speech, self._available = self._create_native_speech()
        else:
            self._speech = engine
            self._available = self._resolve_voices(self._speech)
        self._speaking = False

        self._speech.stateChanged.connect(self._on_state_changed)
        self._speech.errorOccurred.connect(self._on_error)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def speaking(self) -> bool:
        return self._speaking

    def toggle(self, text: str) -> bool:
        if self._speaking:
            self.stop()
            return True
        return self.speak(text)

    def speak(self, text: str) -> bool:
        if not text.strip():
            return False
        wants_chinese = bool(_HAN_RE.search(text))
        selected = self._chinese if wants_chinese else self._english
        if selected is None or not self._available:
            self.error_occurred.emit(
                "未找到可用的系统中文语音" if wants_chinese else "未找到可用的系统英语语音"
            )
            return False
        locale, voice = selected
        self._speech.setLocale(locale)
        self._speech.setVoice(voice)
        self._speech.say(text)
        return True

    def stop(self) -> None:
        if self._speaking:
            self._speech.stop()

    def _create_native_speech(self) -> tuple[QTextToSpeech, bool]:
        try:
            engines = QTextToSpeech.availableEngines()
        except Exception:  # noqa: BLE001 - surface the failure in the UI
            engines = []

        candidates: list[str | None] = [None]
        candidates.extend(engine for engine in engines if engine != "mock")
        tried: set[str] = set()
        fallback: QTextToSpeech | None = None
        for engine_name in candidates:
            candidate = (
                QTextToSpeech()
                if engine_name is None
                else QTextToSpeech(engine_name)
            )
            actual_engine = candidate.engine()
            if actual_engine == "mock" or actual_engine in tried:
                continue
            tried.add(actual_engine)
            fallback = candidate
            if self._resolve_voices(candidate):
                candidate.setParent(self)
                return candidate, True

        if fallback is None:
            fallback = QTextToSpeech(self)
        else:
            fallback.setParent(self)
        return fallback, False

    def _resolve_voices(self, speech: Any) -> bool:
        self._english = _select_voice_for_language(
            speech, QLocale.Language.English, _ENGLISH_PREFERRED
        )
        self._chinese = _select_voice_for_language(
            speech, QLocale.Language.Chinese, _CHINESE_PREFERRED
        )
        return self._english is not None or self._chinese is not None

    def _on_state_changed(self, state: QTextToSpeech.State) -> None:
        speaking = state not in (
            QTextToSpeech.State.Ready,
            QTextToSpeech.State.Error,
        )
        if speaking != self._speaking:
            self._speaking = speaking
            self.speaking_changed.emit(speaking)

    def _on_error(self, _reason: object, message: str) -> None:
        self._available = False
        if self._speaking:
            self._speaking = False
            self.speaking_changed.emit(False)
        self.error_occurred.emit(message or "系统语音服务不可用")


def _select_voice_for_language(
    speech: Any,
    language: QLocale.Language,
    preferred: tuple[str, ...],
) -> tuple[QLocale, Any] | None:
    try:
        locales = list(speech.availableLocales())
    except Exception:  # noqa: BLE001 - surface the failure in the UI
        return None

    matched = [locale for locale in locales if locale.language() == language]
    if not matched:
        return None

    matched.sort(
        key=lambda locale: (
            preferred.index(locale.name().replace("_", "-"))
            if locale.name().replace("_", "-") in preferred
            else len(preferred)
        )
    )
    for locale in matched:
        speech.setLocale(locale)
        voices = list(speech.availableVoices())
        if voices:
            speech.setVoice(voices[0])
            return locale, voices[0]
    return None
