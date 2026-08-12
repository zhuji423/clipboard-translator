"""Platform default hotkey strings (no Qt — safe for Native Messaging host)."""

from __future__ import annotations

import sys


def default_question_hotkey() -> str:
    return "Alt+Shift+Q" if sys.platform == "darwin" else "Ctrl+Shift+Q"


def default_manual_input_hotkey() -> str:
    return "Alt+M" if sys.platform == "darwin" else "Ctrl+M"
