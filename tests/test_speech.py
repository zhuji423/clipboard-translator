from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLocale, QObject, Signal
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtWidgets import QApplication

from speech import SpeechService
from window import TranslatorWindow

_APP = QApplication.instance() or QApplication([])


class _FakeSpeech(QObject):
    stateChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self, locales: list[QLocale]) -> None:
        super().__init__()
        self.locales = locales
        self.locale: QLocale | None = None
        self.voice: object | None = None
        self.spoken: list[str] = []
        self.stop_count = 0

    def availableLocales(self) -> list[QLocale]:  # noqa: N802
        return self.locales

    def setLocale(self, locale: QLocale) -> None:  # noqa: N802
        self.locale = locale

    def availableVoices(self) -> list[object]:  # noqa: N802
        return [object()]

    def setVoice(self, voice: object) -> None:  # noqa: N802
        self.voice = voice

    def say(self, text: str) -> None:
        self.spoken.append(text)
        self.stateChanged.emit(QTextToSpeech.State.Speaking)

    def stop(self) -> None:
        self.stop_count += 1
        self.stateChanged.emit(QTextToSpeech.State.Ready)


def test_speech_service_prefers_us_voice_and_toggles_playback() -> None:
    fake = _FakeSpeech(
        [
            QLocale(QLocale.Language.English, QLocale.Country.UnitedKingdom),
            QLocale(QLocale.Language.English, QLocale.Country.UnitedStates),
        ]
    )
    service = SpeechService(engine=fake)
    changes: list[bool] = []
    service.speaking_changed.connect(changes.append)

    assert service.available is True
    assert fake.locale is not None
    assert fake.locale.name() == "en_US"
    assert service.toggle("Hello world") is True
    assert fake.spoken == ["Hello world"]
    assert service.speaking is True
    assert service.toggle("ignored") is True
    assert fake.stop_count == 1
    assert changes == [True, False]


def test_speech_service_reports_missing_english_voice() -> None:
    fake = _FakeSpeech([QLocale(QLocale.Language.Chinese)])
    service = SpeechService(engine=fake)
    errors: list[str] = []
    service.error_occurred.connect(errors.append)

    assert service.available is False
    assert service.speak("Hello") is False
    assert errors == ["未找到可用的系统英语语音"]


def test_source_speaker_button_tracks_text_and_mode() -> None:
    window = TranslatorWindow()
    try:
        assert window.source_speak_btn.isEnabled() is False
        window.set_source("English source")
        assert window.source_speak_btn.isEnabled() is True
        assert window.source_speak_btn.isVisible() is False

        window.show()
        _APP.processEvents()
        assert window.source_speak_btn.isVisible() is True
        window.set_mode("answer")
        assert window.source_speak_btn.isVisible() is False
        window.set_mode("translate")
        assert window.source_speak_btn.isVisible() is True
        assert window.source_speak_btn.isEnabled() is True
    finally:
        window.close()
