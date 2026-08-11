from __future__ import annotations

from pathlib import Path

# Lightweight check of the extension phrase-buffer rules mirrored in TS.
# The canonical implementation is extension/src/phrase_buffer.ts.


def normalize_phrase(text: str) -> str:
    return " ".join(text.split()).strip()


def join_segments(segments: list[str]) -> str:
    return normalize_phrase(" ".join(segments))


def update_phrase_buffer(
    segments: list[str], text: str, append: bool, max_chars: int = 8000
) -> tuple[list[str], str, bool]:
    phrase = normalize_phrase(text)
    if not phrase:
        return list(segments), "", False
    if not append:
        return [phrase], phrase, False

    next_segs = list(segments)
    last = next_segs[-1] if next_segs else None
    if last is not None and last == phrase:
        pass
    elif last is not None and phrase.startswith(last) and len(phrase) > len(last):
        next_segs[-1] = phrase
    elif last is not None and last.startswith(phrase) and len(last) > len(phrase):
        pass
    else:
        next_segs.append(phrase)

    joined = join_segments(next_segs)
    truncated = False
    if len(joined) > max_chars:
        joined = joined[:max_chars]
        truncated = True
    return next_segs, joined, truncated


def test_plain_select_replaces_buffer() -> None:
    segs, joined, truncated = update_phrase_buffer(["old"], "hello world", False)
    assert segs == ["hello world"]
    assert joined == "hello world"
    assert not truncated


def test_append_joins_and_dedupes() -> None:
    segs: list[str] = []
    segs, joined, _ = update_phrase_buffer(segs, "one two", True)
    assert joined == "one two"
    segs, joined, _ = update_phrase_buffer(segs, "three", True)
    assert segs == ["one two", "three"]
    assert joined == "one two three"
    segs, joined, _ = update_phrase_buffer(segs, "three", True)
    assert segs == ["one two", "three"]
    assert joined == "one two three"


def test_append_replaces_superset_last() -> None:
    segs, joined, _ = update_phrase_buffer(["hello"], "hello world", True)
    assert segs == ["hello world"]
    assert joined == "hello world"


def test_source_file_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "extension" / "src" / "phrase_buffer.ts").is_file()
