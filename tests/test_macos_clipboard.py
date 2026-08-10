from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from macos_clipboard import MacClipboardPoller


def test_poller_emits_on_change_count() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    counts = iter([10, 10, 11, 11])
    poller = MacClipboardPoller(
        interval_ms=100,
        count_provider=lambda: next(counts, 11),
    )
    seen: list[int] = []
    poller.changed.connect(lambda: seen.append(1))
    poller.start()
    poller._tick()
    poller._tick()
    poller._tick()
    assert len(seen) == 1
    poller.stop()
    assert app is not None
