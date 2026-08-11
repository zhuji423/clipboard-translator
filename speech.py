from __future__ import annotations

from typing import Any

from PySide6.QtCore import QLocale, QObject, Signal
from PySide6.QtTextToSpeech import QTextToSpeech


class SpeechService(QObject):
    """Read English source text through the platform's native TTS engine."""

    speaking_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None, engine: Any | None = None) -> None:
        super().__init__(parent)
        if engine is None:
            self._speech, self._available = self._create_native_speech()
        else:
            self._speech = engine
            self._available = self._select_english_voice(self._speech)
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
        if not self._available:
            self.error_occurred.emit("未找到可用的系统英语语音")
            return False
        if not text.strip():
            return False
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
            if self._select_english_voice(candidate):
                candidate.setParent(self)
                return candidate, True

        if fallback is None:
            fallback = QTextToSpeech(self)
        else:
            fallback.setParent(self)
        return fallback, False

    def _select_english_voice(self, speech: Any) -> bool:
        try:
            locales = list(speech.availableLocales())
        except Exception:  # noqa: BLE001 - surface the failure in the UI
            return False

        english_locales = [
            locale
            for locale in locales
            if locale.language() == QLocale.Language.English
        ]
        if not english_locales:
            return False

        preferred = ("en-US", "en-GB")
        english_locales.sort(
            key=lambda locale: (
                preferred.index(locale.name().replace("_", "-"))
                if locale.name().replace("_", "-") in preferred
                else len(preferred)
            )
        )
        for locale in english_locales:
            speech.setLocale(locale)
            voices = list(speech.availableVoices())
            if voices:
                speech.setVoice(voices[0])
                return True
        return False

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
